from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage
from app.models.preference import UserPreference
from app.services.agent_service.contracts import AgentSource, ConversationContextItem


def split_agents(agent_used: str | None) -> list[str]:
    if not agent_used:
        return []
    return [agent.strip() for agent in agent_used.split(",") if agent.strip()]


async def build_conversation_context(
    db: AsyncSession,
    session_id,
    limit: int = 6,
) -> list[ConversationContextItem]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    context: list[ConversationContextItem] = []
    for message in messages:
        sources = []
        metadata = message.metadata_json or {}
        for source in metadata.get("sources", []):
            if isinstance(source, dict) and source.get("type"):
                sources.append(AgentSource.model_validate(source))

        created_at = (
            message.created_at.isoformat()
            if getattr(message, "created_at", None)
            else None
        )
        context.append(
            ConversationContextItem(
                role=message.role,
                content=message.content,
                created_at=created_at,
                sources=sources,
            )
        )
    return context


async def load_user_preferences(db: AsyncSession, user_id: int | None) -> dict:
    if user_id is None:
        return {}

    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    )
    return {pref.key: pref.value_json for pref in result.scalars().all()}
