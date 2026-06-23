from __future__ import annotations

import logging
from typing import Any

from agent_service.agents.orchestrator import AGENT_CLASSES
from agent_service.agents.base import BaseAgent
from agent_service.config import AgentSettings
from agent_service.contracts import AgentAction, AgentContext, AgentResult
from agent_service.llm.function_schema import function_declarations_for
from agent_service.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _deterministic_actions_from_steps(steps: list[Any]) -> list[AgentAction]:
    """Wrap tool-loop steps as AgentActions so build_result can format them."""
    actions: list[AgentAction] = []
    for i, step in enumerate(steps):
        result = step.result if isinstance(step.result, dict) else {}
        evidence = result.get("evidence_ids", [])
        actions.append(AgentAction(
            iteration=i,
            action_type="call_tool",
            status="success" if result.get("status") == "success" else "error",
            tool_result=result,
            evidence_ids=evidence if isinstance(evidence, list) else [],
        ))
    return actions


async def _run_deterministic(agent: BaseAgent, context: AgentContext,
                             registry: ToolRegistry) -> AgentResult:
    """Fallback: run the agent's existing deterministic ReAct loop."""
    return await agent.run(
        context, state={"agent_blackboard": {"entries": []}},
        tool_registry=registry, llm_client=None,
        timeout_seconds=30.0,
    )


async def run_specialist(
    *,
    agent_name: str,
    context: AgentContext,
    registry: ToolRegistry,
    llm_client: Any | None,
    settings: AgentSettings,
) -> AgentResult:
    agent_cls = AGENT_CLASSES.get(agent_name)
    if agent_cls is None:
        return AgentResult(agent_name=agent_name, status="failed",
                           content=f"Unknown agent: {agent_name}")
    agent = agent_cls(max_iterations=settings.AGENT_MAX_ITERATIONS, use_llm=bool(llm_client))

    use_llm = bool(llm_client) and settings.AGENT_SPECIALIST_LLM_ENABLED
    if not use_llm:
        return await _run_deterministic(agent, context, registry)

    tool_defs = registry.list_for_agent(agent_name)
    declarations = function_declarations_for(tool_defs)

    async def executor(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await registry.call(tool_name=tool_name, agent_name=agent_name, **args)

    system_prompt = BaseAgent._role_description(agent_name)
    user_message = (
        f"Truy vấn người dùng: {context.query}\n"
        f"Bộ lọc: {context.routing_filters}\n"
        "Hãy dùng công cụ để lấy dữ liệu rồi đưa ra phân tích ngắn gọn bằng tiếng Việt. "
        "KHÔNG bịa thông tin không có trong kết quả công cụ."
    )

    try:
        loop = await llm_client.run_tool_loop(
            system_prompt=system_prompt,
            user_message=user_message,
            function_declarations=declarations,
            executor=executor,
            max_iterations=settings.AGENT_MAX_ITERATIONS,
            timeout_seconds=settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("[%s] FC loop failed (%s); deterministic fallback", agent_name, exc)
        return await _run_deterministic(agent, context, registry)

    if loop.skipped_reason or not loop.steps:
        # No tool evidence gathered → use deterministic path to guarantee retrieval.
        return await _run_deterministic(agent, context, registry)

    actions = _deterministic_actions_from_steps(loop.steps)
    base_result = agent.build_result(context, thoughts=[], actions=actions)

    # Prefer LLM analysis text for content; keep structured sources/evidence.
    content = loop.text.strip() or base_result.content
    return base_result.model_copy(update={"content": content, "iterations": loop.iterations})
