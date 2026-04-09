"""
SQLAlchemy ORM models for chat sessions and messages.
"""

import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ChatSession(Base):
    """A chat conversation session."""

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable = anonymous chat
    title = Column(String(300))  # Auto-generated from first message

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    messages = relationship("ChatMessage", back_populates="session", order_by="ChatMessage.created_at")

    def __repr__(self):
        return f"<ChatSession(id='{self.id}')>"


class ChatMessage(Base):
    """A single message in a chat session."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False, index=True)

    role = Column(String(15), nullable=False)    # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)

    # Agent tracing
    agent_used = Column(String(50))              # Which agent(s) handled this
    metadata_json = Column(JSONB, default={})    # Sources, citations, search context

    # Timestamps
    created_at = Column(DateTime, default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role='{self.role}', session='{self.session_id}')>"
