import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.types import Tool


READ_ONLY_TOOL_NAMES = frozenset(
    {"list_recipes", "get_recipe", "list_recipe_ingredients"}
)
GEMINI_SCHEMA_KEYS = frozenset(
    {"type", "description", "properties", "required", "items", "enum"}
)
GEMINI_SCHEMA_TYPES = {
    "array": "ARRAY",
    "boolean": "BOOLEAN",
    "integer": "INTEGER",
    "number": "NUMBER",
    "object": "OBJECT",
    "string": "STRING",
}


@asynccontextmanager
async def connect_to_mcp(tenant_id: str) -> AsyncIterator[ClientSession]:
    project_root = Path(__file__).resolve().parents[1]
    server_environment = {"MCP_TENANT_ID": tenant_id}
    if "DATABASE_URL" in os.environ:
        server_environment["DATABASE_URL"] = os.environ["DATABASE_URL"]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=server_environment,
        cwd=project_root,
    )
    try:
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
    except McpError as exc:
        raise RuntimeError("The MCP recipe server could not be reached") from exc


def gemini_function_declarations(tools: list[Tool]) -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": _gemini_schema(tool.inputSchema),
        }
        for tool in tools
        if tool.name in READ_ONLY_TOOL_NAMES
    ]


async def call_read_tool(
    session: ClientSession, name: str, arguments: dict
) -> object:
    if name not in READ_ONLY_TOOL_NAMES:
        raise ValueError(f"MCP tool '{name}' is not available to the assistant")
    try:
        result = await session.call_tool(name, arguments)
    except McpError as exc:
        raise RuntimeError(f"MCP tool '{name}' could not be completed") from exc
    if result.isError:
        raise RuntimeError(f"MCP tool '{name}' failed")
    if result.structuredContent is not None:
        return result.structuredContent
    return [item.text for item in result.content if hasattr(item, "text")]


def _gemini_schema(schema: dict) -> dict:
    normalized = {
        key: value
        for key, value in schema.items()
        if key in GEMINI_SCHEMA_KEYS
    }
    if "type" in normalized:
        normalized["type"] = GEMINI_SCHEMA_TYPES.get(
            normalized["type"], normalized["type"]
        )
    if "properties" in normalized:
        normalized["properties"] = {
            name: _gemini_schema(property_schema)
            for name, property_schema in normalized["properties"].items()
        }
    if "items" in normalized:
        normalized["items"] = _gemini_schema(normalized["items"])
    return normalized
