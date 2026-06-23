from __future__ import annotations

from agent_service.contracts import ToolDef
from agent_service.llm.function_schema import (
    function_declarations_for,
    tooldef_to_function_declaration,
)


def test_maps_params_and_required():
    td = ToolDef(
        name="search_listings",
        description="Tìm BĐS",
        parameters={"query": "str", "filters": "dict", "top_k": "int"},
        required_params=["query"],
        allowed_for=["property_search"],
    )
    fd = tooldef_to_function_declaration(td)
    assert fd.name == "search_listings"
    assert fd.description == "Tìm BĐS"
    props = fd.parameters.properties
    assert set(props.keys()) == {"query", "filters", "top_k"}
    assert str(props["query"].type).upper().endswith("STRING")
    assert str(props["top_k"].type).upper().endswith("INTEGER")
    assert fd.parameters.required == ["query"]


def test_function_declarations_for_list():
    tds = [
        ToolDef(name="a", parameters={"x": "str"}),
        ToolDef(name="b", parameters={"y": "int"}),
    ]
    decls = function_declarations_for(tds)
    assert [d.name for d in decls] == ["a", "b"]
