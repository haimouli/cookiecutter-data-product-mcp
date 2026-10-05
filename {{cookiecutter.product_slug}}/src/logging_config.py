"""Stdout logging for the console, CloudWatch, and Splunk.

One event per line goes to stdout. Container log drivers, the CloudWatch agent,
and Splunk forwarders can collect that stream without a vendor SDK.

MCP_LOG_FORMAT=json emits a single JSON object per line. MCP_LOG_FORMAT=console
emits a single readable line for local development.
"""

import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uvicorn.config import LOGGING_CONFIG

from src.settings import Settings

CONSOLE_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s service=%(service)s request_id=%(request_id)s"
_HANDLER_MARKER = "_data_product_handler"
_RESERVED_LOG_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_service_context: dict[str, str] = {}
_request_ids: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger(__name__)


def set_service_context(settings: Settings) -> None:
    """Copy product identity onto every later log record."""
    _service_context["service"] = settings.product_slug
    _service_context["product"] = settings.product_name
    _service_context["team"] = settings.domain_team


class ContextFilter(logging.Filter):
    """Add service identity and the active request id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach service, product, team, and request id to the record."""
        for key, value in _service_context.items():
            setattr(record, key, value)
        if not getattr(record, "request_id", None):
            record.request_id = _request_ids.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize the record as one JSON object."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_KEYS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str, separators=(",", ":"))


def _formatter(log_format: str) -> logging.Formatter:
    """Return the console or JSON formatter selected by settings."""
    if log_format == "console":
        return logging.Formatter(CONSOLE_FORMAT)
    return JsonFormatter()


def _stdout_handler() -> logging.Handler:
    """Return the process stdout handler, creating it once."""
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return handler
    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    return handler


def logging_dict(settings: Settings) -> dict[str, Any]:
    """Uvicorn replaces handlers on startup, so give it the same stdout config."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"context": {"()": "src.logging_config.ContextFilter"}},
        "formatters": {
            "json": {"()": "src.logging_config.JsonFormatter"},
            "console": {"format": CONSOLE_FORMAT},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": settings.log_format,
                "filters": ["context"],
            }
        },
        "root": {"level": settings.log_level, "handlers": ["stdout"]},
        "loggers": {"uvicorn.access": {"level": "WARNING"}},
    }


def configure_logging(settings: Settings) -> None:
    """Point application and uvicorn logs at stdout in the selected format."""
    set_service_context(settings)
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    handler = _stdout_handler()
    handler.setLevel(settings.log_level)
    handler.setFormatter(_formatter(settings.log_format))
    if not any(isinstance(item, ContextFilter) for item in handler.filters):
        handler.addFilter(ContextFilter())
    LOGGING_CONFIG.clear()
    LOGGING_CONFIG.update(logging_dict(settings))


def _header(scope: Scope, name: bytes) -> str | None:
    """Return one decoded request header, or None when it is missing or invalid."""
    for key, value in scope.get("headers", []):
        if key.lower() != name:
            continue
        try:
            decoded = value.decode().strip()
        except UnicodeDecodeError:
            return None
        return decoded or None
    return None


def _client_ip(scope: Scope) -> str:
    """Return the client address, or a dash when the connection has none."""
    client = scope.get("client")
    if not client:
        return "-"
    return str(client[0])


def _request_level(path: str, status_code: int, log_health: bool) -> int:
    """Keep successful health probes at DEBUG unless health logging is enabled."""
    if path == "/health" and status_code < 400 and not log_health:
        return logging.DEBUG
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


class AccessLogMiddleware:
    """Log one structured line per HTTP request without buffering the body."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        """Keep the downstream app and logging settings."""
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Log method, path, status, and duration without reading the body."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _header(scope, b"x-request-id") or uuid4().hex
        token = _request_ids.set(request_id)
        status_code = 500
        start = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            """Capture the status code and echo X-Request-Id on the response."""
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(
                "Request failed",
                extra={"event": "http.error", "method": scope.get("method", "-"), "path": scope.get("path", "-")},
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path = scope.get("path", "-")
            logger.log(
                _request_level(path, status_code, self.settings.log_health),
                "HTTP request",
                extra={
                    "event": "http.request",
                    "request_id": request_id,
                    "method": scope.get("method", "-"),
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip(scope),
                },
            )
            _request_ids.reset(token)
