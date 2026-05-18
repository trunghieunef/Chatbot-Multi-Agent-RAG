"""Production multi-agent chatbot service."""

from app.services.chatbot.orchestrator import run_chat_pipeline

__all__ = ["run_chat_pipeline"]
