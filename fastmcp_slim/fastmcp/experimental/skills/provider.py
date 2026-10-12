"""Filesystem publication for the experimental MCP Skills extension."""

from __future__ import annotations

import mimetypes
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, unquote

import yaml
from anyio.to_thread import run_sync
from mcp.server.context import ServerRequestContext
from mcp.shared.path_security import PathEscapeError, safe_join
from pydantic import AnyUrl

from fastmcp.experimental.skills._resources import SkillFileResource, SkillFileTemplate
from fastmcp.experimental.skills._snapshot import Snapshot, snapshot
from fastmcp.resources.base import Resource
from fastmcp.resources.template import ResourceTemplate
from fastmcp.server.dependencies import get_context
from fastmcp.server.providers.base import Provider
from fastmcp.skills.models import Skill
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.versions import VersionSpec

logger = get_logger(__name__)


class SkillsDirectoryProvider(Provider):
    """Publish strict filesystem skills as Resources and Skills entries.

    Each directory containing `SKILL.md` beneath a configured root is a skill,
    including nested directories. Its root-relative path becomes its `skill://`
    namespace. Files are read live; discovery computes fresh manifests.

    Args:
        roots: Directories containing skill directories.
        supporting_files: Publish supporting files individually or through templates.
    """

    def __init__(
        self,
        roots: str | Path | Sequence[str | Path],
        *,
        supporting_files: Literal["template", "resources"] = "template",
    ) -> None:
        super().__init__()
        if isinstance(roots, (str, Path)):
            roots = [roots]
        self._roots = tuple(Path(root).absolute() for root in roots)
        self._supporting_files = supporting_files

    def _candidate_directories(self) -> list[tuple[str, Path]]:
        candidates: list[tuple[str, Path]] = []
        for root in self._roots:
            if root.is_symlink():
                logger.warning("Ignoring symlink Skills root: %s", root)
                continue
            if not root.is_dir():
                continue
            for main in sorted(root.rglob("SKILL.md")):
                directory = main.parent
                if directory == root:
                    continue
                if any(
                    p.is_symlink()
                    for p in (directory, *directory.parents)
                    if p == root or root in p.parents
                ):
                    continue
                candidates.append((directory.relative_to(root).as_posix(), directory))
        return candidates

    def _directories(self) -> list[tuple[str, Path]]:
        candidates = self._candidate_directories()
        counts = Counter(name for name, _ in candidates)
        for name, count in counts.items():
            if count > 1:
                logger.warning("Omitting duplicate skill path: %s", name)
        return [(name, path) for name, path in candidates if counts[name] == 1]

    def _snapshots(self) -> list[Snapshot]:
        snapshots: list[Snapshot] = []
        for name, path in self._directories():
            try:
                snapshots.append(snapshot(path, name))
            except (OSError, ValueError, yaml.YAMLError, RecursionError) as exc:
                logger.warning("Omitting invalid skill %s: %s", path, exc)
        return snapshots

    def _resource(
        self, uri: str, path: Path, root: Path, entry: Skill
    ) -> SkillFileResource:
        is_main = uri == entry.uri
        return SkillFileResource(
            uri=AnyUrl(uri),
            name=entry.frontmatter.name if is_main else path.name,
            description=entry.frontmatter.description if is_main else None,
            mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            root=root,
            relative_path=path.relative_to(root).as_posix(),
        )

    async def _list_resources(self) -> Sequence[Resource]:
        snapshots = await run_sync(self._snapshots)
        resources: dict[str, Resource] = {}
        for snap in snapshots:
            root = next(
                path.parent for uri, path in snap.files if uri == snap.entry.uri
            )
            for uri, path in snap.files:
                if uri == snap.entry.uri or self._supporting_files == "resources":
                    resources[uri] = self._resource(uri, path, root, snap.entry)
        return list(resources.values())

    def _directories_for_name(self, name: str) -> list[Path]:
        directories = []
        for root in self._roots:
            try:
                directory = safe_join(root, name)
            except (PathEscapeError, OSError, RuntimeError):
                continue
            lexical = root / name
            if any(
                path.is_symlink()
                for path in (lexical, *lexical.parents)
                if path == root or root in path.parents
            ):
                continue
            if (directory / "SKILL.md").is_file():
                directories.append(lexical)
        return directories

    def _uri_parts(self, uri: str) -> list[str] | None:
        if not uri.startswith("skill://"):
            return None
        encoded = uri[len("skill://") :]
        decoded = unquote(encoded)
        parts = decoded.split("/")
        if (
            quote(decoded, safe="/") != encoded
            or len(parts) < 2
            or any(part in {"", ".", ".."} for part in parts)
            or "\\" in decoded
        ):
            return None
        return parts

    def _resolve_file(self, uri: str) -> tuple[Path, str] | None:
        parts = self._uri_parts(uri)
        if parts is None:
            return None
        for length in range(len(parts) - 1, 0, -1):
            directories = self._directories_for_name("/".join(parts[:length]))
            if len(directories) > 1:
                return None
            if directories:
                return directories[0], "/".join(parts[length:])
        return None

    async def _get_resource(
        self, uri: str, version: VersionSpec | None = None
    ) -> Resource | None:
        resolved = self._resolve_file(uri)
        if resolved is None:
            return None
        root, relative = resolved
        if relative != "SKILL.md" and self._supporting_files != "resources":
            return None
        path = root / relative
        if not path.is_file():
            return None
        return SkillFileResource(
            uri=AnyUrl(uri),
            name=root.name if relative == "SKILL.md" else path.name,
            mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            root=root,
            relative_path=relative,
        )

    async def _list_resource_templates(self) -> Sequence[ResourceTemplate]:
        if self._supporting_files != "template":
            return []
        return [
            SkillFileTemplate(
                uri_template=f"skill://{quote(name, safe='/')}/{{path*}}",
                name=f"{root.name}_files",
                root=root,
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            )
            for name, root in self._directories()
        ]

    async def _get_resource_template(
        self, uri: str, version: VersionSpec | None = None
    ) -> ResourceTemplate | None:
        if self._supporting_files != "template":
            return None
        resolved = self._resolve_file(uri)
        if resolved is None:
            return None
        root, relative = resolved
        if relative == "SKILL.md":
            return None
        prefix = uri[: -len(quote(relative, safe="/"))]
        return SkillFileTemplate(
            uri_template=f"{prefix}{{path*}}",
            name=f"{root.name}_files",
            root=root,
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )

    async def _visible_entry(self, snap: Snapshot) -> Skill | None:
        server = get_context().fastmcp
        for uri, path in snap.files:
            resource = await server.get_resource(uri)
            if resource is not None:
                if (
                    not isinstance(resource, SkillFileResource)
                    or resource.root / resource.relative_path != path
                ):
                    return None
                continue
            template = await server.get_resource_template(uri)
            if not isinstance(template, SkillFileTemplate):
                return None
            params = template.matches(uri)
            if params is None or template.root / params["path"] != path:
                return None
        return snap.entry

    async def _list_skill_entries(
        self, context: ServerRequestContext[Any, Any]
    ) -> Sequence[Skill]:
        entries = []
        for snap in await run_sync(self._snapshots):
            entry = await self._visible_entry(snap)
            if entry is not None:
                entries.append(entry)
        return entries

    async def _get_skill_entry(
        self, uri: str, context: ServerRequestContext[Any, Any]
    ) -> Skill | None:
        parts = self._uri_parts(uri)
        if parts is None or parts[-1] != "SKILL.md":
            return None
        name = "/".join(parts[:-1])
        directories = self._directories_for_name(name)
        if len(directories) != 1:
            return None
        try:
            snap = await run_sync(snapshot, directories[0], name)
        except (OSError, ValueError, yaml.YAMLError, RecursionError) as exc:
            logger.warning("Omitting invalid skill %s: %s", directories[0], exc)
            return None
        return await self._visible_entry(snap)

    def claims_uri(self, uri: str) -> bool:
        parts = self._uri_parts(uri)
        return parts is not None and any(
            self._directories_for_name("/".join(parts[:length]))
            for length in range(len(parts) - 1, 0, -1)
        )
