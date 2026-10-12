---
name: fastmcp-server
description: Build, extend, test, or debug Python MCP servers using FastMCP. Use when FastMCP is requested or already used by the server; covers tool and resource interfaces, lifecycle, state, and transport behavior. Not for MCP client integrations or merely calling an existing server.
---

# FastMCP server authoring

Use the standalone `fastmcp` package, not the similarly named module inside
`mcp.server`. Preserve an existing project's chosen SDK and version; an MCP
request alone is not a reason to migrate it to FastMCP.

## Establish the API in use

Inspect the project's dependency declarations and lockfile before installing
anything. In its environment, check the installed distribution and CLI:

```bash
uv run python -c "from importlib.metadata import version; print(version('fastmcp'))"
uv run fastmcp --help
```

For a new project using uv, `uv add fastmcp` records
the dependency. Follow an existing project's package manager.

Retrieve the relevant official documentation before relying on a signature,
import, decorator argument, or CLI option. Start at
[the docs index](https://gofastmcp.com/llms.txt). The root documents the current
major; older majors have versioned sections such as `/v3/`. Check the page's
version and the installed package: a versioned major's docs can still describe
features newer than the installed minor. Use installed source/signatures or
the matching Git tag when docs and runtime disagree. Do not upgrade a project
just to make a copied example work.

Read only the pages relevant to the change:

| Task | Documentation paths on gofastmcp.com |
| --- | --- |
| Component definitions, schemas, errors | `/servers/tools.md`, `/servers/resources.md`, `/servers/prompts.md` |
| Startup and shared dependencies | `/servers/lifespan.md`, `/servers/dependency-injection.md` |
| Context, state, user interaction | `/servers/context.md`, `/servers/sessions.md`, `/servers/elicitation.md` |
| Combining servers | `/servers/composition.md` |
| Authentication and permissions | `/servers/auth/authentication.md`, `/servers/authorization.md` |
| Tests and transport | `/servers/testing.md`, `/deployment/running-server.md`, `/deployment/http.md` |
| CLI and project configuration | `/cli/running.md`, `/cli/inspecting.md`, `/deployment/server-configuration.md` |

Resolve version-specific equivalents through the index. For migration work,
read the matching upgrade guide under `/getting-started/upgrading/` and verify
composition, state, and protocol behavior as well as renamed imports.

## Design the model-facing interface

- Use tools for operations, resources for addressable content, and prompts for
  reusable message templates. Match what the target client actually supports.
- Prefer a typed operation such as `search_notes(query, limit)` over a generic
  `execute(action, payload)` dispatcher. Descriptions should explain when to
  call it, significant side effects, and what the result means.
- Annotate parameters and returns. Use `Annotated` with Pydantic `Field` for
  bounds and parameter descriptions; use `Literal` or enums for closed choices.
  Inspect the emitted schema rather than assuming docstring parsing works in
  every version. Inject `Context` or dependencies through the documented API;
  callers should not supply them as tool arguments.
- Return native typed data instead of JSON-encoding tool results into strings.
  Use specific item types (`list[Note]`, not a bare `list`) when structured
  output matters. Test the advertised output schema and actual result.
- Bound search/list results and expose continuation or narrowing information.
  Never silently truncate serialized JSON. Resources returning JSON should
  declare `mime_type="application/json"`; resource contents are distinct from
  tool structured output.
- Set accurate MCP annotations such as `readOnlyHint`; these are client hints,
  not authorization or a guarantee that execution is safe. Enforce permissions
  against the authenticated caller at the operation boundary.
- Raise `fastmcp.exceptions.ToolError` for deliberate, safe, actionable tool
  failures. Do not return `{"error": ...}` as a successful tool result or expose
  raw upstream exceptions containing credentials. Verify error masking and
  client-visible messages in the target version.

## Lifecycle and concurrency

Keep the server importable: a module-level `mcp = FastMCP(...)` is a simple
CLI entrypoint; retain existing factories or composition when appropriate.
Put executable startup behind a main guard for direct script use. The CLI
imports the module and does not run that guard.

Acquire shared HTTP clients, pools, and other owned resources in a lifespan,
with cleanup on exit. When embedding `http_app()` in an ASGI app, wire its
lifespan as documented. Avoid network calls at import time or creating an
unclosed client on every tool call.

Use `async def` with async I/O libraries. Declaring a function async does not
make blocking I/O nonblocking. Recent FastMCP versions dispatch synchronous
handlers to a threadpool; verify the target version and account for thread
safety. Keep domain logic callable independently of MCP wrappers.

Inject `Context` for request logging, progress, and protocol capabilities.
Check which methods are async and await them. Do not retain a request Context
in globals or use it after its call ends. Keep stdio stdout exclusively for
protocol traffic; send diagnostics to stderr or the logging facilities.

## State and interactive operations

Distinguish request data, server-wide dependencies, and durable user data.
Do not assume `ctx.set_state` survives subsequent requests: semantics depend
on FastMCP version and protocol era. For cross-call state, read the session
state docs. Key multi-user state by verified caller identity; for trusted
single-client use, choose explicit session or application storage and document
its scope. Never use a module global as a per-user store. Verify isolation and
restart persistence when the request requires them.

Elicitation and resumable input differ by protocol era. Read the version's
elicitation docs and confirm the client's capabilities before implementing
confirmation. Handle decline, cancellation, and unsupported clients without
performing the mutation. A caller-supplied `confirmed=True` is not evidence of
human approval. For resumable operations, bind approval to the caller and exact
operation, recheck permissions, and prevent duplicate effects on retries.

For filesystem-backed components, resolve paths against an explicit allowed
root and reject escapes, including symlinks and absolute paths. A URI template
or a client-provided root is not an access-control boundary. Test outside-root
reads through both tools and resources that expose files.

## Run and verify

For local use, stdio is a simple default; network access uses Streamable HTTP.
Keep host/port settings on the transport runner, not the `FastMCP` constructor.
Use `run_async()` when the caller already owns an event loop. Binding HTTP does
not add authentication: configure the documented auth integration for protected
remote access. Hosting-provider provisioning is separate from server authoring.

Start with in-process protocol tests. This minimal example can live in a single
`test_server.py`; run it with the project's pytest and async test plugin:

```python
import pytest
from fastmcp import Client, FastMCP

mcp = FastMCP("Arithmetic")


@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@pytest.mark.asyncio
async def test_add():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools] == ["add"]
        result = await client.call_tool("add", {"a": 1, "b": 2})
        assert result.data == 3
```

Test through `Client(mcp)`, not just direct handler calls. Include meaningful
invalid input and domain failure cases; verify errors are errors on the wire.
Exercise resource reads and prompts if exposed. Test lifecycle cleanup, caller
isolation, and confirmation decline/retry behavior where relevant.

Inspect the client-visible catalog with the installed CLI's `inspect` command
or `Client.list_tools()`. An in-process pass does not verify transport wiring:
smoke-test the requested stdio/HTTP entrypoint, including authentication and
lifespan startup if applicable. Report the version and actual checks run.
