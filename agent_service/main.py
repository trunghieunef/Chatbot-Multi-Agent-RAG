from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.responses import StreamingResponse

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest, AgentChatResponse
from agent_service.evaluation.judge import judge_answer
from agent_service.graph.agentic_workflow import run_agentic_graph, run_agentic_graph_stream
from agent_service.llm.cost import get_runtime_cost_summary
from agent_service.security import require_internal_key
from agent_service.tools.readiness import build_readiness_snapshot


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
        "llm_cost": get_runtime_cost_summary(settings),
    }


@app.get("/internal/agent/readiness")
async def readiness(_: None = Depends(require_internal_key)) -> dict:
    sources = await build_readiness_snapshot()
    status = "ok" if any(
        source.get("status") == "ready" for source in sources.values()
    ) else "degraded"
    return {"status": status, "sources": sources}

@app.post("/internal/agent/chat", response_model=AgentChatResponse)
async def chat(
    body: AgentChatRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_internal_key),
) -> AgentChatResponse:
    """Agentic RAG endpoint — autonomous agents with ReAct loops + LangGraph checkpoint."""
    del background_tasks
    return await run_agentic_graph(body)


@app.post("/internal/agent/chat/stream")
async def chat_stream(
    body: AgentChatRequest,
    _: None = Depends(require_internal_key),
):
    """Agentic RAG streaming endpoint — SSE events per graph node.

    Events:
        node_start: {"event":"node_start","node":"route","status":"đang phân tích..."}
        node_complete: {"event":"node_complete","node":"route","duration_ms":12.5}
        final: {"event":"final","request_id":"...","payload":AgentChatResponse}
    """
    import json

    async def event_generator():
        async for event in run_agentic_graph_stream(body):
            event_name = event.get("event", "message")
            yield f"event: {event_name}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/internal/agent/evaluate")
async def evaluate(body: dict, _: None = Depends(require_internal_key)) -> dict:
    settings = get_agent_settings()
    return await judge_answer(
        question=body.get("question", ""),
        answer=body.get("answer", ""),
        sources=body.get("sources", []),
        trace=body.get("trace", {}),
        graph_version=body.get("graph_version") or settings.AGENT_GRAPH_VERSION,
        prompt_version=body.get("prompt_version") or settings.AGENT_PROMPT_VERSION,
        model_name=body.get("model_name") or settings.GEMINI_JUDGE_MODEL,
    )


