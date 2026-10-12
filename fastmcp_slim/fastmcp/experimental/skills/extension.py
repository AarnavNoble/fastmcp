"""Opt-in filesystem integration for the Skills extension."""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import quote

from mcp.server.context import ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_PARAMS

from fastmcp.experimental.skills.provider import SkillsDirectoryProvider
from fastmcp.server.context import Context
from fastmcp.skills.extension import SkillsExtension as BaseSkillsExtension
from fastmcp.skills.models import (
    GetSkillParams,
    GetSkillResult,
    ListSkillsParams,
    ListSkillsResult,
)


class SkillsExtension(BaseSkillsExtension):
    """Experimental filesystem Skills discovery through ordinary Resources.

    Pair with the experimental `SkillsDirectoryProvider`. Host-side skill
    activation, approval, and code execution are outside this extension.
    """

    def _colliding_uris(self) -> set[str]:
        counts = Counter(
            f"skill://{quote(name, safe='/')}/SKILL.md"
            for provider in self._providers
            if isinstance(provider, SkillsDirectoryProvider)
            for name, _ in provider._candidate_directories()
        )
        return {uri for uri, count in counts.items() if count > 1}

    def owns_resource_uri(self, uri: str) -> bool:
        return any(
            isinstance(provider, SkillsDirectoryProvider) and provider.claims_uri(uri)
            for provider in self._providers
        )

    async def _handle_list(
        self, context: ServerRequestContext[Any, Any], params: ListSkillsParams
    ) -> ListSkillsResult:
        async with Context(fastmcp=self.server):
            collisions = self._colliding_uris()
            result = await super()._handle_list(context, params)
            return result.model_copy(
                update={
                    "skills": [
                        entry for entry in result.skills if entry.uri not in collisions
                    ]
                }
            )

    async def _handle_get(
        self, context: ServerRequestContext[Any, Any], params: GetSkillParams
    ) -> GetSkillResult:
        async with Context(fastmcp=self.server):
            matches = 0
            for provider in self._providers:
                if not isinstance(provider, SkillsDirectoryProvider):
                    continue
                parts = provider._uri_parts(params.uri)
                if parts is not None and parts[-1] == "SKILL.md":
                    matches += len(provider._directories_for_name("/".join(parts[:-1])))
            if matches > 1:
                raise MCPError(
                    code=INVALID_PARAMS, message=f"Unknown skill URI: {params.uri}"
                )
            return await super()._handle_get(context, params)
