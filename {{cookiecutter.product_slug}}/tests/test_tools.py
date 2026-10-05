import asyncio

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError

from src.server import app, create_app
from src.settings import Settings


def _list_tools():
    async def _run():
        async with Client(app.state.mcp) as client:
            return await client.list_tools()

    return asyncio.run(_run())


def _call_tool(name: str, arguments: dict):
    async def _run():
        async with Client(app.state.mcp) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(_run())


def test_health_reports_product_metadata() -> None:
    settings = app.state.settings
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "product": settings.product_slug,
        "team": settings.domain_team,
        "auth_scope": settings.auth_scope,
    }


def test_extra_workers_still_serve_health() -> None:
    application = create_app(Settings(workers=4))
    assert application.state.settings.workers == 4
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200


def test_list_tools_includes_prefixed_summary() -> None:
    settings = app.state.settings
    tools = _list_tools()
    summary = next(tool for tool in tools if tool.name == f"{settings.tools_prefix}get_summary")
    assert summary.meta is not None
    assert summary.meta["required_scope"] == settings.auth_scope
    assert summary.meta["domain_team"] == settings.domain_team
    assert summary.meta["owner"] == settings.owner_email


def test_call_summary_tool() -> None:
    settings = app.state.settings
    result = _call_tool(f"{settings.tools_prefix}get_summary", {"id": "42"})
    assert result.data is not None
    assert "42" in str(result.data)
    assert settings.product_name in str(result.data)


def test_call_summary_tool_rejects_blank_id() -> None:
    settings = app.state.settings
    with pytest.raises(ToolError, match="id is required"):
        _call_tool(f"{settings.tools_prefix}get_summary", {"id": "  "})


def test_call_unknown_tool() -> None:
    with pytest.raises(ToolError):
        _call_tool("missing_tool", {})
