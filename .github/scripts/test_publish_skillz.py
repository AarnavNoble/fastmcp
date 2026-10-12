# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML==6.0.2", "atproto==0.0.72"]
# ///
"""Exercise the publisher with real Git and an HTTP AT Protocol fixture."""

import base64
import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from atproto import Client
from atproto.exceptions import AtProtocolError

spec = importlib.util.spec_from_file_location(
    "publish_skillz", Path(__file__).with_name("publish_skillz.py")
)
assert spec and spec.loader
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def token(did: str) -> str:
    payload = {"sub": did, "exp": int(time.time()) + 3600, "iat": int(time.time())}
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"e30.{encoded}.c2lnbmF0dXJl"


class PublishingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.previous_root = publisher.ROOT
        publisher.ROOT = self.root
        self.addCleanup(setattr, publisher, "ROOT", self.previous_root)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        skill = self.root / "skills/fastmcp-server/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: fastmcp-server\ndescription: Build servers.\n---\nBody.\n"
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        self.record = publisher.skill_record("fastmcp-server")
        self.records: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []
        self.commit = "baseline"
        self.identity = publisher.DID
        self.concurrent_write = False
        self.fixture = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.thread = threading.Thread(target=self.fixture.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.client = Client(f"http://127.0.0.1:{self.fixture.server_port}")
        self.previous_password = os.environ.get("SKILLZ_APP_PASSWORD")
        os.environ["SKILLZ_APP_PASSWORD"] = "fixture-only"
        self.addCleanup(self.restore_password)

    def restore_password(self) -> None:
        if self.previous_password is None:
            os.environ.pop("SKILLZ_APP_PASSWORD", None)
        else:
            os.environ["SKILLZ_APP_PASSWORD"] = self.previous_password

    def stop_server(self) -> None:
        self.fixture.shutdown()
        self.fixture.server_close()
        self.thread.join()

    def handler(self) -> type[BaseHTTPRequestHandler]:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def reply(self, body: dict[str, Any], status: int = 200) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                method = self.path.split("?", 1)[0].rsplit("/", 1)[1]
                fixture.calls.append(method)
                if method == "com.atproto.sync.getLatestCommit":
                    self.reply({"cid": fixture.commit, "rev": "revision"})
                elif method == "com.atproto.repo.listRecords":
                    records = [
                        {
                            "uri": f"at://{publisher.DID}/{publisher.COLLECTION}/{key}",
                            "cid": "record-cid",
                            "value": value,
                        }
                        for key, value in fixture.records.items()
                    ]
                    self.reply({"records": records})
                elif method == "com.atproto.server.getSession":
                    self.reply({"did": fixture.identity, "handle": "gofastmcp.com"})
                else:
                    self.reply({"error": "UnknownMethod"}, 400)

            def do_POST(self) -> None:
                method = self.path.rsplit("/", 1)[1]
                fixture.calls.append(method)
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if method == "com.atproto.server.createSession":
                    if fixture.concurrent_write:
                        fixture.commit = "concurrent"
                    self.reply(
                        {
                            "did": fixture.identity,
                            "handle": "gofastmcp.com",
                            "accessJwt": token(fixture.identity),
                            "refreshJwt": token(fixture.identity),
                        }
                    )
                elif method == "com.atproto.repo.applyWrites":
                    if body["swapCommit"] != fixture.commit:
                        self.reply(
                            {"error": "InvalidSwap", "message": "Concurrent write"}, 400
                        )
                        return
                    for write in body["writes"]:
                        fixture.records[write["rkey"]] = write["value"]
                    self.reply({"commit": {"cid": "next", "rev": "next"}})
                else:
                    self.reply({"error": "UnknownMethod"}, 400)

        return Handler

    def test_create_noop_update_preserves_creation_and_unrelated_records(self) -> None:
        self.records["unrelated"] = {"body": "untouched"}
        self.assertEqual(publisher.publish(self.client, [self.record]), 1)
        key = "fastmcp.fastmcp-server"
        created = self.records[key]["createdAt"]
        self.calls.clear()
        self.assertEqual(publisher.publish(self.client, [self.record]), 0)
        self.assertNotIn("com.atproto.server.createSession", self.calls)
        self.assertNotIn("com.atproto.repo.applyWrites", self.calls)
        updated = {**self.record, "body": "Updated.\n"}
        self.assertEqual(publisher.publish(self.client, [updated]), 1)
        self.assertEqual(self.records[key]["body"], "Updated.\n")
        self.assertEqual(self.records[key]["createdAt"], created)
        self.assertEqual(self.records["unrelated"], {"body": "untouched"})

    def test_dry_run_does_not_authenticate_or_write(self) -> None:
        os.environ.pop("SKILLZ_APP_PASSWORD")
        self.assertEqual(publisher.publish(self.client, [self.record], True), 1)
        self.assertEqual(self.records, {})
        self.assertNotIn("com.atproto.server.createSession", self.calls)

    def test_collision_and_wrong_identity_do_not_write(self) -> None:
        self.records["fastmcp.fastmcp-server"] = {"repoUrl": "https://other.example"}
        before = copy.deepcopy(self.records)
        with self.assertRaisesRegex(ValueError, "another source"):
            publisher.publish(self.client, [self.record])
        self.assertEqual(before, self.records)
        self.records.clear()
        self.identity = "did:plc:other"
        with self.assertRaisesRegex(ValueError, "wrong DID"):
            publisher.publish(self.client, [self.record])
        self.assertNotIn("com.atproto.repo.applyWrites", self.calls)

    def test_missing_credential_does_not_write(self) -> None:
        os.environ.pop("SKILLZ_APP_PASSWORD")
        with self.assertRaisesRegex(ValueError, "required"):
            publisher.publish(self.client, [self.record])
        self.assertEqual(self.records, {})

    def test_concurrent_change_is_not_overwritten(self) -> None:
        self.concurrent_write = True
        with self.assertRaises(AtProtocolError):
            publisher.publish(self.client, [self.record])
        self.assertEqual(self.records, {})

    def test_only_explicit_tracked_skill_is_selected(self) -> None:
        private = self.root / ".agents/skills/private/SKILL.md"
        private.parent.mkdir(parents=True)
        private.write_text("private")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        self.assertEqual(publisher.tracked_skills(), ["fastmcp-server"])
        source = self.root / "skills/fastmcp-server/SKILL.md"
        source.unlink()
        source.symlink_to(private)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            publisher.tracked_skills()
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        with self.assertRaisesRegex(ValueError, "regular tracked"):
            publisher.tracked_skills()

    def test_freshness_ignores_unrelated_commits_but_rejects_changed_skill(
        self,
    ) -> None:
        def git(*args: str) -> None:
            subprocess.run(
                ["git", *args], cwd=self.root, check=True, capture_output=True
            )

        git("config", "user.email", "fixture@example.test")
        git("config", "user.name", "Fixture")
        git("commit", "-qm", "initial")
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        remote = self.root / "remote.git"
        git("init", "--bare", str(remote))
        git("remote", "add", "origin", str(remote))
        git("push", "origin", "HEAD:main")
        self.assertTrue(publisher.source_is_current())
        (self.root / "unrelated.txt").write_text("unrelated")
        git("add", "unrelated.txt")
        git("commit", "-qm", "unrelated")
        git("push", "origin", "HEAD:main")
        git("checkout", "--detach", revision)
        self.assertTrue(publisher.source_is_current())
        git("checkout", "--detach", "FETCH_HEAD")
        source = self.root / "skills/fastmcp-server/SKILL.md"
        source.write_text(source.read_text() + "changed")
        git("add", "skills")
        git("commit", "-qm", "changed skill")
        git("push", "origin", "HEAD:main")
        git("checkout", "--detach", revision)
        self.assertFalse(publisher.source_is_current())

    def test_frontmatter_and_limits_reject_bad_source(self) -> None:
        source = self.root / "skills/fastmcp-server/SKILL.md"
        for text in (
            "body only",
            "---\nname: other\n---\nbody",
            "---\nname: fastmcp-server\ndescription: ''\n---\nbody",
        ):
            source.write_text(text)
            with self.assertRaises(ValueError):
                publisher.skill_record("fastmcp-server")


if __name__ == "__main__":
    unittest.main()
