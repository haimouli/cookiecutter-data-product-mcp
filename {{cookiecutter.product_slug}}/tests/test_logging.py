import asyncio
import io
import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import ValidationError
from uvicorn.config import LOGGING_CONFIG

from src.logging_config import (
    AccessLogMiddleware,
    ContextFilter,
    JsonFormatter,
    _request_ids,
    configure_logging,
)
from src.server import app, create_app
from src.settings import Settings


def test_settings_normalize_log_configuration() -> None:
    settings = Settings(log_level="debug", log_format="JSON")
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "json"


def test_settings_reject_unknown_log_level() -> None:
    with pytest.raises(ValidationError, match="MCP_LOG_LEVEL"):
        Settings(log_level="verbose")


def test_settings_reject_unknown_log_format() -> None:
    with pytest.raises(ValidationError):
        Settings(log_format="xml")


def test_json_formatter_includes_exception_and_extra_fields() -> None:
    try:
        raise RuntimeError("db down")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="src.demo",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed %s",
        args=("summary",),
        exc_info=exc_info,
    )
    record.event = "tool.failed"
    record.custom = object()
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "failed summary"
    assert payload["event"] == "tool.failed"
    assert "db down" in payload["exception"]
    assert "custom" in payload
    assert "msg" not in payload


def test_context_filter_uses_active_request_id() -> None:
    record = logging.LogRecord("src.demo", logging.INFO, __file__, 1, "hello", (), None)
    assert ContextFilter().filter(record) is True
    assert record.request_id == "-"

    token = _request_ids.set("req-from-context")
    try:
        contextual = logging.LogRecord("src.demo", logging.INFO, __file__, 1, "hello", (), None)
        ContextFilter().filter(contextual)
        assert contextual.request_id == "req-from-context"
    finally:
        _request_ids.reset(token)

    explicit = logging.LogRecord("src.demo", logging.INFO, __file__, 1, "hello", (), None)
    explicit.request_id = "keep-me"
    ContextFilter().filter(explicit)
    assert explicit.request_id == "keep-me"


def _capture_log(message: str, **extra: object) -> str:
    handler = next(item for item in logging.getLogger().handlers if getattr(item, "_data_product_handler", False))
    stream = io.StringIO()
    previous = handler.stream
    handler.stream = stream
    try:
        logging.getLogger("src.demo").info(message, extra=extra or None)
    finally:
        handler.stream = previous
    return stream.getvalue().strip()


def test_configure_logging_writes_json_and_console() -> None:
    configure_logging(
        Settings(log_level="INFO", log_format="json", product_slug="demo-svc", product_name="Demo", domain_team="Team")
    )
    payload = json.loads(_capture_log("json-ready", event="unit"))
    assert payload["message"] == "json-ready"
    assert payload["service"] == "demo-svc"
    assert payload["request_id"] == "-"

    configure_logging(Settings(log_level="DEBUG", log_format="console", product_slug="demo-svc"))
    console_line = _capture_log("console-ready")
    assert "console-ready" in console_line
    assert "service=demo-svc" in console_line
    assert LOGGING_CONFIG["handlers"]["stdout"]["formatter"] == "console"
    assert LOGGING_CONFIG["root"]["level"] == "DEBUG"


def test_health_logs_at_info_when_enabled(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    application = create_app(Settings(log_health=True, log_level="INFO"))
    with TestClient(application) as client:
        response = client.get("/health", headers={"X-Request-Id": "req-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert any(
        getattr(record, "event", None) == "http.request" and getattr(record, "path", None) == "/health"
        for record in caplog.records
    )
    assert any(getattr(record, "event", None) == "app.starting" for record in caplog.records)
    assert any(getattr(record, "event", None) == "app.stopping" for record in caplog.records)


def test_tool_failure_is_logged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)

    def boom(_entity_id: str) -> str:
        raise RuntimeError("db down")

    monkeypatch.setattr("src.tools.handlers.get_summary", boom)

    async def _run() -> None:
        async with Client(app.state.mcp) as client:
            await client.call_tool(f"{app.state.settings.tools_prefix}get_summary", {"id": "1"})

    with pytest.raises(ToolError, match="Tool execution failed") as exc_info:
        asyncio.run(_run())
    assert "db down" not in str(exc_info.value)
    assert any(getattr(record, "event", None) == "tool.failed" for record in caplog.records)


async def _call_middleware(inner, scope: dict, settings: Settings | None = None) -> list[dict]:
    messages: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    await AccessLogMiddleware(inner, settings or Settings(log_health=False))(scope, receive, send)
    return messages


def test_access_log_ignores_non_http() -> None:
    seen: dict[str, str] = {}

    async def inner(scope, receive, send) -> None:
        seen["type"] = scope["type"]

    asyncio.run(_call_middleware(inner, {"type": "lifespan"}))
    assert seen["type"] == "lifespan"


def test_access_log_generates_request_id_and_records_server_error(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    async def inner(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 500, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    generated = asyncio.run(
        _call_middleware(
            inner,
            {
                "type": "http",
                "method": "POST",
                "path": "/health",
                "headers": [(b"accept", b"text/plain"), (b"x-request-id", b"  ")],
            },
        )
    )
    invalid = asyncio.run(
        _call_middleware(
            inner,
            {"type": "http", "method": "POST", "path": "/mcp", "headers": [(b"x-request-id", b"\xff")]},
        )
    )
    assert generated[0]["headers"][-1][1].decode()
    assert invalid[0]["headers"][-1][1].decode()
    assert any(
        getattr(record, "event", None) == "http.request" and record.levelno == logging.ERROR and record.client_ip == "-"
        for record in caplog.records
    )


def test_access_log_records_unhandled_exception(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)

    async def inner(scope, receive, send) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            _call_middleware(
                inner,
                {"type": "http", "method": "GET", "path": "/mcp", "headers": [], "client": ("10.1.2.3", 9)},
            )
        )
    assert any(getattr(record, "event", None) == "http.error" for record in caplog.records)
    assert any(getattr(record, "client_ip", None) == "10.1.2.3" for record in caplog.records)
