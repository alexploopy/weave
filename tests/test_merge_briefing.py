"""Tests for the pure text-briefing merge layer.

Run (from repo root):  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_merge_briefing.py -q
"""

import unittest

from weave.context.types import ChatContext
from weave.merge.briefing import (
    BriefingMerger,
    StubBriefingMerger,
    build_briefing_prompt,
)
from weave.merge.exceptions import MergeResponseError


def _ctx(summary):
    return ChatContext(
        session_id="s", source_label="shared", leaf_uuid="u",
        git_branch=None, summary=summary,
    )


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None

    def complete(self, prompt):
        self.last_prompt = prompt
        return self.response


_A_BRANCH = [{"type": "user", "uuid": "a1",
              "message": {"role": "user", "content": "A did this"}}]
_B_BRANCH = [{"type": "user", "uuid": "b1",
              "message": {"role": "user", "content": "B did that"}}]


class StubBriefingMergerTests(unittest.TestCase):
    def test_returns_text_mentioning_branch_sizes(self):
        out = StubBriefingMerger().merge(_ctx("background"), _A_BRANCH, _B_BRANCH)
        self.assertIsInstance(out, str)
        self.assertIn("background", out)
        self.assertIn("1", out)  # one turn per branch

    def test_handles_no_shared_context(self):
        out = StubBriefingMerger().merge(None, _A_BRANCH, _B_BRANCH)
        self.assertIsInstance(out, str)
        self.assertTrue(out.strip())


class BriefingMergerTests(unittest.TestCase):
    def test_returns_stripped_client_text(self):
        client = _FakeClient("  MERGED BRIEFING  ")
        out = BriefingMerger(client=client).merge(_ctx("bg"), _A_BRANCH, _B_BRANCH)
        self.assertEqual(out, "MERGED BRIEFING")

    def test_prompt_includes_branch_content(self):
        client = _FakeClient("ok")
        BriefingMerger(client=client).merge(_ctx("bg"), _A_BRANCH, _B_BRANCH)
        self.assertIn("A did this", client.last_prompt)
        self.assertIn("B did that", client.last_prompt)

    def test_empty_response_raises(self):
        client = _FakeClient("   ")
        with self.assertRaises(MergeResponseError):
            BriefingMerger(client=client).merge(_ctx("bg"), _A_BRANCH, _B_BRANCH)


class BuildBriefingPromptTests(unittest.TestCase):
    def test_no_shared_context_is_labeled(self):
        prompt = build_briefing_prompt(None, _A_BRANCH, _B_BRANCH)
        self.assertIn("none", prompt.lower())
        self.assertIn("A did this", prompt)


if __name__ == "__main__":
    unittest.main()
