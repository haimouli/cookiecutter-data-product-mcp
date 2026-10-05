# cookiecutter-data-product-mcp

Cookiecutter template for an independent MCP server for a core data product.

The generated project is a FastAPI app that mounts a [FastMCP](https://gofastmcp.com) server over Streamable HTTP at `/mcp`, a public `/health` endpoint, domain logic separated from tool registration, stdout JSON logs for CloudWatch or Splunk, pytest coverage gated at 95%, and a non-root container image.

## Generate

```bash
uvx cookiecutter .
```

Prompts:

- `product_name`
- `product_slug`
- `domain_team`
- `tools_prefix`
- `auth_scope`
- `owner_email`
- `python_version`

After generation, the hook runs `uv lock` if uv is installed. Then:

```bash
cd <product_slug>
make install
make ci
make run
```

MCP endpoint: `http://localhost:8000/mcp`

Health: `http://localhost:8000/health`

Make targets expect GNU Make. On Windows, use Git Bash, WSL, or another GNU Make install.
