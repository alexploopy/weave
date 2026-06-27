"""Tests for weave.core — no real ~/.claude is ever touched.

Run (from repo root):  python3 -m unittest discover -s tests -t .
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import claude_connector_api as cc
from weave import core


class _WeaveBase(unittest.TestCase):
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


class ConfigTests(_WeaveBase):
    def test_remote_add_writes_url(self):
        core.remote_add("origin", "user@host:/srv/weave", path=self.cfg)
        self.assertEqual(
            core._remote_url("origin", path=self.cfg), "user@host:/srv/weave")

    def test_remote_add_updates_existing(self):
        core.remote_add("origin", "user@host:/old", path=self.cfg)
        core.remote_add("origin", "user@host:/new", path=self.cfg)
        self.assertEqual(
            core._remote_url("origin", path=self.cfg), "user@host:/new")

    def test_unknown_remote_raises(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        with self.assertRaises(ValueError):
            core._remote_url("missing", path=self.cfg)


class FakeServer:
    """In-memory stand-in for the future `server` module."""
    def __init__(self, store=None):
        self.store = dict(store or {})
        self.pushed = []  # (url, name, text)

    def push(self, url, name, text):
        self.pushed.append((url, name, text))
        self.store[(url, name)] = text

    def pull(self, url, name):
        if (url, name) not in self.store:
            raise ValueError(f"no session {name!r} on remote")
        return self.store[(url, name)]

    def list(self, url):
        return [n for (u, n) in self.store if u == url]


class PushTests(_WeaveBase):
    def _seed_session(self, session_id, text):
        cc.write_text(cc.session_path(self.cwd, session_id), text)

    def test_push_sends_exact_bytes(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        self._seed_session("sess-1", '{"uuid":"x"}\n')
        fake = FakeServer()
        core.push("origin", "auth-refactor", "sess-1",
                  server=fake, config_path=self.cfg)
        self.assertEqual(
            fake.pushed, [("u@h:/p", "auth-refactor", '{"uuid":"x"}\n')])

    def test_push_unknown_session_raises(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        with self.assertRaises(ValueError):
            core.push("origin", "n", "missing-id",
                      server=FakeServer(), config_path=self.cfg)


class RewriteAndPullTests(_WeaveBase):
    def test_rewrite_for_local_sets_cwd_and_sessionid(self):
        entries = [{"uuid": "a", "cwd": "/old", "sessionId": "old"},
                   {"uuid": "b", "cwd": "/old", "sessionId": "old"}]
        out = core._rewrite_for_local(entries, "new-id", "/Users/me/proj")
        for e in out:
            self.assertEqual(e["cwd"], "/Users/me/proj")
            self.assertEqual(e["sessionId"], "new-id")
        self.assertEqual(entries[0]["cwd"], "/old")  # input not mutated

    def test_pull_writes_fresh_local_session(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        remote_text = (
            '{"parentUuid":null,"type":"user","uuid":"u1",'
            '"cwd":"/Users/alice/proj","sessionId":"alice-sess",'
            '"timestamp":"2026-06-26T10:00:00.000Z",'
            '"message":{"role":"user","content":"hi"}}\n')
        fake = FakeServer({("u@h:/p", "auth"): remote_text})
        new_id = core.pull("origin", "auth", cwd=self.cwd,
                           server=fake, config_path=self.cfg)
        path = cc.session_path(self.cwd, new_id)
        self.assertTrue(path.is_file())
        entries = [json.loads(l) for l in
                   path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertTrue(entries)
        for e in entries:
            self.assertEqual(e["cwd"], self.cwd)
            self.assertEqual(e["sessionId"], new_id)

    def test_pull_empty_history_raises_before_writing(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        fake = FakeServer({("u@h:/p", "empty"): "\n"})
        before = set(cc.list_sessions())
        with self.assertRaises(ValueError):
            core.pull("origin", "empty", cwd=self.cwd,
                      server=fake, config_path=self.cfg)
        self.assertEqual(set(cc.list_sessions()), before)  # nothing written


class LsTests(_WeaveBase):
    def test_ls_local_filters_to_cwd(self):
        cc.write_text(cc.session_path(self.cwd, "mine-1"), "{}\n")
        cc.write_text(cc.session_path(self.cwd, "mine-2"), "{}\n")
        cc.write_text(cc.session_path("/Users/tester/other", "elsewhere"),
                      "{}\n")
        ids = core.ls(cwd=self.cwd)
        self.assertEqual(set(ids), {"mine-1", "mine-2"})

    def test_ls_remote_delegates_to_server(self):
        core.remote_add("origin", "u@h:/p", path=self.cfg)
        fake = FakeServer({("u@h:/p", "a"): "x", ("u@h:/p", "b"): "y"})
        self.assertEqual(
            set(core.ls("origin", server=fake, config_path=self.cfg)),
            {"a", "b"})


if __name__ == "__main__":
    unittest.main()
