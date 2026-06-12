from typing import Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_observability import (
    AgentRetrievalEvent,
    AgentTrace,
    AgentTraceStep,
    EvalRun,
)
from app.models.chat import ChatMessage, ChatSession
from app.models.preference import ChatFeedback, MemoryProposal
from app.models.source_readiness import SourceReadiness
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.admin import (
    AgentTraceDetail,
    AgentTraceListItem,
    AgentTraceSearchResponse,
)
from app.services.agent_service.client import (
    AgentServiceError,
    get_agent_service_client,
)


router = APIRouter(prefix="/admin", tags=["Admin"])


def require_admin_user(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def serialize_model_public_columns(model: Any) -> dict[str, Any]:
    return {
        column.name: getattr(model, column.name)
        for column in model.__table__.columns
    }


def _serialize_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [serialize_model_public_columns(row) for row in rows]


@router.get("/chat-traces", response_model=list[AgentTraceListItem])
async def list_chat_traces(
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentTrace)
        .order_by(AgentTrace.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/chat-traces/search", response_model=AgentTraceSearchResponse)
async def search_chat_traces(
    q: str | None = None,
    status: str | None = None,
    intent: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentTrace)
    if status:
        query = query.where(AgentTrace.status == status)
    if intent:
        query = query.where(AgentTrace.intent == intent)
    if q:
        query = query.where(AgentTrace.request_id.ilike(f"%{q}%"))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(AgentTrace.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return {"items": rows, "total": total}


@router.get("/chat-traces/{request_id}", response_model=AgentTraceDetail)
async def get_chat_trace(
    request_id: str,
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentTrace).where(AgentTrace.request_id == request_id)
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status_code=404, detail="Agent trace not found")
    steps = (
        await db.execute(
            select(AgentTraceStep)
            .where(AgentTraceStep.request_id == request_id)
            .order_by(AgentTraceStep.id)
        )
    ).scalars().all()
    retrieval_events = (
        await db.execute(
            select(AgentRetrievalEvent)
            .where(AgentRetrievalEvent.request_id == request_id)
            .order_by(AgentRetrievalEvent.id)
        )
    ).scalars().all()
    eval_runs = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.request_id == request_id)
            .order_by(EvalRun.created_at.desc())
        )
    ).scalars().all()

    payload = serialize_model_public_columns(trace)
    payload["steps"] = _serialize_rows(steps)
    payload["retrieval_events"] = _serialize_rows(retrieval_events)
    payload["eval_runs"] = _serialize_rows(eval_runs)
    return payload


@router.get("/pipeline-readiness")
async def pipeline_readiness(
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceReadiness).order_by(SourceReadiness.source_name)
    )
    return _serialize_rows(result.scalars().all())


@router.get("/eval-runs")
async def eval_runs(
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EvalRun)
        .order_by(EvalRun.created_at.desc())
        .limit(limit)
    )
    return _serialize_rows(result.scalars().all())


@router.get("/agent-health")
async def agent_health(
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            AgentTrace.status,
            func.count(AgentTrace.id).label("count"),
            func.avg(AgentTrace.latency_ms).label("avg_latency_ms"),
        )
        .group_by(AgentTrace.status)
        .order_by(AgentTrace.status)
    )
    llm_cost = {
        "tracking_available": False,
        "budget_exceeded": False,
        "estimated_cost_usd": 0.0,
    }
    try:
        agent_health_payload = await get_agent_service_client().health()
        llm_cost = agent_health_payload.get("llm_cost") or llm_cost
    except AgentServiceError:
        pass

    return {
        "items": [
            {
                "status": status,
                "count": count,
                "avg_latency_ms": float(avg_latency_ms or 0.0),
            }
            for status, count, avg_latency_ms in result.all()
        ],
        "llm_cost": llm_cost,
    }


@router.get("/top-queries")
async def top_queries(
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ChatMessage.content, func.count(ChatMessage.id).label("count"))
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.role == "user")
        .group_by(ChatMessage.content)
        .order_by(func.count(ChatMessage.id).desc())
        .limit(limit)
    )
    if since is not None:
        query = query.where(ChatMessage.created_at >= since)
    if until is not None:
        query = query.where(ChatMessage.created_at <= until)

    rows = (await db.execute(query)).all()
    return {
        "items": [
            {"query": content, "count": count}
            for content, count in rows
        ]
    }


@router.get("/feedback")
async def feedback(
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatFeedback)
        .order_by(ChatFeedback.created_at.desc())
        .limit(limit)
    )
    return _serialize_rows(result.scalars().all())


@router.get("/memory-proposals")
async def memory_proposals(
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MemoryProposal)
        .order_by(MemoryProposal.created_at.desc())
        .limit(limit)
    )
    return _serialize_rows(result.scalars().all())
