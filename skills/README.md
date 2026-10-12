# FastMCP skills

These are user-facing skills for agents working with FastMCP. Repository
maintenance skills live separately in `.agents/skills/`.

- [Server authoring](fastmcp-server/SKILL.md): build and test Python MCP servers,
  with version-aware API retrieval and practical interface and lifecycle idioms.
- [Client CLI](fastmcp-client-cli/SKILL.md): discover and call existing servers.

## skillz.supply publication

The `Publish authoring skill` workflow publishes `fastmcp-server` on relevant
`main` changes as `gofastmcp.com` (`did:plc:fkndnffqehgkbuahbysm3d4w`). It does
not publish maintenance skills or the client CLI skill. Git remains the source;
skillz.supply carries the skill body, metadata, and a link back to its source.

PRs run a public, unauthenticated comparison. Publishing
requires the repository's `SKILLZ_APP_PASSWORD` Actions secret, an app password
for the publishing account. Never place that value in repository files.
Manual runs default to dry-run; publishing runs require `main`. Superseded publication
source is skipped (unrelated commits do not suppress publishing), and AT Protocol commit comparison rejects concurrent
account changes rather than overwriting them. Rerun on current `main` after
inspecting a conflict.

```bash
uv run .github/scripts/publish_skillz.py --dry-run
```

The publisher creates or updates `supply.skillz.skill/fastmcp.fastmcp-server`,
preserves its creation time, skips unchanged content, and refuses a record
owned by a different source URL. It never deletes listings. Removing the source
requires an explicit listing-retirement decision.
