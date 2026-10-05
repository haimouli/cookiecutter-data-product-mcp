import pytest
from fastapi.testclient import TestClient

from src.auth import AuthenticationError, authorize, parse_scopes
from src.server import create_app
from src.settings import Settings


def test_parse_scopes_ignores_empty_parts() -> None:
    assert parse_scopes(" data:read   data:write ") == {"data:read", "data:write"}
    assert parse_scopes("   ") == set()


def test_authorize_skips_when_auth_disabled() -> None:
    authorize(None, Settings(auth_required=False))


def test_authorize_requires_bearer_token() -> None:
    settings = Settings(auth_required=True, auth_scope="data:customer:read")
    with pytest.raises(AuthenticationError, match="Bearer token required") as exc_info:
        authorize("Token secret", settings)
    assert exc_info.value.status_code == 401


def test_authorize_requires_configured_scope() -> None:
    settings = Settings(auth_required=True, auth_scope="data:customer:read")
    with pytest.raises(AuthenticationError, match="Missing required scope") as exc_info:
        authorize("Bearer other:scope", settings)
    assert exc_info.value.status_code == 403


def test_authorize_accepts_required_scope() -> None:
    settings = Settings(auth_required=True, auth_scope="data:customer:read")
    authorize("Bearer data:customer:read extra", settings)


def test_mcp_route_requires_scope_when_auth_enabled() -> None:
    settings = Settings(auth_required=True, auth_scope="data:customer:read")
    app = create_app(settings)
    with TestClient(app) as client:
        missing = client.get("/mcp")
        assert missing.status_code == 401

        wrong_scope = client.get("/mcp", headers={"Authorization": "Bearer other:scope"})
        assert wrong_scope.status_code == 403

        allowed = client.get("/mcp", headers={"Authorization": "Bearer data:customer:read"})
        assert allowed.status_code not in {401, 403}

        health = client.get("/health")
        assert health.status_code == 200
