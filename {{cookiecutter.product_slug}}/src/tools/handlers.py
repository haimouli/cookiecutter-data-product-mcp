import logging
import time

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from src.domain_logic.summary import get_summary
from src.settings import Settings

logger = logging.getLogger(__name__)


def register_tools(server: FastMCP, settings: Settings) -> None:
    """Register product tools. Add new tools in this function."""
    tool_name = f"{settings.tools_prefix}get_summary"

    @server.tool(
        name=tool_name,
        description=f"Retrieve summary data for {settings.product_name}",
        meta={
            "required_scope": settings.auth_scope,
            "domain_team": settings.domain_team,
            "owner": settings.owner_email,
        },
        annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    )
    def get_summary_tool(id: str) -> str:
        """Return the summary, or raise ToolError when the id is blank or the call fails."""
        started = time.perf_counter()
        try:
            result = get_summary(id)
        except ValueError as exc:
            logger.warning(
                "Tool call rejected",
                extra={
                    "event": "tool.rejected",
                    "tool": tool_name,
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                    "duration_ms": _elapsed_ms(started),
                },
            )
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            logger.exception(
                "Tool call failed",
                extra={"event": "tool.failed", "tool": tool_name, "duration_ms": _elapsed_ms(started)},
            )
            raise ToolError("Tool execution failed") from exc
        logger.info(
            "Tool call completed",
            extra={"event": "tool.completed", "tool": tool_name, "duration_ms": _elapsed_ms(started)},
        )
        return result

    logger.info("Registered tool", extra={"event": "tool.registered", "tool": tool_name})


def _elapsed_ms(started: float) -> float:
    """Return milliseconds since started, rounded for log fields."""
    return round((time.perf_counter() - started) * 1000, 2)
