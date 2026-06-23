from __future__ import annotations

from typing import Any

from google.genai import types

from agent_service.contracts import ToolDef


_TYPE_MAP = {
    "str": types.Type.STRING,
    "string": types.Type.STRING,
    "int": types.Type.INTEGER,
    "integer": types.Type.INTEGER,
    "float": types.Type.NUMBER,
    "number": types.Type.NUMBER,
    "bool": types.Type.BOOLEAN,
    "boolean": types.Type.BOOLEAN,
    "dict": types.Type.OBJECT,
    "object": types.Type.OBJECT,
    "list": types.Type.ARRAY,
    "array": types.Type.ARRAY,
}


def _schema_for(py_type: str) -> types.Schema:
    gem_type = _TYPE_MAP.get(str(py_type).lower(), types.Type.STRING)
    if gem_type == types.Type.OBJECT:
        # Gemini requires OBJECT schemas to be open or have properties; keep open.
        return types.Schema(type=gem_type)
    if gem_type == types.Type.ARRAY:
        return types.Schema(type=gem_type, items=types.Schema(type=types.Type.STRING))
    return types.Schema(type=gem_type)


def tooldef_to_function_declaration(tool_def: ToolDef) -> types.FunctionDeclaration:
    properties = {
        name: _schema_for(py_type)
        for name, py_type in (tool_def.parameters or {}).items()
    }
    parameters = types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=list(tool_def.required_params or []),
    )
    return types.FunctionDeclaration(
        name=tool_def.name,
        description=tool_def.description or "",
        parameters=parameters,
    )


def function_declarations_for(
    tool_defs: list[ToolDef],
) -> list[types.FunctionDeclaration]:
    return [tooldef_to_function_declaration(td) for td in tool_defs]
