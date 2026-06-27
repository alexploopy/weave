"""Tests for JSONL distillation into ChatContext."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from weave.context.distill import distill_from_jsonl

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "merge"


class DistillFromJsonlTests(unittest.TestCase):
    def test_minimal_jsonl_produces_chat_context(self):
        text = (_FIXTURES / "session_a_minimal.jsonl").read_text(encoding="utf-8")
        source_path = str(_FIXTURES / "session_a_minimal.jsonl")

        result = distill_from_jsonl(
            text, source_label="a", source_path=source_path
        )

        ctx = result.context
        self.assertEqual(ctx.session_id, "sess-a-001")
        self.assertEqual(ctx.source_label, "a")
        self.assertEqual(ctx.leaf_uuid, "uuid-a-leaf")
        self.assertEqual(ctx.git_branch, "feature-auth")
        self.assertEqual(ctx.cwd, "/Users/alice/proj")
        self.assertEqual(ctx.source_path, source_path)
        self.assertIn("JWT auth middleware", ctx.summary)
        self.assertEqual(ctx.entry_count, 2)
        self.assertEqual(result.warnings, [])

    def test_malformed_line_is_skipped_with_warning(self):
        text = (
            '{"parentUuid":null,"type":"user","uuid":"u1","sessionId":"s1",'
            '"message":{"role":"user","content":"hello"}}\n'
            "not valid json\n"
            '{"parentUuid":"u1","type":"assistant","uuid":"a1","sessionId":"s1",'
            '"message":{"role":"assistant","content":"hi"}}\n'
        )
        result = distill_from_jsonl(text, source_label="a", source_path="/tmp/x.jsonl")

        self.assertEqual(result.context.session_id, "s1")
        self.assertEqual(result.context.leaf_uuid, "a1")
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("line 2", result.warnings[0])

    def test_empty_or_no_uuid_history_raises(self):
        with self.assertRaises(ValueError) as ctx:
            distill_from_jsonl("", source_label="a", source_path="/tmp/empty.jsonl")
        self.assertIn("no uuid-bearing chat history", str(ctx.exception))

        meta_only = '{"type":"mode","mode":"default"}\n'
        with self.assertRaises(ValueError):
            distill_from_jsonl(
                meta_only, source_label="a", source_path="/tmp/meta.jsonl"
            )


if __name__ == "__main__":
    unittest.main()
