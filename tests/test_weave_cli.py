"""Tests for weave.cli — no real ~/.claude is ever touched.

Run (from repo root):  python3 -m pytest tests/test_weave_cli.py -v
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
from weave.core import core as _core_mod


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
                  mock.patch.object(_core_mod.os, "getcwd", return_value=self.cwd)):
            p.start()
            self.addCleanup(p.stop)


class CliTests(CliBase):
    def test_pull_subcommand_writes_and_returns_zero(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        fake = FakeServer({("u@h:/p", "auth"):
            '{"parentUuid":null,"type":"user","uuid":"u1","cwd":"/a",'
            '"sessionId":"s","timestamp":"2026-06-26T10:00:00.000Z",'
            '"message":{"role":"user","content":"hi"}}\n'})
        with mock.patch.object(_core_mod, "_load_server", return_value=fake):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["pull", "origin", "auth"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(core.ls(cwd=self.cwd)), 1)

    def test_pull_without_remote_uses_sole_remote(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        fake = FakeServer({("u@h:/p", "auth"):
            '{"parentUuid":null,"type":"user","uuid":"u1","cwd":"/a",'
            '"sessionId":"s","timestamp":"2026-06-26T10:00:00.000Z",'
            '"message":{"role":"user","content":"hi"}}\n'})
        with mock.patch.object(_core_mod, "_load_server", return_value=fake):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli.main(["pull", "auth"])
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

    def test_merge_subcommand_prints_resume_hint(self):
        expected = _core_mod.MergeResult(
            session_id="merged-123", jsonl_path="/tmp/merged-123.jsonl",
            branch_point="bp", a_tail_len=1, b_tail_len=2)
        with mock.patch.object(core, "merge", return_value=expected) as m:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["merge", "/tmp/a.jsonl", "/tmp/b.jsonl"])
        self.assertEqual(rc, 0)
        m.assert_called_once_with("/tmp/a.jsonl", "/tmp/b.jsonl")
        self.assertIn("merged-123", out.getvalue())
        self.assertIn("claude --resume merged-123", out.getvalue())


if __name__ == "__main__":
    unittest.main()
