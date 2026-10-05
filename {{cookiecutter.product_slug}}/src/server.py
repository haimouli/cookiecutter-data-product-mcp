import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp import FastMCP

from src.auth import ScopeAuthMiddleware
from src.logging_config import AccessLogMiddleware, configure_logging
from src.settings import Settings, get_settings
from src.tools.handlers import register_tools

logger = logging.getLogger(__name__)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server and register the product tools."""
    server = FastMCP(
        settings.product_name,
        instructions=(
            f"MCP server for {settings.product_name}, owned by {settings.domain_team} "
            f"({settings.owner_email}). Tool calls require scope {settings.auth_scope} when auth is enabled."
        ),
        mask_error_details=True,
    )
    register_tools(server, settings)
    return server


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app, mount FastMCP, and expose public health."""
    settings = settings or get_settings()
    configure_logging(settings)
    mcp = create_mcp_server(settings)
    # path="/" because the app is mounted at /mcp. Lifespan must be passed up; Starlette does not run nested mounts.
    mcp_app = mcp.http_app(path="/", stateless_http=settings.workers > 1)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Start FastMCP's session manager and log process start and stop."""
        logger.info(
            "MCP server starting",
            extra={
                "event": "app.starting",
                "host": settings.host,
                "port": settings.port,
                "workers": settings.workers,
                "auth_required": settings.auth_required,
                "log_format": settings.log_format,
            },
        )
        async with mcp_app.lifespan(_app):
            yield
        logger.info("MCP server stopping", extra={"event": "app.stopping"})

    app = FastAPI(
        title=f"{settings.product_name} MCP Server",
        description=(
            f"Owned by {settings.domain_team} ({settings.owner_email}). Required scope: {settings.auth_scope}."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(ScopeAuthMiddleware, settings=settings)
    app.add_middleware(AccessLogMiddleware, settings=settings)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Return product identity for probes. This route stays public."""
        return {
            "status": "healthy",
            "product": settings.product_slug,
            "team": settings.domain_team,
            "auth_scope": settings.auth_scope,
        }

    app.mount("/mcp", mcp_app)
    app.state.mcp = mcp
    app.state.settings = settings
    return app


app = create_app()
