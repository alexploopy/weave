"""Tests for weave.cli — no real ~/.claude is ever touched.

Run (from repo root):  python3 -m unittest tests.test_weave_cli -v
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from weave import cli, config, core
from weave.config import config as _config_mod


class FakeServer:
    def __init__(self, store=None):
        self.store = dict(store or {})

    def push(self, url, name, text):
        self.store[(url, name)] = text

    def pull(self, url, name):
        return self.store[(url, name)]

    def list(self, url):
        return [n for (u, n) in self.store if u == url]


class CliBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        patcher = mock.patch.dict(
            os.environ, {"CLAUDE_CONFIG_DIR": str(self.tmp / "claude")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = self.tmp / ".weave" / "config"
        self.cwd = "/Users/tester/proj"
        # Redirect core defaults at their definition site.
        for p in (mock.patch.object(_config_mod, "DEFAULT_PATH", str(self.cfg)),
                  mock.patch.object(core.os, "getcwd", return_value=self.cwd)):
            p.start()
            self.addCleanup(p.stop)


class CliTests(CliBase):
    def test_pull_subcommand_writes_and_returns_zero(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        fake = FakeServer({("u@h:/p", "auth"):
            '{"parentUuid":null,"type":"user","uuid":"u1","cwd":"/a",'
            '"sessionId":"s","timestamp":"2026-06-26T10:00:00.000Z",'
            '"message":{"role":"user","content":"hi"}}\n'})
        with mock.patch.object(core, "_load_server", return_value=fake):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["pull", "origin", "auth"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(core.ls(cwd=self.cwd)), 1)

    def test_unknown_remote_exits_1_with_message(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["pull", "nope", "x"])
        self.assertEqual(rc, 1)
        self.assertIn("weave:", err.getvalue())

    def test_remote_add_subcommand(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["remote", "add", "origin", "u@h:/p"])
        self.assertEqual(rc, 0)
        self.assertEqual(config.get_remote("origin", path=self.cfg), "u@h:/p")

    def test_merge_subcommand_prints_sidecar_path(self):
        sidecar = self.tmp / "merged" / "test-merge.json"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text("{}", encoding="utf-8")
        expected = core.MergeResult(
            merge_id="test-merge",
            sidecar_path=str(sidecar),
            source_a_path=str(self.tmp / "a.jsonl"),
            source_b_path=str(self.tmp / "b.jsonl"),
        )
        with mock.patch.object(core, "merge_contexts", return_value=expected):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(
                    [
                        "merge",
                        str(self.tmp / "a.jsonl"),
                        str(self.tmp / "b.jsonl"),
                        "--output-dir",
                        str(self.tmp / "merged"),
                    ]
                )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), str(sidecar))


if __name__ == "__main__":
    unittest.main()
