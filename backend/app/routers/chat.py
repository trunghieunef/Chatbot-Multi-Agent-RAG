"""
Chat API router.

REST endpoint for chatbot interaction. WebSocket support will be added in Phase 3.
"""

import logging
import asyncio
import random
import uuid
from datetime import datetime
from inspect import isawaitable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session, get_db
from app.models.agent_observability import EvalRun, EvalScore
from app.models.chat import ChatMessage, ChatSession
from app.models.preference import ChatFeedback, MemoryProposal
from app.models.user import User
from app.routers.auth import get_optional_user
from app.routers.metrics import CHAT_REQUESTS
from app.schemas.chat import (
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionResponse,
)
from app.services.agent_service.client import (
    AgentServiceError,
    get_agent_service_client,
)
from app.services.agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
    TraceSummary,
)
from app.services.agent_service.observability import (
    persist_agent_observability as _persist_agent_observability,
)
from app.services.chatbot import run_chat_pipeline
from app.services.chatbot.context import (
    build_conversation_context,
    load_user_preferences,
    split_agents,
)
from app.services.chatbot.memory import (
    decide_memory_status,
    mark_memory_proposal_resolved,
    upsert_user_preference,
)
from app.services.chatbot.abuse_guard import (
    ChatAbuseGuard,
    enforce_chat_abuse_guard,
)
from app.services.chatbot.quota import enforce_chat_quota
from app.services.chatbot.session_guard import verify_session_ownership

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)

_anon_abuse_guard = ChatAbuseGuard(
    max_requests=get_settings().CHAT_ABUSE_GUARD_ANON_MAX_REQUESTS,
    window_seconds=get_settings().CHAT_ABUSE_GUARD_ANON_WINDOW_SECONDS,
)
_auth_abuse_guard = ChatAbuseGuard(
    max_requests=get_settings().CHAT_ABUSE_GUARD_AUTH_MAX_REQUESTS,
    window_seconds=get_settings().CHAT_ABUSE_GUARD_AUTH_WINDOW_SECONDS,
)


def is_agent_service_enabled() -> bool:
    return get_settings().CHATBOT_AGENT_SERVICE_ENABLED


def should_schedule_eval(
    *,
    enabled: bool,
    sample_rate: float,
    answer: str,
    mode: str | None,
) -> bool:
    if not enabled or not answer.strip():
        return False
    if mode in {"agent_service_error", "legacy_pipeline", "legacy"}:
        return False
    if sample_rate <= 0:
        return False
    if sample_rate >= 1:
        return True
    return random.random() < sample_rate


def _chat_abuse_key(body: ChatMessageRequest, user: User | None, request: Request) -> str:
    if user is not None:
        return f"auth:{user.id}"
    client_host = request.client.host if request.client else "unknown"
    return f"anon:ip:{client_host}"


def _enforce_chat_abuse_guard(
    body: ChatMessageRequest,
    user: User | None,
    request: Request,
    response: Response,
) -> None:
    settings = get_settings()
    guard = _auth_abuse_guard if user is not None else _anon_abuse_guard
    enforce_chat_abuse_guard(
        guard,
        key=_chat_abuse_key(body, user, request),
        enabled=settings.CHAT_ABUSE_GUARD_ENABLED,
        response=response,
    )


async def _run_chatbot_pipeline(
    message: str,
    db: AsyncSession,
    session_id: uuid.UUID,
) -> dict:
    """Run production multi-agent chat."""
    try:
        return await run_chat_pipeline(message, db, session_id=str(session_id))
    except Exception as exc:
        return {
            "final_response": (
                "Chatbot chua san sang do pipeline multi-agent gap loi. "
                f"Chi tiet: {exc}"
            ),
            "agent_used": "multi_agent_error",
            "sources": [],
            "suggested_actions": [
                "Kiem tra backend logs",
                "Kiem tra du lieu da ingest",
                "Thu lai sau",
            ],
        }


def _legacy_response_to_agent_shape(
    request_id: str,
    result: dict,
) -> AgentChatResponse:
    agents_used = split_agents(result.get("agent_used")) or ["unknown"]
    sources = [
        source
        for source in result.get("sources", [])
        if isinstance(source, dict) and source.get("type")
    ]
    return AgentChatResponse(
        request_id=request_id,
        final_response=result.get("final_response") or "Toi chua tao duoc cau tra loi phu hop.",
        agents_used=agents_used,
        sources=sources,
        suggested_actions=result.get("suggested_actions", []),
        trace_summary=TraceSummary(
            intent="legacy",
            agents=agents_used,
            source_count=len(result.get("sources", [])),
            latency_ms=0,
            warnings=["legacy_pipeline"],
        ),
        full_trace={"mode": "legacy", "raw_sources": result.get("sources", [])},
    )


async def _resolve(value):
    if isawaitable(value):
        return await value
    return value


async def _run_agent_service_pipeline(
    message: str,
    db: AsyncSession,
    session: ChatSession,
    user: User | None,
    request_id: str,
) -> AgentChatResponse:
    if not is_agent_service_enabled():
        legacy_result = await _run_chatbot_pipeline(message, db, session.id)
        return _legacy_response_to_agent_shape(request_id, legacy_result)

    settings = get_settings()
    user_id = user.id if user else None
    request = AgentChatRequest(
        request_id=request_id,
        message=message,
        session_id=str(session.id),
        user_id=user_id,
        is_authenticated=user is not None,
        conversation_context=await _resolve(build_conversation_context(db, session.id)),
        user_preferences=await _resolve(load_user_preferences(db, user_id)),
        requested_trace_level=settings.CHATBOT_TRACE_LEVEL,
    )
    try:
        return await get_agent_service_client().chat(request)
    except AgentServiceError as exc:
        return AgentChatResponse(
            request_id=request_id,
            final_response=(
                "Agent Service chua san sang. Vui long thu lai sau hoac dung pipeline du phong."
            ),
            agents_used=["agent_service_error"],
            suggested_actions=[
                "Thu lai sau",
                "Kiem tra backend logs",
            ],
            trace_summary=TraceSummary(
                intent="agent_service_error",
                agents=["agent_service_error"],
                latency_ms=0,
                warnings=[str(exc)],
            ),
            full_trace={"mode": "agent_service_error"},
            readiness={},
        )


def _source_dicts(response: AgentChatResponse) -> list[dict]:
    if response.full_trace.get("mode") == "legacy":
        return response.full_trace.get("raw_sources", [])
    return [source.model_dump(mode="json") for source in response.sources]


def _trace_summary_dict(response: AgentChatResponse) -> dict:
    return response.trace_summary.model_dump(mode="json")


async def persist_agent_observability(
    session_factory,
    chat_session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> None:
    await _persist_agent_observability(
        session_factory=session_factory,
        chat_session=chat_session,
        user=user,
        response=response,
    )


async def _commit_if_supported(db: AsyncSession) -> None:
    commit = getattr(db, "commit", None)
    if commit is not None:
        await commit()


def _memory_proposal_hint(record: MemoryProposal) -> dict:
    return {
        "id": record.id,
        "request_id": record.request_id,
        "action": record.action,
        "key": record.key,
        "value_json": record.value_json,
        "confidence": record.confidence,
        "evidence": record.evidence,
        "requires_user_confirmation": record.requires_user_confirmation,
        "status": record.status,
    }


async def handle_memory_proposals(
    db: AsyncSession,
    session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> list[dict]:
    if user is None:
        return []

    hints = []
    for proposal in response.memory_proposals:
        status = decide_memory_status(proposal)
        record = MemoryProposal(
            user_id=user.id,
            session_id=session.id,
            request_id=response.request_id,
            action=proposal.action,
            key=proposal.key,
            value_json={"value": proposal.value},
            confidence=proposal.confidence,
            evidence=proposal.evidence,
            requires_user_confirmation=proposal.requires_user_confirmation,
            status=status,
        )
        db.add(record)
        if status == "pending":
            await db.flush()
            hints.append(_memory_proposal_hint(record))
        if status == "auto_applied":
            mark_memory_proposal_resolved(record, status="auto_applied")
            await upsert_user_preference(
                db,
                user_id=user.id,
                key=proposal.key,
                value_json={"value": proposal.value},
                confidence=proposal.confidence,
                source="agent_proposal",
            )
    return hints


def _trace_value(full_trace: dict, key: str, default: str) -> str:
    value = full_trace.get(key)
    if value is None or str(value).strip() == "":
        return default
    return str(value)


def _score_value(metric: str, value) -> tuple[float, str]:
    if isinstance(value, dict):
        raw_score = value.get("score", 0.0)
        rationale = value.get("rationale") or value.get("reason") or ""
    else:
        raw_score = value
        rationale = ""
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = 0.0
    return score, str(rationale)


def _eval_payload(
    *,
    question: str,
    answer: str,
    sources: list[dict],
    response: AgentChatResponse,
    graph_version: str,
    prompt_version: str,
    model_name: str,
) -> dict:
    return {
        "question": question,
        "answer": answer,
        "sources": sources,
        "trace": response.full_trace if isinstance(response.full_trace, dict) else {},
        "graph_version": graph_version,
        "prompt_version": prompt_version,
        "model_name": model_name,
    }


async def _process_eval_run(
    *,
    session_factory,
    eval_run_id: int,
    payload: dict,
) -> None:
    try:
        async with session_factory() as db:
            result = await db.execute(select(EvalRun).where(EvalRun.id == eval_run_id))
            eval_run = result.scalar_one_or_none()
            if eval_run is None:
                return
            try:
                evaluation = await get_agent_service_client().evaluate(payload)
                status = str(evaluation.get("status") or "completed")
                eval_run.status = status if status in {"completed", "skipped"} else "completed"
                eval_run.summary_json = evaluation.get("summary") or {}
                eval_run.error_message = None
                eval_run.completed_at = datetime.utcnow()
                if eval_run.status == "completed":
                    scores = evaluation.get("scores") or {}
                    if isinstance(scores, dict):
                        for metric, value in scores.items():
                            score, rationale = _score_value(str(metric), value)
                            db.add(
                                EvalScore(
                                    eval_run_id=eval_run.id,
                                    metric=str(metric),
                                    score=score,
                                    rationale=rationale,
                                )
                            )
            except Exception as exc:
                logger.exception("Agent evaluation failed for eval_run_id=%s", eval_run_id)
                eval_run.status = "failed"
                eval_run.error_message = exc.__class__.__name__
                eval_run.completed_at = datetime.utcnow()
            await db.commit()
    except Exception:
        logger.exception("Agent evaluation task failed for eval_run_id=%s", eval_run_id)


async def schedule_agent_evaluation(
    *,
    session_factory,
    chat_session: ChatSession,
    question: str,
    sources: list[dict],
    response: AgentChatResponse,
    sync_for_tests: bool,
) -> None:
    full_trace = response.full_trace if isinstance(response.full_trace, dict) else {}
    graph_version = _trace_value(full_trace, "graph_version", "unknown_graph")
    prompt_version = _trace_value(full_trace, "prompt_version", "unknown_prompt")
    model_name = _trace_value(full_trace, "model_name", "unknown_model")
    payload = _eval_payload(
        question=question,
        answer=response.final_response,
        sources=sources,
        response=response,
        graph_version=graph_version,
        prompt_version=prompt_version,
        model_name=model_name,
    )

    async with session_factory() as db:
        eval_run = EvalRun(
            request_id=response.request_id,
            session_id=chat_session.id,
            status="pending",
            evaluator="gemini",
            graph_version=graph_version,
            prompt_version=prompt_version,
            model_name=model_name,
            summary_json={},
        )
        db.add(eval_run)
        await db.flush()
        eval_run_id = eval_run.id
        await db.commit()

    if sync_for_tests:
        await _process_eval_run(
            session_factory=session_factory,
            eval_run_id=eval_run_id,
            payload=payload,
        )
    else:
        asyncio.create_task(
            _process_eval_run(
                session_factory=session_factory,
                eval_run_id=eval_run_id,
                payload=payload,
            )
        )


@router.post("/feedback", response_model=ChatFeedbackResponse)
async def submit_feedback(
    body: ChatFeedbackRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Store feedback for a chat response."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == body.session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id is not None and (user is None or session.user_id != user.id):
        raise HTTPException(status_code=404, detail="Session not found")

    feedback = ChatFeedback(
        user_id=user.id if user else None,
        session_id=body.session_id,
        request_id=body.request_id,
        rating=body.rating,
        issue_type=body.issue_type,
        comment=body.comment,
        metadata_json=body.metadata_json or {},
    )
    db.add(feedback)
    await db.flush()
    return ChatFeedbackResponse(id=feedback.id)


@router.post("", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    request: Request = None,
    response: Response = None,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to the chatbot and get a response.

    If session_id is not provided, a new session is created.
    The RAG multi-agent pipeline will process the message (Phase 3).
    """
    request_id = str(uuid.uuid4())
    request = request or Request({"type": "http", "client": ("direct-test", 0)})
    response = response or Response()
    _enforce_chat_abuse_guard(body, user, request, response)

    # Get or create session
    if body.session_id:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == body.session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        verify_session_ownership(session, user)
    else:
        session = ChatSession(
            user_id=user.id if user else None,
            title=body.message[:80],
        )
        db.add(session)
        await db.flush()

    await enforce_chat_quota(db, user=user, session_id=session.id)

    agent_response = await _run_agent_service_pipeline(
        body.message,
        db,
        session,
        user,
        request_id,
    )

    # Save user message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    response_text = agent_response.final_response
    agents_used = agent_response.agents_used
    agent_used = ", ".join(agents_used) if agents_used else "unknown"
    sources = _source_dicts(agent_response)
    suggested_actions = agent_response.suggested_actions
    trace_summary = _trace_summary_dict(agent_response)
    memory_hints = await handle_memory_proposals(db, session, user, agent_response)

    # Save assistant response
    CHAT_REQUESTS.labels(agent=agent_used or "unknown").inc()
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=response_text,
        agent_used=agent_used,
        metadata_json={
            "request_id": request_id,
            "sources": sources,
            "suggested_actions": suggested_actions,
            "trace_summary": trace_summary,
            "agents_used": agents_used,
            "memory_hints": memory_hints,
        },
    )
    db.add(assistant_msg)
    await db.flush()
    await _commit_if_supported(db)

    try:
        await _resolve(
            persist_agent_observability(
                async_session,
                session,
                user,
                agent_response,
            )
        )
    except Exception:
        logger.exception(
            "Failed to persist agent observability for request_id=%s",
            agent_response.request_id,
        )

    settings = get_settings()
    full_trace = agent_response.full_trace if isinstance(agent_response.full_trace, dict) else {}
    if should_schedule_eval(
        enabled=settings.CHATBOT_EVAL_ENABLED,
        sample_rate=settings.CHATBOT_EVAL_SAMPLE_RATE,
        answer=response_text,
        mode=full_trace.get("mode"),
    ):
        try:
            await schedule_agent_evaluation(
                session_factory=async_session,
                chat_session=session,
                question=body.message,
                sources=sources,
                response=agent_response,
                sync_for_tests=settings.CHATBOT_EVAL_SYNC_FOR_TESTS,
            )
        except Exception:
            logger.exception(
                "Failed to schedule agent evaluation for request_id=%s",
                agent_response.request_id,
            )

    return ChatMessageResponse(
        session_id=session.id,
        role="assistant",
        content=response_text,
        agent_used=agent_used,
        agents_used=agents_used,
        sources=sources,
        suggested_actions=suggested_actions,
        trace_summary=trace_summary,
        memory_hints=memory_hints,
        request_id=request_id,
        created_at=assistant_msg.created_at,
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def get_sessions(
    user: User = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all chat sessions for the current user."""
    query = select(ChatSession).order_by(ChatSession.updated_at.desc())
    if user:
        query = query.where(ChatSession.user_id == user.id)
    else:
        # Anonymous: return empty
        return []

    result = await db.execute(query)
    sessions = result.scalars().all()

    response = []
    for s in sessions:
        # Count messages
        count_q = await db.execute(
            select(func.count()).select_from(ChatMessage)
            .where(ChatMessage.session_id == s.id)
        )
        msg_count = count_q.scalar() or 0
        resp = ChatSessionResponse.model_validate(s)
        resp.message_count = msg_count
        response.append(resp)

    return response


@router.get("/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(
    session_id: uuid.UUID,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full chat history for a session."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    verify_session_ownership(session, user)

    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = msg_result.scalars().all()

    return ChatHistoryResponse(
        session=ChatSessionResponse(
            id=session.id,
            title=session.title,
            message_count=len(messages),
            created_at=session.created_at,
            updated_at=session.updated_at,
        ),
        messages=[
            ChatMessageResponse(
                session_id=session.id,
                role=m.role,
                content=m.content,
                agent_used=m.agent_used,
                agents_used=(
                    (m.metadata_json or {}).get("agents_used")
                    or split_agents(m.agent_used)
                ),
                sources=(m.metadata_json or {}).get("sources", []),
                suggested_actions=(m.metadata_json or {}).get("suggested_actions", []),
                trace_summary=(m.metadata_json or {}).get("trace_summary"),
                memory_hints=(m.metadata_json or {}).get("memory_hints"),
                request_id=(m.metadata_json or {}).get("request_id"),
                created_at=m.created_at,
            )
            for m in messages
        ],
    )
