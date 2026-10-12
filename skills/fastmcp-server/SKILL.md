---
name: fastmcp-server
description: Build, extend, or review Python MCP servers using FastMCP 3 or 4. Covers tool design, implementation, and verification with documentation matched to the project's version.
---

# FastMCP server authoring

## Retrieve the API you need

Check the project's dependency constraints, lockfile, and installed `fastmcp`
version before writing code. Preserve its major version and package manager.
Use the standalone `fastmcp` package rather than `mcp.server.fastmcp`.

Fetch [gofastmcp.com/llms.txt](https://gofastmcp.com/llms.txt), find the relevant
topic in the installed major's documentation, and read that page's Markdown.
The index includes versioned pages such as `/v3/`; don't assume the unversioned
page matches the project. Fetch only what the task needs, such as tools,
composition, lifespan, testing, or deployment.

Confirm newer features against the installed package's signatures/source or
its exact release tag: even same-major docs may be ahead of an older minor.
For a Git-pinned dependency, inspect that revision. If docs are unavailable,
use installed source and tests and state any uncertainty. Don't upgrade the
project to fit an example. Especially recheck state lifetime, elicitation,
transforms, and import paths when moving between FastMCP 3 and 4.

## Design for the agent's task

Start with a concrete request the server should help complete. Design the
operations and responses around that workflow, not automatically around every
REST endpoint. For example, diagnosing a failed run should expose the run,
relevant logs, and failure context without making the agent join raw API dumps.

- Return compact summaries for discovery, with stable IDs and a way to fetch
  detail. Keep search snippets separate from full documents. Bound output and
  report partial results with a cursor or useful narrowing advice.
- Filter and aggregate near the data. Remove irrelevant fields, but preserve
  meaningful nulls, empty values, and declared output contracts.
- Describe when to use each tool, its side effects, and how to continue from
  its result. Put shared workflow guidance in server instructions; use resources
  and prompts for reference material clients can retrieve when needed.
- Use typed parameters and results, meaningful field descriptions, and input
  constraints. Return native structured data instead of JSON strings. Inspect
  the schemas clients actually receive. Tool annotations are hints, not auth.
- For a broad API or composable SDK, consider tool search or code mode instead
  of loading every schema upfront. Check availability in the project's version;
  don't force a transform onto a small, already useful toolset.

[Is Your MCP Server Good?](https://github.com/PrefectHQ/is-your-mcp-server-good)
compares these designs. Measure catalog size, response size, and the agent's
actual tool-call sequence; fewer tools alone doesn't prove a better server.

## Implement and verify

Use async I/O without blocking the event loop. Own shared clients and pools
through a lifespan with cleanup; keep credentials and caller state scoped to
their actual owner. Return actionable failures through FastMCP's error handling.
For stateful or interactive tools, retrieve the version's behavior and test
caller isolation, cancellation, and retries rather than assuming persistence.

Keep the server importable. Preserve the requested hosting provider and
transport: local stdio, self-hosted HTTP/ASGI, and managed hosting are all valid.
Read the chosen runtime's current configuration requirements; do not couple
tool logic to a provider. Keep stdout clean for stdio and verify lifespan/auth
wiring for HTTP.

Exercise tools through `Client(server)`, including a meaningful failure case,
and inspect the advertised inputs and outputs. Then smoke-test the actual
entrypoint/transport. Run a representative agent task and inspect whether the
returned evidence supports a useful answer without excessive calls or context.
