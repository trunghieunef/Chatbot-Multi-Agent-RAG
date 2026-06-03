"""
Chat API router.

REST endpoint for chatbot interaction. WebSocket support will be added in Phase 3.
"""

import uuid
from inspect import isawaitable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.agent_observability import AgentTrace
from app.models.chat import ChatMessage, ChatSession
from app.models.preference import MemoryProposal
from app.models.user import User
from app.routers.auth import get_optional_user
from app.routers.metrics import CHAT_REQUESTS
from app.schemas.chat import (
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
from app.services.chatbot import run_chat_pipeline
from app.services.chatbot.context import (
    build_conversation_context,
    load_user_preferences,
    split_agents,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


def is_agent_service_enabled() -> bool:
    return get_settings().CHATBOT_AGENT_SERVICE_ENABLED


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
        final_response=result["final_response"],
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


def persist_agent_observability(
    db: AsyncSession,
    session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> None:
    db.add(
        AgentTrace(
            request_id=response.request_id,
            session_id=session.id,
            user_id=user.id if user else None,
            intent=response.trace_summary.intent,
            agents_used=response.agents_used,
            trace_summary_json=_trace_summary_dict(response),
            full_trace_json=response.full_trace,
            readiness_json=response.readiness,
            latency_ms=response.trace_summary.latency_ms,
            status="success",
        )
    )


def handle_memory_proposals(
    db: AsyncSession,
    session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> list[dict]:
    if user is None:
        return []

    hints = []
    for proposal in response.memory_proposals:
        status = "pending" if proposal.requires_user_confirmation else "auto_applied"
        db.add(
            MemoryProposal(
                user_id=user.id,
                session_id=session.id,
                request_id=response.request_id,
                action=proposal.action,
                key=proposal.key,
                value_json=proposal.value,
                confidence=proposal.confidence,
                evidence=proposal.evidence,
                requires_user_confirmation=proposal.requires_user_confirmation,
                status=status,
            )
        )
        if proposal.requires_user_confirmation:
            hints.append(proposal.model_dump(mode="json"))
    return hints


@router.post("", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to the chatbot and get a response.

    If session_id is not provided, a new session is created.
    The RAG multi-agent pipeline will process the message (Phase 3).
    """
    request_id = str(uuid.uuid4())

    # Get or create session
    if body.session_id:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == body.session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = ChatSession(
            user_id=user.id if user else None,
            title=body.message[:80],
        )
        db.add(session)
        await db.flush()

    # Save user message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)

    agent_response = await _run_agent_service_pipeline(
        body.message,
        db,
        session,
        user,
        request_id,
    )
    response_text = agent_response.final_response
    agents_used = agent_response.agents_used
    agent_used = ", ".join(agents_used) if agents_used else "unknown"
    sources = _source_dicts(agent_response)
    suggested_actions = agent_response.suggested_actions
    trace_summary = _trace_summary_dict(agent_response)
    persist_agent_observability(db, session, user, agent_response)
    memory_hints = handle_memory_proposals(db, session, user, agent_response)

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
    db: AsyncSession = Depends(get_db),
):
    """Get full chat history for a session."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
