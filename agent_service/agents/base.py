from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentThought,
    StructuredWarning,
    ToolDef,
)
from agent_service.graph.blackboard import read_blackboard

if TYPE_CHECKING:
    from agent_service.llm.gemini import GeminiClient

logger = logging.getLogger(__name__)


def _warning(code: str, message: str) -> StructuredWarning:
    return StructuredWarning(code=code, message=message)


class BaseAgent(ABC):
    """Abstract base for all autonomous specialist agents.

    Implements the ReAct (Reasoning + Acting) loop:
        think → act → observe → (repeat or stop)

    Subclasses implement:
      - think():   Decide what to do next
      - act():     Execute the decided action
      - observe(): Determine if the loop should stop
      - build_result(): Produce the final AgentResult
    """

    def __init__(
        self,
        *,
        agent_name: str,
        max_iterations: int = 3,
        use_llm: bool = False,
    ):
        self.agent_name = agent_name
        self.max_iterations = max_iterations
        self.use_llm = use_llm
        self._tool_registry: Any = None
        self._llm_client: GeminiClient | None = None

    # ── Subclass interface ──────────────────────────────────────

    @abstractmethod
    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        """Decide the next action.

        Args:
            context: Full agent context (query, filters, preferences, etc.)
            iteration: Current loop iteration (0-indexed).
            previous_actions: All actions taken so far in this run.
            blackboard_entries: Latest entries from the shared blackboard.

        Returns:
            AgentThought with action, tool_name, tool_params, etc.
        """
        ...

    @abstractmethod
    async def act(
        self,
        thought: AgentThought,
        context: AgentContext,
    ) -> AgentAction:
        """Execute the action decided by think().

        For call_tool actions, this should call self.call_tool().
        For final_answer, this should return immediately.
        """
        ...

    @abstractmethod
    async def observe(
        self,
        thought: AgentThought,
        action: AgentAction,
        context: AgentContext,
    ) -> bool:
        """Determine if the ReAct loop should stop.

        Returns:
            True if the agent has enough information to answer.
        """
        ...

    @abstractmethod
    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        """Build the final AgentResult from the completed loop."""
        ...

    # ── Shared infrastructure ────────────────────────────────────

    async def call_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Call a tool via the ToolRegistry.

        Subclasses should use this rather than calling tools directly.
        The ToolRegistry is injected at run time via run().
        """
        if self._tool_registry is None:
            raise RuntimeError(
                "ToolRegistry not set. Call agent.run() which injects it."
            )
        return await self._tool_registry.call(
            tool_name=tool_name,
            agent_name=self.agent_name,
            **tool_params,
        )

    def _read_blackboard(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return read_blackboard(state, min_confidence="low", max_entries=20)

    # ── LLM-powered thinking ─────────────────────────────────────

    @staticmethod
    def _role_description(agent_name: str) -> str:
        """Return the agent's role description in Vietnamese."""
        roles: dict[str, str] = {
            "property_search": (
                "Bạn là chuyên viên môi giới bất động sản 15 năm kinh nghiệm tại "
                "Việt Nam, đã tư vấn hàng nghìn giao dịch và hiểu rõ tâm lý người mua.\n"
                "PHONG CÁCH: nói như một người tư vấn thật — không liệt kê máy móc. Với "
                "mỗi lựa chọn, nêu điểm mạnh/điểm cần cân nhắc (vị trí, hướng, pháp lý, "
                "giá/m² so với khu vực, tiềm năng), và đưa ra GỢI Ý phù hợp nhất với nhu "
                "cầu người hỏi, giải thích LÝ DO.\n"
                "CHUYÊN MÔN: biết đọc giá/m² để đánh giá đắt/rẻ; lưu ý người mua về nhà "
                "chưa sổ, nhà vi bằng, quy hoạch treo, hẻm/mặt tiền; nhắc xem thực tế "
                "trước khi cọc.\n"
                "TRUNG THỰC: chỉ dùng dữ liệu từ công cụ. Nếu ít lựa chọn khớp, nói rõ và "
                "đề xuất nới tiêu chí (khu lân cận, tầm giá) thay vì bịa. Kết thúc bằng "
                "một câu hỏi làm rõ nhu cầu khi cần (ngân sách, mục đích ở/đầu tư, ưu tiên)."
            ),
            "market_analysis": (
                "Bạn là chuyên gia phân tích thị trường bất động sản với 15 năm theo dõi "
                "giá nhà đất Việt Nam, quen dùng dữ liệu để nhận định thay vì cảm tính.\n"
                "PHONG CÁCH: đưa ra nhận định có SỐ LIỆU dẫn chứng (giá trung bình/m², "
                "mức tăng/giảm, so sánh khu vực). Giải thích ý nghĩa con số cho người "
                "không chuyên: đắt hay rẻ so với mặt bằng, xu hướng đang lên hay chững.\n"
                "CHUYÊN MÔN: phân biệt giá chào bán vs giá giao dịch; lưu ý yếu tố ảnh "
                "hưởng (hạ tầng, quy hoạch, nguồn cung). Nếu thiếu dữ liệu cho một khu "
                "vực/thời điểm, NÓI RÕ là chưa có số liệu — tuyệt đối không suy đoán con số."
            ),
            "legal_advisor": (
                "Bạn là luật sư/chuyên viên pháp lý bất động sản am hiểu luật đất đai, "
                "nhà ở và giao dịch tại Việt Nam.\n"
                "PHẠM VI: CHỈ trả lời pháp lý bất động sản. Câu ngoài phạm vi → từ chối "
                "lịch sự và hướng về chủ đề nhà đất.\n"
                "PHONG CÁCH: giải thích quy trình/thủ tục theo bước rõ ràng (giấy tờ cần, "
                "trình tự công chứng/sang tên, thuế phí trước bạ), cảnh báo các bẫy pháp "
                "lý thường gặp (sổ chung, tranh chấp, thế chấp, vi bằng, đặt cọc rủi ro).\n"
                "TRUNG THỰC: chỉ nêu điều bạn chắc chắn hoặc có trong tài liệu; dẫn nguồn "
                "khi có. LUÔN kèm: 'Thông tin chỉ mang tính tham khảo, không thay thế tư "
                "vấn luật sư — cần kiểm tra văn bản pháp luật mới nhất.'"
            ),
            "investment_advisor": (
                "Bạn là cố vấn đầu tư bất động sản 15 năm kinh nghiệm, tư duy theo dòng "
                "tiền và rủi ro, không chạy theo tâm lý đám đông.\n"
                "PHONG CÁCH: phân tích cơ hội đầu tư có cân nhắc ĐƯỢC–MẤT. Ước tính lợi "
                "suất cho thuê (rental yield) khi đủ dữ liệu, so sánh với gửi ngân hàng; "
                "chỉ ra rủi ro (thanh khoản, pháp lý, đòn bẩy, quy hoạch) thay vì chỉ vẽ "
                "màu hồng.\n"
                "CHUYÊN MÔN: phân biệt đầu tư ở/cho thuê/lướt sóng; lưu ý chi phí ẩn (phí "
                "quản lý, thuế, lãi vay). Nếu thiếu dữ liệu để tính, nói rõ. LUÔN kèm: "
                "'Đây không phải lời khuyên tài chính; hãy tự đánh giá khả năng tài chính "
                "và tham khảo chuyên gia trước khi quyết định.'"
            ),
            "project_agent": (
                "Bạn là chuyên gia thẩm định dự án bất động sản, đánh giá dự án như một "
                "nhà đầu tư thận trọng nhìn vào chủ đầu tư và pháp lý trước khi nhìn quảng cáo.\n"
                "PHONG CÁCH: khi giới thiệu dự án, nêu chủ đầu tư (uy tín, lịch sử bàn "
                "giao), tình trạng pháp lý, tiến độ, vị trí và tiện ích — kèm điểm cần "
                "lưu ý. Cảnh báo dự án chậm tiến độ, chưa đủ pháp lý mở bán, cam kết lợi "
                "nhuận phi thực tế.\n"
                "TRUNG THỰC: chỉ dùng thông tin từ công cụ; không thổi phồng theo lời "
                "quảng cáo. Nhắc người mua kiểm tra giấy phép và hợp đồng mẫu."
            ),
            "news_agent": (
                "Bạn là biên tập viên/chuyên gia phân tích tin tức bất động sản, giỏi "
                "lọc tin quan trọng và giải thích tác động tới người mua/nhà đầu tư.\n"
                "PHONG CÁCH: tóm tắt tin ngắn gọn, rồi phân tích Ý NGHĨA — tin này ảnh "
                "hưởng giá/thanh khoản/pháp lý ra sao, người mua nên lưu ý gì. Ưu tiên "
                "nguồn đáng tin, nêu rõ nguồn.\n"
                "TRUNG THỰC: không suy diễn ngoài nội dung tin; phân biệt tin xác thực và "
                "tin đồn/quảng cáo."
            ),
        }
        return roles.get(
            agent_name,
            "Bạn là chuyên gia bất động sản Việt Nam nhiều năm kinh nghiệm. Tư vấn trung "
            "thực, có dẫn chứng, chỉ dùng dữ liệu từ công cụ và nói rõ khi thiếu dữ liệu.",
        )

    def _build_think_prompt(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
        tools: list[ToolDef],
    ) -> str:
        """Build the prompt for the LLM to decide the next action."""
        role = self._role_description(self.agent_name)

        action_history = []
        for action in previous_actions[-5:]:
            action_history.append({
                "iteration": action.iteration,
                "action_type": action.action_type,
                "status": action.status,
                "tool_name": (
                    action.tool_result.get("tool", "")
                    if action.action_type == "call_tool" else None
                ),
                "result_summary": str(action.tool_result)[:300] if action.tool_result else "",
                "error": action.error_message,
            })

        bb_summary = [
            {"author": e.get("author"), "type": e.get("type"),
             "content": str(e.get("content", ""))[:200]}
            for e in blackboard_entries[-5:]
        ]

        tool_list = [
            {"name": t.name, "description": t.description, "params": t.parameters}
            for t in tools
        ]

        lines = [
            "Bạn là một AI agent trong hệ thống tư vấn bất động sản Agentic RAG.",
            "Bạn phải trả về CHỈ MỘT JSON object (không markdown, không code fence).",
            "",
            role,
            "",
            f"### Ngữ cảnh (iteration {iteration + 1})",
            f"- Truy vấn gốc: {context.query}",
            f"- Truy vấn chuẩn hóa: {context.normalized_query}",
            f"- Bộ lọc: {json.dumps(context.routing_filters, ensure_ascii=False)}",
            f"- Sở thích người dùng: {json.dumps(context.user_preferences, ensure_ascii=False)}",
            "",
            "### Lịch sử hành động",
            json.dumps(action_history, ensure_ascii=False, indent=2) if action_history else "[]",
            "",
            "### Bảng đen (kết quả từ agent khác)",
            json.dumps(bb_summary, ensure_ascii=False, indent=2) if bb_summary else "[]",
            "",
            "### Công cụ có sẵn",
            json.dumps(tool_list, ensure_ascii=False, indent=2),
            "",
            "### Hành động tiếp theo",
            "Chọn MỘT trong các hành động sau:",
            '- "call_tool": Gọi một công cụ để lấy dữ liệu. Chọn tool_name từ danh sách trên.',
            '- "final_answer": Đã có đủ dữ liệu để trả lời. Đưa ra kết luận cuối cùng.',
            '- "ask_clarification": Cần hỏi lại người dùng để làm rõ yêu cầu.',
            "",
            "Trả về JSON với định dạng CHÍNH XÁC sau:",
            "{",
            '  "iteration": <số nguyên, iteration hiện tại>',
            '  "reasoning": "<lý do chọn hành động này, bằng tiếng Việt>",',
            '  "action": "call_tool" | "final_answer" | "ask_clarification"',
            '  "tool_name": "<tên công cụ>"  // chỉ khi action="call_tool"',
            '  "tool_params": {}  // chỉ khi action="call_tool", tham số cho công cụ',
            '  "clarifying_question": "<câu hỏi>"  // chỉ khi action="ask_clarification"',
            '  "confidence": <số thực 0.0-1.0>',
            "}",
            "",
            'QUAN TRỌNG: Nếu đã có đủ dữ liệu (xem lịch sử hành động), hãy chọn "final_answer".',
            "KHÔNG gọi tool khi đã có kết quả từ tool đó ở lần trước.",
        ]

        return "\n".join(lines)

    async def _llm_think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        """Use Gemini to decide the next action in the ReAct loop.

        Falls back to deterministic think() if LLM is unavailable or fails.
        Logs every LLM call and fallback reason for debugging.
        """
        if self._llm_client is None:
            logger.warning("[%s] iter=%d LLM_SKIP: no llm_client (use_llm=%s)", self.agent_name, iteration, self.use_llm)
            return await self.think(context, iteration, previous_actions, blackboard_entries)

        tools = (
            self._tool_registry.list_for_agent(self.agent_name)
            if self._tool_registry else []
        )
        if not tools:
            logger.warning("[%s] iter=%d LLM_SKIP: no tools available", self.agent_name, iteration)
            return await self.think(context, iteration, previous_actions, blackboard_entries)

        prompt = self._build_think_prompt(
            context, iteration, previous_actions, blackboard_entries, tools
        )

        try:
            logger.warning("[%s] iter=%d LLM_CALL: sending prompt (%d chars)", self.agent_name, iteration, len(prompt))
            raw = await self._llm_client.generate_json(
                prompt,
                timeout_seconds=15.0,
            )
            if not raw or not raw.get("action"):
                logger.warning("[%s] iter=%d LLM_EMPTY: empty or invalid response, fallback to deterministic", self.agent_name, iteration)
                return await self.think(context, iteration, previous_actions, blackboard_entries)

            thought = AgentThought(
                iteration=iteration,
                reasoning=raw.get("reasoning", "LLM decided next action."),
                action=raw.get("action", "final_answer"),
                tool_name=raw.get("tool_name"),
                tool_params=raw.get("tool_params", {}),
                clarifying_question=raw.get("clarifying_question"),
                confidence=float(raw.get("confidence", 0.5)),
            )
            logger.warning(
                "[%s] iter=%d LLM_OK: action=%s tool=%s confidence=%.2f",
                self.agent_name, iteration, thought.action, thought.tool_name, thought.confidence,
            )

            # Guard: Force tool call on first iteration if LLM tries to answer without data
            if thought.action == "final_answer" and iteration == 0 and not previous_actions and tools:
                logger.warning(
                    "[%s] iter=%d LLM_GUARD: LLM said final_answer on iter 0 with no data, using deterministic tool decision",
                    self.agent_name, iteration,
                )
                fallback_thought = await self.think(
                    context, iteration, previous_actions, blackboard_entries
                )
                if fallback_thought.action != "final_answer":
                    return fallback_thought

            return thought
        except Exception as exc:
            logger.warning("[%s] iter=%d LLM_FAIL: %s, fallback to deterministic", self.agent_name, iteration, exc)
            return await self.think(context, iteration, previous_actions, blackboard_entries)

    # ── ReAct loop ───────────────────────────────────────────────

    async def run(
        self,
        context: AgentContext,
        state: dict[str, Any],
        *,
        tool_registry: Any | None = None,
        llm_client: Any | None = None,
        timeout_seconds: float = 30.0,
    ) -> AgentResult:
        """Execute the full ReAct loop.

        Args:
            context: AgentContext with query, filters, preferences.
            state: Full graph state (for blackboard access).
            tool_registry: ToolRegistry instance for tool calling.
            llm_client: GeminiClient for LLM-powered thinking (optional).
            timeout_seconds: Max time for the entire agent run.

        Returns:
            AgentResult with content, sources, evidence_ids, etc.
        """
        self._tool_registry = tool_registry
        self._llm_client = llm_client
        logger.warning(
            "[%s] RUN_START: use_llm=%s llm_client=%s tools=%d iterations=%d",
            self.agent_name,
            self.use_llm,
            self._llm_client is not None,
            len(self._tool_registry.list_for_agent(self.agent_name)) if self._tool_registry else 0,
            self.max_iterations,
        )
        thoughts: list[AgentThought] = []
        actions: list[AgentAction] = []
        started = time.perf_counter()

        for iteration in range(self.max_iterations):
            elapsed = time.perf_counter() - started
            if elapsed > timeout_seconds:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content="Agent timed out before completing analysis.",
                    warnings=[_warning("agent_timeout", f"Timed out after {elapsed:.1f}s")],
                    iterations=iteration,
                )

            _, _, result = await self.run_one_iteration(
                context,
                state,
                thoughts=thoughts,
                actions=actions,
                iteration=iteration,
                tool_registry=tool_registry,
                llm_client=llm_client,
            )
            if result is not None:
                return result

        # Max iterations reached
        return self.build_result(context, thoughts, actions)

    async def run_one_iteration(
        self,
        context: AgentContext,
        state: dict[str, Any],
        *,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
        iteration: int,
        tool_registry: Any | None = None,
        llm_client: Any | None = None,
    ) -> tuple[AgentThought | None, AgentAction | None, AgentResult | None]:
        """Execute exactly one ReAct iteration.

        The orchestrator uses this to coordinate agents across shared
        blackboard rounds while preserving each agent's thought/action history.
        """
        if tool_registry is not None:
            self._tool_registry = tool_registry
        if llm_client is not None or self._llm_client is None:
            self._llm_client = llm_client

        try:
            blackboard_entries = self._read_blackboard(state)
            if self.use_llm and self._llm_client is not None:
                logger.warning("[%s] iter=%d THINK: using LLM", self.agent_name, iteration)
                thought = await self._llm_think(
                    context, iteration, actions, blackboard_entries
                )
            else:
                logger.warning("[%s] iter=%d THINK: using deterministic (use_llm=%s client=%s)",
                               self.agent_name, iteration, self.use_llm, self._llm_client is not None)
                thought = await self.think(
                    context, iteration, actions, blackboard_entries
                )
            thoughts.append(thought)
        except Exception as exc:
            return None, None, AgentResult(
                agent_name=self.agent_name,
                status="failed",
                content=f"Agent failed during think: {exc}",
                warnings=[_warning("think_error", str(exc))],
                iterations=iteration,
            )

        if thought.action == "final_answer":
            action = AgentAction(
                iteration=iteration,
                action_type="final_answer",
                status="success",
            )
            actions.append(action)
            return thought, action, self.build_result(context, thoughts, actions)

        if thought.action == "ask_clarification":
            return thought, None, AgentResult(
                agent_name=self.agent_name,
                status="partial",
                content=thought.clarifying_question
                or "Could you provide more details?",
                iterations=iteration,
            )

        try:
            action = await self.act(thought, context)
            actions.append(action)
        except Exception as exc:
            return thought, None, AgentResult(
                agent_name=self.agent_name,
                status="failed",
                content=f"Agent failed during act: {exc}",
                warnings=[_warning("act_error", str(exc))],
                iterations=iteration,
            )

        try:
            done = await self.observe(thought, action, context)
            if done:
                return thought, action, self.build_result(context, thoughts, actions)
        except Exception as exc:
            return thought, action, AgentResult(
                agent_name=self.agent_name,
                status="failed",
                content=f"Agent failed during observe: {exc}",
                warnings=[_warning("observe_error", str(exc))],
                iterations=iteration,
            )

        return thought, action, None
