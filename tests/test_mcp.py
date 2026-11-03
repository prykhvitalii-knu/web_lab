import asyncio
import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("MCP_TENANT_ID", "mcp-test-tenant")

from app import mcp_agent, mcp_server, models


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
    declarations = mcp_agent.gemini_function_declarations(list(tools.values()))
    assert {tool["name"] for tool in declarations} == {
        "list_recipes",
        "get_recipe",
        "list_recipe_ingredients",
    }
    list_declaration = next(
        tool for tool in declarations if tool["name"] == "list_recipes"
    )
    assert list_declaration["parameters"]["type"] == "OBJECT"
    assert list_declaration["parameters"]["properties"]["skip"]["type"] == "INTEGER"
    assert "default" not in list_declaration["parameters"]["properties"]["skip"]


def test_assistant_cannot_use_mcp_write_tools():
    class FakeSession:
        async def call_tool(self, name, arguments):
            raise AssertionError("A write tool must never be invoked")

    with pytest.raises(ValueError, match="not available to the assistant"):
        asyncio.run(mcp_agent.call_read_tool(FakeSession(), "create_recipe", {}))


def test_mcp_client_reads_only_the_requested_tenant(tmp_path, monkeypatch):
    database_path = tmp_path / "mcp.sqlite"
    engine = create_engine(f"sqlite:///{database_path}")
    models.Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        selected_user = models.User(
            email="selected@example.com",
            hashed_password="unused",
            tenant_id="selected-tenant",
        )
        other_user = models.User(
            email="other@example.com",
            hashed_password="unused",
            tenant_id="other-tenant",
        )
        db.add_all([selected_user, other_user])
        db.flush()
        db.add_all(
            [
                models.Recipe(
                    title="Selected Pale Ale",
                    style="Pale Ale",
                    abv=5.0,
                    ibu=35,
                    owner_id=selected_user.id,
                ),
                models.Recipe(
                    title="Private Stout",
                    style="Stout",
                    abv=6.0,
                    ibu=45,
                    owner_id=other_user.id,
                ),
            ]
        )
        db.commit()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    async def inspect_tenant_recipes():
        async with mcp_agent.connect_to_mcp("selected-tenant") as session:
            tools = await session.list_tools()
            assert "list_recipes" in {tool.name for tool in tools.tools}
            result = await session.call_tool(
                "list_recipes", {"skip": 0, "limit": 10}
            )
            assert not result.isError
            return json.loads(result.content[0].text)

    recipes = asyncio.run(inspect_tenant_recipes())
    assert [recipe["title"] for recipe in recipes["items"]] == [
        "Selected Pale Ale"
    ]
