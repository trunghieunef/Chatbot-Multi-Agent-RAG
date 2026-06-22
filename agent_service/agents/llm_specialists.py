from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError


DeterministicRunner = Callable[..., Awaitable[dict[str, Any]]]
GenerateJson = Callable[..., Awaitable[dict[str, Any]]]


class LLMSpecialistOutput(BaseModel):
    agent_name: str
    status: str
    content: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids_used: list[str] = Field(default_factory=list)
    confidence: float | str | None = None
    warnings: list[Any] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


def _evidence_id(record: dict[str, Any]) -> str | None:
    value = record.get("evidence_id") or record.get("id")
    return str(value) if value is not None else None


def _compact_evidence(record: dict[str, Any]) -> dict[str, Any]:
    facts = record.get("facts") if isinstance(record.get("facts"), dict) else {}
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    return {
        "evidence_id": _evidence_id(record),
        "domain": record.get("domain"),
        "source_type": record.get("source_type"),
        "facts": facts,
        "source": {
            "type": source.get("type"),
            "title": source.get("title"),
            "url": source.get("url"),
        },
    }


def build_specialist_prompt(
    *,
    agent_name: str,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
) -> str:
    evidence_payload = [_compact_evidence(record) for record in evidence]

    # ── Domain‑specific guardrails & instructions ──────────────────────
    domain_barriers: dict[str, str] = {
        "legal_advisor": (
            "BẠN CHỈ ĐƯỢC TRẢ LỜI các câu hỏi pháp lý liên quan đến BẤT ĐỘNG SẢN: "
            "mua bán, cho thuê, chuyển nhượng, giấy tờ pháp lý (sổ đỏ, sổ hồng, "
            "giấy chứng nhận), thuế phí, lệ phí trước bạ, sang tên, công chứng, "
            "thừa kế, thế chấp, quy hoạch, xây dựng, đất đai, nhà ở, chung cư, "
            "dự án bất động sản, đền bù giải tỏa, hợp đồng mua bán/thuê bất động sản.\n"
            "Nếu câu hỏi KHÔNG liên quan đến bất động sản, hãy trả lời: "
            "'Tôi chỉ hỗ trợ các vấn đề pháp lý về bất động sản. "
            "Vui lòng hỏi về mua bán, giấy tờ, thuế phí, hoặc các vấn đề pháp lý "
            "liên quan đến nhà đất.' và đặt status='out_of_domain'."
        ),
    }

    # ── Agent‑specific LLM instructions ───────────────────────────────
    agent_instructions: dict[str, str] = {
        "market_analysis": (
            "Bạn là chuyên gia phân tích thị trường bất động sản. "
            "Evidence bạn nhận được chứa dữ liệu chuỗi thời gian (timeseries) "
            "với các trường: month, avg_price_per_m2, listing_count, trend direction, "
            "change_pct (phần trăm thay đổi).\n"
            "Hãy:\n"
            "1. Diễn giải xu hướng giá (tăng/giảm/đi ngang) bằng tiếng Việt tự nhiên\n"
            "2. Nêu mức giá trung bình, cao nhất, thấp nhất trong kỳ\n"
            "3. Đánh giá mức độ biến động (cao/thấp)\n"
            "4. Nếu có đủ dữ liệu, so sánh với các khu vực lân cận\n"
            "5. LUÔN kèm disclaimer: 'Dữ liệu chỉ mang tính tham khảo, giá thực tế "
            "có thể khác tùy vị trí cụ thể.'"
        ),
        "property_search": (
            "Bạn là chuyên gia tìm kiếm bất động sản. "
            "Evidence chứa danh sách listing với giá/m², diện tích, vị trí, "
            "và so sánh với giá trung bình khu vực.\n"
            "Hãy:\n"
            "1. Liệt kê các listing phù hợp nhất (tối đa 5-7)\n"
            "2. Với mỗi listing: nêu giá, diện tích, giá/m², so với TB khu vực\n"
            "3. Đánh giá listing nào có giá tốt nhất (thấp hơn TB khu vực)\n"
            "4. Gợi ý người dùng nên xem trực tiếp và kiểm tra pháp lý\n"
            "5. Nếu thiếu thông tin (hướng, nội thất...), hỏi lại người dùng"
        ),
        "legal_advisor": (
            "Bạn là cố vấn pháp lý bất động sản. "
            "Evidence chứa các điều khoản pháp luật kèm citation (Chương/Điều/Khoản) "
            "và ngày ban hành.\n"
            "Hãy:\n"
            "1. Trả lời câu hỏi dựa trên điều khoản cụ thể, trích dẫn rõ Điều mấy\n"
            "2. Giải thích bằng ngôn ngữ dễ hiểu, tránh thuật ngữ pháp lý phức tạp\n"
            "3. Nếu văn bản đã cũ, cảnh báo có thể đã có sửa đổi\n"
            "4. LUÔN kèm disclaimer: 'Không thay thế tư vấn luật sư chuyên nghiệp'\n"
            "5. Nếu câu hỏi ngoài phạm vi BĐS → từ chối lịch sự"
        ),
        "investment_advisor": (
            "Bạn là cố vấn đầu tư bất động sản. "
            "Evidence chứa: listing với giá/m², điểm hấp dẫn đầu tư (1-10), "
            "xu hướng giá, và đánh giá rủi ro.\n"
            "Hãy:\n"
            "1. Phân tích cơ hội đầu tư dựa trên điểm attractiveness score\n"
            "2. So sánh các listing về tiềm năng tăng giá\n"
            "3. Nêu rõ các rủi ro (thanh khoản, pháp lý, thị trường)\n"
            "4. Hỏi người dùng về khẩu vị rủi ro, thời gian đầu tư, ngân sách\n"
            "5. LUÔN kèm disclaimer: 'Đây KHÔNG phải lời khuyên tài chính. "
            "Cần tự thẩm định trước khi quyết định đầu tư.'"
        ),
        "project_agent": (
            "Bạn là chuyên gia đánh giá dự án bất động sản. "
            "Evidence chứa thông tin dự án: tên, chủ đầu tư, vị trí, quy mô, tiến độ.\n"
            "Hãy:\n"
            "1. Tóm tắt thông tin chính của dự án\n"
            "2. Đánh giá uy tín chủ đầu tư (nếu có thông tin)\n"
            "3. Nêu tiến độ và pháp lý dự án\n"
            "4. Cảnh báo nếu thiếu thông tin quan trọng"
        ),
        "news_agent": (
            "Bạn là chuyên gia phân tích tin tức bất động sản. "
            "Evidence chứa các bài báo về thị trường, chính sách, dự án.\n"
            "Hãy:\n"
            "1. Tóm tắt tin tức liên quan đến câu hỏi\n"
            "2. Phân tích tác động đến thị trường BĐS (tích cực/tiêu cực)\n"
            "3. Nếu có nhiều tin, nhóm theo chủ đề\n"
            "4. Dẫn nguồn bài viết gốc khi có URL"
        ),
    }

    barrier = domain_barriers.get(agent_name, "")
    instructions = agent_instructions.get(agent_name, "")

    lines = [
        "You are a real-estate specialist agent. You MUST respond with ONLY a raw JSON object (no markdown, no code fences). Do NOT wrap the JSON in ``` or any other formatting.",
        f"Agent name: {agent_name}",
    ]
    if instructions:
        lines.append(instructions)
    if barrier:
        lines.append(barrier)
    lines.extend([
        f"User query: {query}",
        f"User preferences: {json.dumps(preferences, ensure_ascii=True)}",
        "Use only the provided evidence IDs. Do not cite or infer from unseen evidence.",
        "If evidence is insufficient, return status no_evidence or partial and explain what is missing.",
        "Required JSON fields: agent_name, status, content, claims, evidence_ids_used, confidence, warnings, missing_evidence.",
        "Each claim should include text and evidence_id when it depends on a source.",
        f"Evidence: {json.dumps(evidence_payload, ensure_ascii=True)}",
    ])
    return "\n".join(lines)


def _append_warning(result: dict[str, Any], warning: str) -> dict[str, Any]:
    updated = dict(result)
    updated["warnings"] = [*list(updated.get("warnings") or []), warning]
    return updated


def _valid_evidence_ids(evidence: list[dict[str, Any]]) -> set[str]:
    return {
        evidence_id
        for record in evidence
        if (evidence_id := _evidence_id(record)) is not None
    }


def _returns_source_backed_content(output: LLMSpecialistOutput) -> bool:
    return output.status in {"completed", "partial"} and bool(output.content.strip())


def _claim_requires_evidence(claim: Any) -> bool:
    if not isinstance(claim, dict):
        return True
    return claim.get("type") not in {"caveat", "disclaimer", "missing_evidence"}


async def run_llm_or_deterministic_specialist(
    *,
    agent_name: str,
    deterministic_runner: DeterministicRunner,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
    generate_json: GenerateJson,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    deterministic_result = await deterministic_runner(
        query=query,
        evidence=evidence,
        preferences=preferences,
        readiness=readiness,
    )

    try:
        prompt = build_specialist_prompt(
            agent_name=agent_name,
            query=query,
            evidence=evidence,
            preferences=preferences,
        )
        try:
            payload = await generate_json(prompt, timeout_seconds=timeout_seconds)
        except TypeError:
            payload = await generate_json(prompt)
        output = LLMSpecialistOutput.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        return _append_warning(deterministic_result, "llm_specialist_invalid_json")

    if output.agent_name != agent_name:
        return _append_warning(deterministic_result, "llm_specialist_invalid_json")

    allowed_ids = _valid_evidence_ids(evidence)
    if _returns_source_backed_content(output) and not allowed_ids:
        return _append_warning(deterministic_result, "llm_specialist_missing_evidence")

    if _returns_source_backed_content(output) and not output.claims:
        return _append_warning(deterministic_result, "llm_specialist_missing_claims")

    used_ids = {str(evidence_id) for evidence_id in output.evidence_ids_used}
    if _returns_source_backed_content(output) and not used_ids:
        return _append_warning(deterministic_result, "llm_specialist_missing_evidence")

    evidence_claims = [
        claim for claim in output.claims if _claim_requires_evidence(claim)
    ]
    if _returns_source_backed_content(output) and not evidence_claims:
        return _append_warning(
            deterministic_result,
            "llm_specialist_missing_evidence_claims",
        )

    if not used_ids.issubset(allowed_ids):
        return _append_warning(deterministic_result, "llm_specialist_invalid_evidence")

    result = output.model_dump(mode="python")
    result["fallback_content"] = deterministic_result.get("content", "")
    return result
