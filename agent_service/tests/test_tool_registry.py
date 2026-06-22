import pytest
from agent_service.tools.registry import ToolRegistry
from agent_service.contracts import ToolDef


class FakeTool:
    """Simulates an async tool function."""
    def __init__(self, name: str):
        self.name = name
        self.call_count = 0

    async def __call__(self, **kwargs):
        self.call_count += 1
        return {"status": "ok", "kwargs": kwargs}


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search real estate listings",
        parameters={"query": "str", "filters": "dict"},
        required_params=["query"],
        allowed_for=["property_search", "investment_advisor"],
    ))
    reg.register(ToolDef(
        name="search_articles",
        description="Search knowledge articles",
        parameters={"query": "str", "filters": "dict"},
        required_params=["query"],
        allowed_for=["legal_advisor", "news_agent"],
    ))
    return reg


def test_list_tools_for_agent(registry):
    tools = registry.list_for_agent("property_search")
    tool_names = [t.name for t in tools]
    assert "search_listings" in tool_names
    assert "search_articles" not in tool_names


def test_list_tools_for_agent_not_allowed_returns_empty(registry):
    tools = registry.list_for_agent("market_analysis")
    assert len(tools) == 0


def test_has_tool(registry):
    assert registry.has_tool("search_listings") is True
    assert registry.has_tool("nonexistent") is False


def test_get_tool_def(registry):
    tool_def = registry.get_tool_def("search_listings")
    assert tool_def is not None
    assert tool_def.name == "search_listings"
    assert "query" in tool_def.required_params


def test_register_duplicate_raises(registry):
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ToolDef(
            name="search_listings",
            description="Duplicate",
            allowed_for=[],
        ))


def test_is_tool_allowed_for_agent(registry):
    assert registry.is_tool_allowed_for_agent("search_listings", "property_search") is True
    assert registry.is_tool_allowed_for_agent("search_articles", "property_search") is False
    assert registry.is_tool_allowed_for_agent("nonexistent", "property_search") is False
