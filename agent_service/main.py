from fastapi import BackgroundTasks, Depends, FastAPI

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest, AgentChatResponse, TraceSummary
from agent_service.security import require_internal_key


settings = get_agent_settings()

app = FastAPI(
    title="Real Estate Agent Service",
    version="0.1.0",
    description="Internal LangGraph multi-agent RAG service",
)


@app.get("/internal/agent/health")
async def health(_: None = Depends(require_internal_key)) -> dict:
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "graph_version": settings.AGENT_GRAPH_VERSION,
    }


@app.get("/internal/agent/readiness")
async def readiness(_: None = Depends(require_internal_key)) -> dict:
    return {"status": "ok", "sources": {}}


@app.post("/internal/agent/chat", response_model=AgentChatResponse)
async def chat(
    body: AgentChatRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_internal_key),
) -> AgentChatResponse:
    del background_tasks
    return AgentChatResponse(
        request_id=body.request_id,
        final_response="Agent Service is reachable. LangGraph workflow is not wired yet.",
        agents_used=[],
        trace_summary=TraceSummary(
            intent="bootstrap",
            agents=[],
            source_count=0,
            latency_ms=0.0,
            warnings=["graph_not_wired"],
        ),
        full_trace={"request_id": body.request_id, "status": "bootstrap"},
        readiness={"status": "bootstrap"},
    )
