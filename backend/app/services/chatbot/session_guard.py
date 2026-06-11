from fastapi import HTTPException

from app.models.chat import ChatSession
from app.models.user import User


def verify_session_ownership(session: ChatSession, user: User | None) -> None:
    """Raise 404 when an authenticated session is accessed by a non-owner."""
    if session.user_id is not None and (user is None or session.user_id != user.id):
        raise HTTPException(status_code=404, detail="Session not found")
