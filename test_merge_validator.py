"""Tests for merged-context validation."""

import json
import unittest
from pathlib import Path

from weave.context.types import (
    ChatContext,
    CommandRef,
    Decision,
    FileRef,
    TestRef,
    TodoItem,
)
from weave.merge.cerebras import CerebrasMerger
from weave.merge.exceptions import MergeResponseError
from weave.merge.stub import StubMerger
from weave.merge.types import MergedContext, MergedDecision, SourceRef
from weave.merge.validator import validate_merged_context

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "merge"


class FakeCerebrasClient:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, prompt: str) -> str:
        return self.response


def _context_a(*, git_branch: str | None = "feature-auth") -> ChatContext:
    return ChatContext(
        session_id="sess-a-001",
        source_label="session-a",
        leaf_uuid="uuid-a-leaf",
        git_branch=git_branch,
        summary="Explored JWT auth middleware.",
        decisions=[Decision(id="d1", text="Use JWT in httpOnly cookies")],
        file_refs=[FileRef(path="src/auth.py", action="edit")],
        commands=[CommandRef(command="pytest tests/test_auth.py", outcome="pass")],
        tests=[TestRef(name="test_auth", command="pytest tests/test_auth.py", outcome="pass")],
        todos=[TodoItem(text="Add refresh token rotation", status="open")],
        assumptions=["Local Postgres on port 5432"],
    )


def _context_b(*, git_branch: str | None = "feature-auth") -> ChatContext:
    return ChatContext(
        session_id="sess-b-002",
        source_label="session-b",
        leaf_uuid="uuid-b-leaf",
        git_branch=git_branch,
        summary="Added pytest coverage for auth.",
        decisions=[Decision(id="d2", text="Use JWT in httpOnly cookies")],
    )


def _valid_merged_dict() -> dict:
    data = json.loads((FIXTURES / "merged_context_minimal.json").read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


def _valid_merged() -> MergedContext:
    return MergedContext.from_dict(_valid_merged_dict())


def _merged_with_branch_mismatch_contexts() -> MergedContext:
    merged = _valid_merged()
    merged.sources = [
        SourceRef(
            side="a",
            source_label="session-a",
            session_id="sess-a-001",
            git_branch="feature-auth",
            leaf_uuid="uuid-a-leaf",
        ),
        SourceRef(
            side="b",
            source_label="session-b",
            session_id="sess-b-002",
            git_branch="feature-login",
            leaf_uuid="uuid-b-leaf",
        ),
    ]
    return merged


class ValidateMergedContextTests(unittest.TestCase):
    def test_valid_output_passes(self):
        validate_merged_context(_valid_merged(), _context_a(), _context_b())

    def test_invented_file_raises(self):
        merged = _valid_merged()
        merged.file_refs = [FileRef(path="src/invented.py", action="edit")]
        with self.assertRaises(MergeResponseError) as ctx:
            validate_merged_context(merged, _context_a(), _context_b())
        self.assertIn("file_refs", str(ctx.exception))

    def test_invented_command_raises(self):
        merged = _valid_merged()
        merged.commands_to_rerun = [CommandRef(command="npm test", outcome="unknown")]
        with self.assertRaises(MergeResponseError) as ctx:
            validate_merged_context(merged, _context_a(), _context_b())
        self.assertIn("commands_to_rerun", str(ctx.exception))

    def test_invented_test_raises(self):
        merged = _valid_merged()
        merged.tests_to_rerun = [TestRef(name="test_invented", outcome="unknown")]
        with self.assertRaises(MergeResponseError) as ctx:
            validate_merged_context(merged, _context_a(), _context_b())
        self.assertIn("tests_to_rerun", str(ctx.exception))

    def test_invalid_decision_source_side_raises(self):
        merged = _valid_merged()
        merged.decisions = [MergedDecision(text="Bad", sources=["a", "both"])]  # type: ignore[list-item]
        with self.assertRaises(MergeResponseError) as ctx:
            validate_merged_context(merged, _context_a(), _context_b())
        self.assertIn("'a' or 'b'", str(ctx.exception))

    def test_invalid_source_session_raises(self):
        merged = _valid_merged()
        merged.sources = [
            SourceRef(
                side="a",
                source_label="session-a",
                session_id="wrong-session",
                git_branch="feature-auth",
                leaf_uuid="uuid-a-leaf",
            ),
            SourceRef(
                side="b",
                source_label="session-b",
                session_id="sess-b-002",
                git_branch="feature-auth",
                leaf_uuid="uuid-b-leaf",
            ),
        ]
        with self.assertRaises(MergeResponseError) as ctx:
            validate_merged_context(merged, _context_a(), _context_b())
        self.assertIn("session_id", str(ctx.exception))

    def test_empty_bootstrap_prompt_raises(self):
        merged = _valid_merged()
        merged.bootstrap_prompt = "   "
        with self.assertRaises(MergeResponseError) as ctx:
            validate_merged_context(merged, _context_a(), _context_b())
        self.assertIn("bootstrap_prompt", str(ctx.exception))

    def test_branch_mismatch_requires_warning_or_assumption(self):
        merged = _merged_with_branch_mismatch_contexts()
        merged.warnings = []
        merged.assumptions = []
        with self.assertRaises(MergeResponseError) as ctx:
            validate_merged_context(
                merged,
                _context_a(git_branch="feature-auth"),
                _context_b(git_branch="feature-login"),
            )
        self.assertIn("branch mismatch", str(ctx.exception))

    def test_branch_mismatch_passes_with_warning(self):
        merged = _merged_with_branch_mismatch_contexts()
        merged.warnings = ["git_branch mismatch: a='feature-auth', b='feature-login'"]
        validate_merged_context(
            merged,
            _context_a(git_branch="feature-auth"),
            _context_b(git_branch="feature-login"),
        )

    def test_stub_merger_output_passes_validation(self):
        context_a = _context_a()
        context_b = _context_b(git_branch="feature-login")
        merged = StubMerger().merge(context_a, context_b)
        validate_merged_context(merged, context_a, context_b)


class CerebrasMergerValidationTests(unittest.TestCase):
    def test_rejects_invented_file_from_model(self):
        payload = _valid_merged_dict()
        payload["file_refs"] = [{"path": "src/invented.py", "action": "edit"}]
        merger = CerebrasMerger(client=FakeCerebrasClient(json.dumps(payload)))

        with self.assertRaises(MergeResponseError):
            merger.merge(_context_a(), _context_b())

    def test_accepts_valid_model_output(self):
        payload = _valid_merged_dict()
        merger = CerebrasMerger(client=FakeCerebrasClient(json.dumps(payload)))
        merged = merger.merge(_context_a(), _context_b())
        self.assertEqual(merged.merged_summary, payload["merged_summary"])


if __name__ == "__main__":
    unittest.main()
