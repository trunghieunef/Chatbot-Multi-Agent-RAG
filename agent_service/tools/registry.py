from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_service.contracts import ToolDef


ToolFunction = Callable[..., Awaitable[dict[str, Any]]]


class ToolRegistry:
    """Registry of tools that agents can call.

    Each tool is registered with metadata (ToolDef) and an async
    callable. Agents query the registry for their allowed tools
    and call them by name.
    """

    def __init__(self):
        self._defs: dict[str, ToolDef] = {}
        self._functions: dict[str, ToolFunction] = {}

    def register(
        self,
        tool_def: ToolDef,
        func: ToolFunction | None = None,
    ) -> None:
        """Register a tool definition and optionally its function.

        The function can be bound later via bind().
        """
        if tool_def.name in self._defs:
            raise ValueError(
                f"Tool '{tool_def.name}' is already registered."
            )
        self._defs[tool_def.name] = tool_def
        if func is not None:
            self._functions[tool_def.name] = func

    def bind(self, name: str, func: ToolFunction) -> None:
        """Bind a callable to an already-registered tool."""
        if name not in self._defs:
            raise KeyError(f"Tool '{name}' is not registered. Call register() first.")
        self._functions[name] = func

    def has_tool(self, name: str) -> bool:
        """Check if a tool name is registered."""
        return name in self._defs

    def get_tool_def(self, name: str) -> ToolDef | None:
        """Get the ToolDef for a tool, or None."""
        return self._defs.get(name)

    def is_tool_allowed_for_agent(self, tool_name: str, agent_name: str) -> bool:
        """Check if agent is allowed to use this tool."""
        tool_def = self._defs.get(tool_name)
        if tool_def is None:
            return False
        if not tool_def.allowed_for:
            return True  # No restrictions
        return agent_name in tool_def.allowed_for

    def list_for_agent(self, agent_name: str) -> list[ToolDef]:
        """Return all ToolDefs this agent is allowed to use."""
        return [
            tool_def
            for tool_def in self._defs.values()
            if self.is_tool_allowed_for_agent(tool_def.name, agent_name)
        ]

    def list_all(self) -> list[ToolDef]:
        """Return all registered ToolDefs."""
        return list(self._defs.values())

    async def call(
        self,
        tool_name: str,
        agent_name: str,
        **params: Any,
    ) -> dict[str, Any]:
        """Call a tool by name, checking agent permission.

        Returns:
            dict with at least: {"status": "success"|"error", ...}

        Raises:
            KeyError: Tool not registered or not bound.
            PermissionError: Agent not allowed to use this tool.
        """
        if not self.has_tool(tool_name):
            raise KeyError(f"Tool '{tool_name}' is not registered.")
        if not self.is_tool_allowed_for_agent(tool_name, agent_name):
            raise PermissionError(
                f"Agent '{agent_name}' is not allowed to use tool '{tool_name}'."
            )
        func = self._functions.get(tool_name)
        if func is None:
            raise KeyError(
                f"Tool '{tool_name}' has no bound function. Call bind() first."
            )
        return await func(**params)
