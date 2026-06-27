"""Tests for CerebrasMerger with a mocked client (no network)."""

import json
import unittest
from pathlib import Path

from weave.context.types import ChatContext, CommandRef, Decision, FileRef, TestRef
from weave.merge.cerebras import CerebrasMerger, parse_merged_response
from weave.merge.exceptions import MergeResponseError
from weave.merge.prompt import build_merge_prompt
from weave.merge.types import MergedContext

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "merge"


class FakeCerebrasClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def _sample_context_a() -> ChatContext:
    return ChatContext(
        session_id="sess-a-001",
        source_label="session-a",
        leaf_uuid="uuid-a-leaf",
        git_branch="feature-auth",
        summary="Explored JWT auth middleware.",
        decisions=[Decision(id="d1", text="Use JWT in httpOnly cookies")],
        file_refs=[FileRef(path="src/auth.py", action="edit")],
        commands=[CommandRef(command="pytest tests/test_auth.py", outcome="pass")],
        tests=[TestRef(name="test_auth", command="pytest tests/test_auth.py", outcome="pass")],
        assumptions=["Local Postgres on port 5432"],
    )


def _sample_context_b() -> ChatContext:
    return ChatContext(
        session_id="sess-b-002",
        source_label="session-b",
        leaf_uuid="uuid-b-leaf",
        git_branch="feature-auth",
        summary="Added pytest coverage for auth.",
    )


def _minimal_merged_dict() -> dict:
    data = json.loads((FIXTURES / "merged_context_minimal.json").read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


class ParseMergedResponseTests(unittest.TestCase):
    def test_parses_valid_json(self):
        payload = _minimal_merged_dict()
        merged = parse_merged_response(json.dumps(payload))
        self.assertEqual(merged.merged_summary, payload["merged_summary"])
        self.assertTrue(merged.bootstrap_prompt)

    def test_parses_json_inside_markdown_fence(self):
        payload = _minimal_merged_dict()
        raw = "```json\n" + json.dumps(payload) + "\n```"
        merged = parse_merged_response(raw)
        self.assertEqual(merged.schema_version, "1")

    def test_invalid_json_raises(self):
        with self.assertRaises(MergeResponseError) as ctx:
            parse_merged_response("not json at all")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_required_field_raises(self):
        payload = _minimal_merged_dict()
        del payload["bootstrap_prompt"]
        with self.assertRaises(MergeResponseError) as ctx:
            parse_merged_response(json.dumps(payload))
        self.assertIn("MergedContext schema", str(ctx.exception))

    def test_empty_bootstrap_prompt_raises(self):
        payload = _minimal_merged_dict()
        payload["bootstrap_prompt"] = "   "
        with self.assertRaises(MergeResponseError) as ctx:
            parse_merged_response(json.dumps(payload))
        self.assertIn("bootstrap_prompt", str(ctx.exception))


class BuildMergePromptTests(unittest.TestCase):
    def test_includes_both_contexts(self):
        a = _sample_context_a()
        b = _sample_context_b()
        prompt = build_merge_prompt(a, b)
        self.assertIn("session-a", prompt)
        self.assertIn("session-b", prompt)
        self.assertIn("Explored JWT auth middleware.", prompt)
        self.assertIn("Added pytest coverage for auth.", prompt)

    def test_includes_feedback_when_provided(self):
        prompt = build_merge_prompt(
            _sample_context_a(),
            _sample_context_b(),
            feedback="Keep session B redirect URL.",
        )
        self.assertIn("Keep session B redirect URL.", prompt)


class CerebrasMergerTests(unittest.TestCase):
    def test_merge_returns_merged_context_from_mock_response(self):
        payload = _minimal_merged_dict()
        client = FakeCerebrasClient(json.dumps(payload))
        merger = CerebrasMerger(client=client)

        merged = merger.merge(_sample_context_a(), _sample_context_b())
        expected = MergedContext.from_dict(payload)

        self.assertEqual(merged, expected)
        self.assertIsNotNone(client.last_prompt)
        self.assertIn("session-a", client.last_prompt)

    def test_merge_passes_feedback_into_prompt(self):
        payload = _minimal_merged_dict()
        client = FakeCerebrasClient(json.dumps(payload))
        merger = CerebrasMerger(client=client)

        merger.merge(
            _sample_context_a(),
            _sample_context_b(),
            feedback="Prefer session B tests.",
        )
        self.assertIn("Prefer session B tests.", client.last_prompt)

    def test_merge_sets_reprompt_feedback_when_model_omits_it(self):
        payload = _minimal_merged_dict()
        client = FakeCerebrasClient(json.dumps(payload))
        merger = CerebrasMerger(client=client)

        merged = merger.merge(
            _sample_context_a(),
            _sample_context_b(),
            feedback="Retry with B's redirect.",
        )
        self.assertEqual(merged.reprompt_feedback, "Retry with B's redirect.")

    def test_merge_raises_on_invalid_model_json(self):
        client = FakeCerebrasClient("{ broken")
        merger = CerebrasMerger(client=client)

        with self.assertRaises(MergeResponseError):
            merger.merge(_sample_context_a(), _sample_context_b())


if __name__ == "__main__":
    unittest.main()
