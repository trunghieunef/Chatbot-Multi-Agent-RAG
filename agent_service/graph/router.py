from __future__ import annotations

import json
import time
import unicodedata
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from agent_service.config import get_agent_settings
from agent_service.contracts import StructuredWarning
from agent_service.llm.gemini import GeminiClient
from app.database import async_session


ALLOWED_AGENTS = {
    "property_search",
    "project_agent",
    "market_analysis",
    "news_agent",
    "legal_advisor",
    "investment_advisor",
}

AGENT_ORDER = [
    "legal_advisor",
    "investment_advisor",
    "market_analysis",
    "news_agent",
    "project_agent",
    "property_search",
]

INTENT_BY_AGENT = {
    "legal_advisor": "legal_advice",
    "investment_advisor": "investment_advice",
    "market_analysis": "market_analysis",
    "news_agent": "news",
    "project_agent": "project",
    "property_search": "property_search",
}

KEYWORDS_BY_AGENT = {
    "legal_advisor": ["phap ly", "luat", "thu tuc", "cong chung", "so do", "sang ten"],
    "investment_advisor": ["dau tu", "roi", "loi nhuan", "sinh loi", "rental yield"],
    "market_analysis": ["thi truong", "xu huong", "thong ke", "gia trung binh", "gia", "gia ca", "bao nhieu"],
    "news_agent": ["tin tuc", "bao chi", "cap nhat"],
    "project_agent": ["du an", "chu dau tu"],
    "property_search": ["tim", "mua", "thue", "can ho", "nha", "dat", "quan "],
}


# The canonical property_type taxonomy is whatever the ETL actually wrote to the
# data (data_pipeline/clean.py::determine_property_type), in Vietnamese. Rather
# than hardcode and duplicate that list here, the router reads the distinct
# values straight from the DB and injects them into the LLM prompt, so the model
# can only emit values that exist and the SQL filter matches them. Cached
# in-process with a TTL since the taxonomy changes rarely.
_PROPERTY_TYPE_VOCAB_CACHE: tuple[float, list[str]] | None = None
_PROPERTY_TYPE_VOCAB_TTL = 3600.0


async def _fetch_distinct_property_types() -> list[str]:
    """Read the distinct, non-empty property_type values from the listings data."""
    query = text(
        "SELECT DISTINCT property_type FROM listings "
        "WHERE property_type IS NOT NULL AND btrim(property_type) <> '' "
        "ORDER BY property_type"
    )
    async with async_session() as session:
        result = await session.execute(query)
        return [row[0] for row in result.all()]


async def get_property_type_vocabulary(
    *, ttl_seconds: float = _PROPERTY_TYPE_VOCAB_TTL
) -> list[str]:
    """Distinct property_type values from the DB, cached in-process with a TTL.

    Degrades to the last cached value, or ``[]`` if never loaded, on any DB
    error so routing never breaks just because the taxonomy lookup failed.
    """
    global _PROPERTY_TYPE_VOCAB_CACHE
    now = time.monotonic()
    if _PROPERTY_TYPE_VOCAB_CACHE is not None:
        cached_at, values = _PROPERTY_TYPE_VOCAB_CACHE
        if now - cached_at < ttl_seconds:
            return values
    try:
        values = await _fetch_distinct_property_types()
    except Exception:
        return _PROPERTY_TYPE_VOCAB_CACHE[1] if _PROPERTY_TYPE_VOCAB_CACHE else []
    _PROPERTY_TYPE_VOCAB_CACHE = (now, values)
    return values


class RouterDecision(BaseModel):
    intent: str
    agents: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    filters: dict[str, Any] = Field(default_factory=dict)
    needs_clarification: bool = False
    clarifying_question: str | None = None
    reason: str = ""
    rewritten_query: str | None = None
    mode: str = "rule"
    warnings: list[Any] = Field(default_factory=list)


def _strip_accents(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_marks.lower()


def _normalized_tokens(value: str) -> set[str]:
    import re

    return set(re.findall(r"[a-z0-9]+", value))


def _keyword_matches(
    keyword: str,
    normalized_query: str,
    normalized_tokens: set[str],
) -> bool:
    normalized_keyword = _strip_accents(keyword)
    stripped_keyword = normalized_keyword.strip()
    if not stripped_keyword:
        return False
    if stripped_keyword != normalized_keyword or " " in stripped_keyword:
        return normalized_keyword in normalized_query
    return stripped_keyword in normalized_tokens


def sanitize_agents(agents: list[str]) -> tuple[list[str], list[str]]:
    valid = []
    dropped = []
    for agent in agents:
        if agent in ALLOWED_AGENTS and agent not in valid:
            valid.append(agent)
        else:
            dropped.append(agent)
    return valid, dropped


def route_with_rules(state: dict[str, Any]) -> RouterDecision:
    request = state["request"]
    normalized_query = state.get("normalized_query") or _strip_accents(request.message)
    normalized_tokens = _normalized_tokens(normalized_query)
    agents = [
        agent
        for agent in AGENT_ORDER
        if any(
            _keyword_matches(keyword, normalized_query, normalized_tokens)
            for keyword in KEYWORDS_BY_AGENT[agent]
        )
    ]

    if not agents:
        agents = ["property_search"]

    intent = INTENT_BY_AGENT[agents[0]] if len(agents) == 1 else "mixed"
    return RouterDecision(
        intent=intent,
        agents=agents,
        confidence=1.0,
        filters={
            "locale": request.locale,
            "user_preferences": request.user_preferences,
        },
        reason="keyword rules",
        mode="rule",
    )


def merge_router_decisions(
    rule: RouterDecision,
    llm: RouterDecision,
    *,
    confidence_threshold: float,
) -> RouterDecision:
    agents = list(rule.agents)
    if llm.confidence >= confidence_threshold:
        for agent in llm.agents:
            if agent not in agents:
                agents.append(agent)
    if not agents:
        agents = ["property_search"]
    return RouterDecision(
        intent=rule.intent if len(agents) == 1 else "mixed",
        agents=agents,
        confidence=max(rule.confidence, llm.confidence),
        filters={**llm.filters, **rule.filters},
        mode="hybrid",
        reason=f"rule={rule.reason}; llm={llm.reason}",
        warnings=[*rule.warnings, *llm.warnings],
    )


def _router_prompt(
    query: str,
    compact_context: list[dict[str, Any]] | None = None,
    property_types: list[str] | None = None,
) -> str:
    context = compact_context or []
    if property_types:
        property_type_line = (
            "- property_type: CHỌN ĐÚNG MỘT giá trị trong danh sách sau, "
            "giữ nguyên tiếng Việt (KHÔNG dịch sang tiếng Anh): "
            + " | ".join(property_types)
            + "."
        )
    else:
        property_type_line = (
            "- property_type: loại hình bất động sản, giữ nguyên cụm từ "
            "tiếng Việt người dùng dùng (KHÔNG dịch sang tiếng Anh)."
        )
    return "\n".join([
        "Bạn là bộ định tuyến (router) trong hệ thống tư vấn bất động sản Agentic RAG.",
        "Nhiệm vụ: phân tích query và chọn agent(s) phù hợp để xử lý.",
        "",
        "### Các agent có sẵn:",
        "- property_search: Tìm kiếm bất động sản (mua, thuê, căn hộ, nhà, đất).",
        "- market_analysis: Phân tích thị trường, giá cả, xu hướng, thống kê.",
        "- legal_advisor: Tư vấn pháp lý (sổ đỏ, công chứng, thuế, hợp đồng, thủ tục).",
        "- investment_advisor: Tư vấn đầu tư, ROI, so sánh kênh đầu tư.",
        "- project_agent: Đánh giá dự án bất động sản, chủ đầu tư.",
        "- news_agent: Tin tức, bài báo về bất động sản.",
        "",
        "### Quy tắc chọn agent:",
        "- Query hỏi về GIÁ CẢ, XU HƯỚNG, THỐNG KÊ → chọn market_analysis.",
        "- Query hỏi MUA/BÁN/THUÊ cụ thể → chọn property_search.",
        "- Query hỏi PHÁP LÝ, LUẬT, THỦ TỤC → chọn legal_advisor.",
        "- Query hỏi ĐẦU TƯ, LỢI NHUẬN, ROI → chọn investment_advisor.",
        "- Có thể chọn NHIỀU agent nếu query phức tạp.",
        "",
        "### Bộ lọc cần trích xuất (nếu có):",
        "- city: Tỉnh/Thành phố.",
        "- district: Quận/Huyện.",
        property_type_line,
        "- listing_type: sale hoặc rent.",
        "- bedrooms: số phòng ngủ (số nguyên), dùng đúng key 'bedrooms'.",
        "- min_price, max_price: số thực, ĐƠN VỊ TỶ VND "
        "(ví dụ '7 tỷ' -> 7, KHÔNG ghi 7000000000).",
        "",
        f"### Hội thoại gần đây: {json.dumps(context[-3:] if context else [], ensure_ascii=False)}",
        f"### Query: {query}",
        "",
        "Trả về CHỈ MỘT JSON object (không markdown, không code fence) với định dạng:",
        "{",
        '  "intent": "market_analysis|property_search|legal_advice|investment_advice|news|project|mixed",',
        '  "agents": ["agent_1", "agent_2"],',
        '  "confidence": 0.0-1.0,',
        '  "filters": {"city": "...", "district": "...", ...},',
        '  "rewritten_query": "câu hỏi đã được chuẩn hóa, bổ sung ngữ cảnh thiếu từ lịch sử hội thoại, dùng cho retrieval",',
        '  "reason": "lý do ngắn gọn tại sao chọn các agent này"',
        "}",
    ])

async def route_with_llm(
    state: dict[str, Any],
    client: GeminiClient | None = None,
) -> RouterDecision:
    request = state["request"]
    settings = get_agent_settings()
    client = client or GeminiClient()
    try:
        context = state.get("conversation_context") or state.get("compact_context", [])
        property_types = await get_property_type_vocabulary()
        payload = await client.generate_json(
            _router_prompt(request.message, context, property_types),
            timeout_seconds=settings.AGENT_LLM_ROUTER_TIMEOUT_SECONDS,
        )
        decision = RouterDecision.model_validate(payload)
    except Exception:
        return RouterDecision(
            intent="fallback",
            agents=[],
            confidence=0.0,
            mode="fallback",
            reason="invalid llm router output",
            warnings=["llm_router_invalid_json"],
        )

    agents, dropped = sanitize_agents(decision.agents)
    warnings = list(decision.warnings)
    if dropped:
        warnings.append(
            StructuredWarning(
                code="llm_router_unknown_agents",
                domain=None,
                message=f"Unknown agents dropped: {', '.join(dropped)}",
            )
        )
    if decision.confidence < settings.AGENT_LLM_CONFIDENCE_THRESHOLD:
        warnings.append(
            StructuredWarning(
                code="llm_router_low_confidence",
                domain=None,
                message=f"Confidence {decision.confidence} below threshold {settings.AGENT_LLM_CONFIDENCE_THRESHOLD}",
            )
        )
    return decision.model_copy(
        update={
            "agents": agents,
            "warnings": warnings,
            "mode": "llm",
        }
    )


async def route_request(
    state: dict[str, Any],
    client: GeminiClient | None = None,
) -> RouterDecision:
    settings = get_agent_settings()
    rule = route_with_rules(state)
    if state.get("force_deterministic") or settings.AGENT_ROUTER_MODE == "rule":
        return rule

    llm = await route_with_llm(state, client=client)
    if settings.AGENT_ROUTER_MODE == "llm":
        if llm.confidence >= settings.AGENT_LLM_CONFIDENCE_THRESHOLD and llm.agents:
            return llm
        return rule.model_copy(
            update={
                "mode": "fallback",
                "warnings": [*rule.warnings, *llm.warnings],
                "reason": f"{rule.reason}; llm fallback={llm.reason}",
            }
        )

    return merge_router_decisions(
        rule,
        llm,
        confidence_threshold=settings.AGENT_LLM_CONFIDENCE_THRESHOLD,
    )

