from pathlib import Path

import pytest

from fastmcp import Client, FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider
from fastmcp.skills.extension import SkillsExtension


@pytest.mark.parametrize("explicit_default", [False, True])
async def test_default_provider_keeps_legacy_publication(
    tmp_path: Path, explicit_default: bool
):
    root = tmp_path / "review"
    root.mkdir()
    (root / "SKILL.md").write_bytes(b"# No frontmatter\r\nLoose instructions\r\n")
    kwargs = {"experimental_skills": False} if explicit_default else {}
    provider = SkillsDirectoryProvider(tmp_path, **kwargs)
    server = FastMCP("Legacy skills", providers=[provider])
    async with Client(server) as client:
        resources = await client.list_resources()
        assert {str(resource.uri) for resource in resources} == {
            "skill://review/SKILL.md",
            "skill://review/_manifest",
        }
        contents = await client.read_resource("skill://review/SKILL.md")
        assert contents[0].text == "# No frontmatter\nLoose instructions\n"
        assert client.server_capabilities is not None
        assert "io.modelcontextprotocol/skills" not in (
            client.server_capabilities.extensions or {}
        )
    with pytest.raises(ValueError, match="experimental_skills=True"):
        server.add_extension(SkillsExtension(providers=[provider]))


def test_experimental_mode_requires_standard_main_file(tmp_path: Path):
    with pytest.raises(ValueError, match="main_file_name"):
        SkillsDirectoryProvider(
            tmp_path, main_file_name="README.md", experimental_skills=True
        )
