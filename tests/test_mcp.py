import asyncio
import os

os.environ.setdefault("MCP_TENANT_ID", "mcp-test-tenant")

from app import mcp_server


def test_mcp_exposes_three_read_tools_and_one_write_tool():
    tools = {
        tool.name: tool
        for tool in asyncio.run(mcp_server.mcp.list_tools())
    }

    assert {
        "list_recipes",
        "get_recipe",
        "list_recipe_ingredients",
        "create_recipe",
    } <= tools.keys()
    assert tools["list_recipes"].inputSchema["properties"]["skip"]["type"] == "integer"
    assert "title" in tools["create_recipe"].inputSchema["properties"]
