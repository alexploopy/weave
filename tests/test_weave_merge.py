"""Tests for weave.core transcript-level merge.

Run (from repo root):  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_weave_merge.py -q
"""

import unittest

from weave.core import core as _core


def _user(uuid, text, *, sid="s", cwd="/a", ts="2026-06-26T10:00:00.000Z"):
    return {
        "parentUuid": None, "type": "user", "uuid": uuid,
        "sessionId": sid, "cwd": cwd, "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _assistant(uuid, text, *, sid="s", cwd="/a", ts="2026-06-26T10:00:01.000Z"):
    return {
        "parentUuid": None, "type": "assistant", "uuid": uuid,
        "sessionId": sid, "cwd": cwd, "timestamp": ts,
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


class EntryKeyTests(unittest.TestCase):
    def test_same_content_different_identity_matches(self):
        a = _user("uuid-a", "hello", sid="alice", cwd="/Users/alice/p")
        b = _user("uuid-b", "hello", sid="bob", cwd="/Users/bob/p",
                  ts="2026-06-27T00:00:00.000Z")
        self.assertEqual(_core._entry_key(a), _core._entry_key(b))

    def test_different_content_differs(self):
        a = _user("uuid-a", "hello")
        b = _user("uuid-b", "goodbye")
        self.assertNotEqual(_core._entry_key(a), _core._entry_key(b))

    def test_tool_ids_are_ignored(self):
        a = {"type": "assistant", "uuid": "1", "message": {"role": "assistant",
             "content": [{"type": "tool_use", "id": "toolu_AAA", "name": "Read",
                          "input": {"file_path": "x"}}]}}
        b = {"type": "assistant", "uuid": "2", "message": {"role": "assistant",
             "content": [{"type": "tool_use", "id": "toolu_BBB", "name": "Read",
                          "input": {"file_path": "x"}}]}}
        self.assertEqual(_core._entry_key(a), _core._entry_key(b))


class SplitAtBranchTests(unittest.TestCase):
    def test_shared_then_branch(self):
        a = [_user("a1", "shared-1"), _assistant("a2", "shared-2"), _user("a3", "A-only")]
        b = [_user("b1", "shared-1"), _assistant("b2", "shared-2"), _user("b3", "B-only")]
        bp, a_tail, b_tail = _core._split_at_branch(a, b)
        self.assertEqual(bp, "a2")
        self.assertEqual([e["uuid"] for e in a_tail], ["a3"])
        self.assertEqual([e["uuid"] for e in b_tail], ["b3"])

    def test_no_shared_prefix(self):
        a = [_user("a1", "A-start")]
        b = [_user("b1", "B-start")]
        bp, a_tail, b_tail = _core._split_at_branch(a, b)
        self.assertIsNone(bp)
        self.assertEqual(len(a_tail), 1)
        self.assertEqual(len(b_tail), 1)

    def test_a_is_prefix_of_b(self):
        a = [_user("a1", "shared-1")]
        b = [_user("b1", "shared-1"), _user("b2", "B-extra")]
        bp, a_tail, b_tail = _core._split_at_branch(a, b)
        self.assertEqual(bp, "a1")
        self.assertEqual(a_tail, [])
        self.assertEqual([e["uuid"] for e in b_tail], ["b2"])

    def test_identical(self):
        a = [_user("a1", "shared-1"), _assistant("a2", "shared-2")]
        b = [_user("b1", "shared-1"), _assistant("b2", "shared-2")]
        bp, a_tail, b_tail = _core._split_at_branch(a, b)
        self.assertEqual(bp, "a2")
        self.assertEqual(a_tail, [])
        self.assertEqual(b_tail, [])


if __name__ == "__main__":
    unittest.main()
