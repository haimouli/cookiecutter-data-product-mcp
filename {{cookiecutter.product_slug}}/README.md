# {{cookiecutter.product_name}} MCP Server

Independent MCP server for the {{cookiecutter.product_name}} core data product.

- Owner: {{cookiecutter.domain_team}} ({{cookiecutter.owner_email}})
- Required scope: `{{cookiecutter.auth_scope}}`
- Tool prefix: `{{cookiecutter.tools_prefix}}`

Built with FastAPI, uv, and [FastMCP](https://gofastmcp.com). Tools are served over Streamable HTTP at `/mcp`. `/health` stays public.

## Getting started

```bash
make install
cp .env.example .env
make run
```

- Health: http://localhost:8000/health
- MCP: http://localhost:8000/mcp

## Make targets

| Target | What it does |
| --- | --- |
| `make install` | Install runtime and dev dependencies |
| `make format` | Format `src` and `tests` with Ruff |
| `make lint` | Lint and check formatting |
| `make test` | Run pytest |
| `make coverage` | Run tests and fail under 95% coverage |
| `make run` | Start the dev server with reload |
| `make package` | Build an sdist and wheel |
| `make ci` | Clean, reinstall, lint, test with coverage, and package |
| `make docker-build` | Build the container image |
| `make docker-up` | Rebuild and run the container on port 8000 |
| `make docker-down` | Stop and remove the container |
| `make docker-logs` | Follow container logs |
| `make clean` | Remove virtualenv, build, and coverage artifacts |

Make targets expect GNU Make. On Windows, use Git Bash, WSL, or another GNU Make install.

## Add a tool

1. Put the query or transformation in `src/domain_logic/`.
2. Register it in `src/tools/handlers.py` with `@server.tool`, the product prefix, and `required_scope` metadata.
3. Add a test that calls the tool with `fastmcp.Client(app.state.mcp)`.

Unexpected tool failures are logged and returned as a generic `ToolError`. Validation and domain errors you raise as `ToolError` keep their message.

## Auth

Auth is off by default (`MCP_AUTH_REQUIRED=false`). When it is on, requests to `/mcp` must send `Authorization: Bearer <scopes>`.

`src/auth.py` treats the bearer token as a space-separated scope list. That parser is for local development only. Replace `parse_scopes` with verification against your identity provider before enabling auth outside local use.

## Docker

The image runs as a non-root user and checks `/health`. Set `MCP_WORKERS` to the number of uvicorn processes for that environment (`1` by default). `make run` does not use it, because `--reload` cannot run multiple workers. Above `1`, the server uses stateless HTTP so a request is not pinned to the process that created the session. A post-generation hook runs `uv lock` when uv is available. Image builds use `--frozen` when `uv.lock` exists and fall back to an unlocked sync otherwise.

## Logging

Logs go to stdout, one event per line. That is the stream CloudWatch, Splunk, and a local terminal all collect. There is no AWS or Splunk SDK in the app.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MCP_LOG_FORMAT` | `json` | `json` for CloudWatch Logs Insights and Splunk. `console` for local reading. The image sets `json`. |
| `MCP_LOG_LEVEL` | `INFO` | Standard Python level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `MCP_LOG_HEALTH` | `false` | When false, successful `/health` probes are logged at `DEBUG` so they do not flood INFO logs. |

`.env.example` uses `console`. Copy it for local runs. Do not point production at a file logger; leave logs on stdout and let the container log driver or forwarder ship them.

Each JSON line has `timestamp`, `level`, `logger`, `message`, `service`, `product`, `team`, and `request_id`. Request lines add `event=http.request`, `method`, `path`, `status_code`, `duration_ms`, and `client_ip`. Tool lines use `tool.completed`, `tool.rejected`, or `tool.failed`. Entity ids and bearer tokens are not logged.

CloudWatch Logs Insights:

```
fields timestamp, level, event, message, request_id, status_code, duration_ms
| filter event = "http.request"
| sort timestamp desc
```

Splunk, with `sourcetype=_json`:

```
event=http.request OR event=tool.failed
| table timestamp level service request_id event path tool status_code duration_ms
```

Send `X-Request-Id` to correlate a call across the access log, auth denial, and tool log. The response echoes that header.
