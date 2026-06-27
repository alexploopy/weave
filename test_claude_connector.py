"""Tests for claude_connector — no real ~/.claude is ever touched.

Run:  python3 -m unittest test_claude_connector -v
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import claude_connector as cc


class _ConnectorBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config = Path(self._tmp.name)
        patcher = mock.patch.dict(
            os.environ, {"CLAUDE_CONFIG_DIR": str(self.config)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def root(self):
        return self.config / "projects"

    def make(self, encoded_dir, session_id, text="{}\n"):
        d = self.root() / encoded_dir
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{session_id}.jsonl"
        f.write_text(text, encoding="utf-8")
        return f


class PathTests(_ConnectorBase):
    def test_projects_root_uses_config_dir_env(self):
        self.assertEqual(cc.projects_root(), self.config / "projects")

    def test_projects_root_defaults_to_home_without_env(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                cc.projects_root(), Path("~/.claude/projects").expanduser())

    def test_encode_cwd_replaces_non_alphanumeric(self):
        self.assertEqual(cc.encode_cwd("/Users/bob/myapp"), "-Users-bob-myapp")
        self.assertEqual(
            cc.encode_cwd("/Users/me/proj.test_v2"), "-Users-me-proj-test-v2")

    def test_session_path_composition(self):
        self.assertEqual(
            cc.session_path("/Users/bob/myapp", "abc-123"),
            self.config / "projects" / "-Users-bob-myapp" / "abc-123.jsonl")

    def test_errors_subclass_valueerror(self):
        self.assertTrue(issubclass(cc.SessionNotFound, ValueError))
        self.assertTrue(issubclass(cc.AmbiguousSession, ValueError))


if __name__ == "__main__":
    unittest.main()
