import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.settings import Settings

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    def __init__(self, detail: str, status_code: int) -> None:
        """Store the denial message and HTTP status."""
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def parse_scopes(token: str) -> set[str]:
    """Development parser: the bearer token is a space-separated scope list.

    Replace this with IdP token verification before enabling MCP_AUTH_REQUIRED in production.
    """
    return {part for part in token.split() if part}


def authorize(authorization: str | None, settings: Settings) -> None:
    """Allow the call when auth is off or the token has the required scope."""
    if not settings.auth_required:
        return
    if authorization is None or not authorization.startswith("Bearer "):
        raise AuthenticationError("Bearer token required", 401)
    scopes = parse_scopes(authorization.removeprefix("Bearer ").strip())
    if settings.auth_scope not in scopes:
        raise AuthenticationError("Missing required scope", 403)


def _authorization_header(scope: Scope) -> str | None:
    """Return the Authorization header value, if the request sent one."""
    headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
    for key, value in headers:
        if key.lower() == b"authorization":
            return value.decode()
    return None


class ScopeAuthMiddleware:
    """Protect /mcp when auth is enabled. Health stays public.

    This is pure ASGI so it does not buffer Streamable HTTP response bodies.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        """Keep the downstream app and the auth settings."""
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject /mcp calls that lack the required scope when auth is enabled."""
        if scope["type"] != "http" or not self.settings.auth_required:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return
        try:
            authorize(_authorization_header(scope), self.settings)
        except AuthenticationError as exc:
            logger.warning(
                "Authorization denied",
                extra={
                    "event": "auth.denied",
                    "path": path,
                    "status_code": exc.status_code,
                    "reason": exc.detail,
                },
            )
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
