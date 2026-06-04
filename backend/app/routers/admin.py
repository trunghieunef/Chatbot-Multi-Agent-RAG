from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_observability import AgentTrace, EvalRun
from app.models.preference import ChatFeedback, MemoryProposal
from app.models.source_readiness import SourceReadiness
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.admin import AgentTraceDetail, AgentTraceListItem


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
    return trace


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
    return {
        "items": [
            {
                "status": status,
                "count": count,
                "avg_latency_ms": float(avg_latency_ms or 0.0),
            }
            for status, count, avg_latency_ms in result.all()
        ]
    }


@router.get("/top-queries")
async def top_queries(user: User = Depends(require_admin_user)):
    return {"items": []}


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
