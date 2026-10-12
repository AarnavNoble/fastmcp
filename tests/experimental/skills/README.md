# Experimental Skills validation

This experiment targets the stable Skills extension at
`modelcontextprotocol/ext-skills@167da6c` and builds on FastMCP PR #5057.
It provides filesystem publication and standard discovery. It does not implement
host activation or the optional directory-read method.

The upstream conformance runner at
`modelcontextprotocol/conformance@c37eec888e1c6ff140af79987a40008548b7cc5f`
was run against an HTTP server with a real CRLF `SKILL.md` and supporting file:

```sh
node dist/index.js server --url http://127.0.0.1:18764/mcp \
  --scenario sep-2640-skills-enumeration --spec-version 2026-07-28 --force
node dist/index.js server --url http://127.0.0.1:18764/mcp \
  --scenario sep-2640-skills-manifest --spec-version 2026-07-28 --force
node dist/index.js server --url http://127.0.0.1:18764/mcp \
  --scenario sep-2640-skills-directory --spec-version 2026-07-28 --force
```

Enumeration passed 32 checks. Manifest validation passed five checks with one
SHOULD-level warning: resources retain FastMCP's standard `_meta.fastmcp`
metadata instead of moving it under the Skills-specific prefix. The directory
scenario passed wire validation and skipped optional directory checks because
`directoryRead` is not advertised.

Local protocol tests cover both supporting-file publication modes, nested
skills, binary data, authorization, URI aliases, resource shadowing, duplicate
identities, malformed frontmatter, cache refresh, and nonregular files. Snapshot
tests also verify duplicate YAML keys, recursive aliases, JSON-incompatible
values, raw byte digests, symlinks, and unreadable path rejection.
