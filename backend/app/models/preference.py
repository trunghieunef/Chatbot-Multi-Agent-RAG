from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    value_json = Column(JSONB, nullable=False, default={})
    confidence = Column(Float, nullable=False, default=1.0)
    source = Column(String(50), nullable=False, default="user")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class MemoryProposal(Base):
    __tablename__ = "memory_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    request_id = Column(String(80), nullable=False, index=True)
    action = Column(String(30), nullable=False)
    key = Column(String(100), nullable=False, index=True)
    value_json = Column(JSONB, nullable=False, default={})
    confidence = Column(Float, nullable=False)
    evidence = Column(Text, nullable=False)
    requires_user_confirmation = Column(Boolean, nullable=False, default=True)
    status = Column(String(30), nullable=False, default="pending")
    created_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime, nullable=True)


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    request_id = Column(String(80), nullable=False, index=True)
    rating = Column(String(20), nullable=False)
    issue_type = Column(String(80), nullable=True)
    comment = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime, default=func.now())
