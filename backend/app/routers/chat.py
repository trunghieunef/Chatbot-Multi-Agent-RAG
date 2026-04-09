"""
Chat API router.

REST endpoint for chatbot interaction. WebSocket support will be added in Phase 3.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat import ChatSession, ChatMessage
from app.models.user import User
from app.routers.auth import get_optional_user
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatHistoryResponse,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


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
            title=body.message[:80],  # auto-title from first message
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

    # ─────────────────────────────────────────────────────────────
    # TODO (Phase 3): Replace this placeholder with RAG pipeline call
    #
    # from rag.graph import run_chat_pipeline
    # result = await run_chat_pipeline(body.message, session.id)
    # response_text = result["final_response"]
    # agent_used = result["agent_used"]
    # sources = result["sources"]
    # ─────────────────────────────────────────────────────────────

    response_text = (
        f"Cảm ơn bạn đã liên hệ! Tôi là chatbot tư vấn bất động sản. "
        f"Hiện tại hệ thống RAG đang được phát triển. "
        f"Câu hỏi của bạn: \"{body.message}\" sẽ được xử lý bởi multi-agent system trong Phase 3."
    )
    agent_used = "placeholder"

    # Save assistant response
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=response_text,
        agent_used=agent_used,
        metadata_json={"sources": [], "suggested_actions": []},
    )
    db.add(assistant_msg)
    await db.flush()

    return ChatMessageResponse(
        session_id=session.id,
        role="assistant",
        content=response_text,
        agent_used=agent_used,
        sources=[],
        suggested_actions=[
            "Tìm căn hộ theo khu vực",
            "Xem xu hướng giá",
            "Tư vấn pháp lý mua nhà",
        ],
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
                sources=m.metadata_json.get("sources", []) if m.metadata_json else [],
                created_at=m.created_at,
            )
            for m in messages
        ],
    )
