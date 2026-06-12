from fastapi import BackgroundTasks, Depends, FastAPI

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest, AgentChatResponse
from agent_service.evaluation.judge import judge_answer
from agent_service.graph.workflow import run_agent_graph
from agent_service.llm.cost import get_runtime_cost_summary
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
        "llm_cost": get_runtime_cost_summary(settings),
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
