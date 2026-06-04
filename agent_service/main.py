from fastapi import BackgroundTasks, Depends, FastAPI

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest, AgentChatResponse
from agent_service.graph.workflow import run_agent_graph
from agent_service.security import require_internal_key


app = FastAPI(
    title="Real Estate Agent Service",
    version="0.1.0",
    description="Internal LangGraph multi-agent RAG service",
)


@app.get("/internal/agent/health")
async def health(_: None = Depends(require_internal_key)) -> dict:
    settings = get_agent_settings()
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
    return await run_agent_graph(body)
