"""Daily chat quota enforcement."""

from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.config import get_settings
from app.models.chat import ChatMessage, ChatSession


async def _acquire_quota_lock(db, *, user, session_id, day_start: datetime) -> None:
    if user is not None:
        subject = f"auth:{user.id}"
    elif session_id is not None:
        subject = f"anon:session:{session_id}"
    else:
        return

    lock_key = f"chat-quota:{day_start.date().isoformat()}:{subject}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": lock_key},
    )


async def enforce_chat_quota(db, *, user, session_id) -> None:
    """Raise when the current user/session has exhausted today's chat quota."""
    settings = get_settings()
    day_start = datetime.combine(datetime.now(UTC).date(), time.min)
    day_end = day_start + timedelta(days=1)
    await _acquire_quota_lock(
        db,
        user=user,
        session_id=session_id,
        day_start=day_start,
    )

    query = (
        select(func.count())
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.role == "user")
        .where(ChatMessage.created_at >= day_start)
        .where(ChatMessage.created_at < day_end)
    )

    if user is not None:
        limit = settings.AUTH_CHAT_DAILY_LIMIT
        query = query.where(ChatSession.user_id == user.id)
    else:
        if session_id is None:
            return
        limit = settings.ANON_CHAT_DAILY_LIMIT
        query = query.where(ChatSession.user_id.is_(None))
        query = query.where(ChatSession.id == session_id)

    result = await db.execute(query)
    current_count = result.scalar() or 0
    if current_count >= limit:
        raise HTTPException(
            status_code=429,
            detail="Ban da dat gioi han chat trong ngay. Vui long thu lai vao ngay mai.",
        )
