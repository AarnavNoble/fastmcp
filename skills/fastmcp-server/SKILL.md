---
name: fastmcp-server
description: Build, extend, or review MCP servers with Python FastMCP, using documentation matched to the project's version.
---

# Authoring MCP servers with FastMCP

## Find the current API

Check the project's installed FastMCP version and dependency constraints.
Fetch [the documentation index](https://gofastmcp.com/llms.txt) and read the
relevant pages for that version. The index includes versioned documentation;
select the matching major for FastMCP 3 or 4. For APIs newer than the installed
release, check that release's source or signatures. For a new project, check
the current stable release before choosing a dependency.

Use the standalone `fastmcp` package. Its API differs from
`mcp.server.fastmcp` in the Python MCP SDK.

## Author the server

Choose the MCP interface to suit what the server exposes: tools for callable
operations, resources for addressable content, and prompts for reusable message
templates. FastMCP derives tool schemas from Python annotations and descriptions;
inspect those schemas to understand what clients will see.

Let the intended client tasks guide tool boundaries, descriptions, and result
shape. Give clients enough context to use results and recover from errors.
The right granularity depends on the service; generated API tools, custom tools,
and compositions can all be appropriate.

Look up FastMCP's relevant facilities as needed: context and dependencies,
lifespan, authentication, composition, and transports. Use the project's runtime
and hosting choices to determine configuration.

Verify the server through FastMCP's `Client`, which can connect directly to a
server instance for in-process testing. Check a representative operation, its
client-visible schema and result, and a meaningful failure. Exercise the chosen
transport when connection or deployment behavior is part of the change.
