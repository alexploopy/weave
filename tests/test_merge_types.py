"""Tests for MergedContext and nested merge types."""

import json
import unittest
from pathlib import Path

from weave.context.types import CommandRef, FileRef, TestRef, TodoItem
from weave.merge.types import (
    MERGE_SCHEMA_VERSION,
    Conflict,
    MergedContext,
    MergedDecision,
    SourceRef,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "merge"


def _sample_merged() -> MergedContext:
    return MergedContext(
        merged_summary="Both sessions worked on auth; unified on JWT cookies.",
        decisions=[
            MergedDecision(
                text="Use JWT in httpOnly cookies",
                sources=["a", "b"],
            ),
            MergedDecision(
                text="Defer refresh token rotation",
                sources=["a"],
                note="Session B had not started this yet",
            ),
        ],
        conflicts=[
            Conflict(
                topic="Redirect after login",
                side_a="Redirect to /dashboard",
                side_b="Redirect to /home",
                resolution="Use /dashboard",
            )
        ],
        assumptions=["Shared dev database at localhost:5432"],
        unresolved_todos=[TodoItem(text="Add refresh token rotation", status="open")],
        file_refs=[
            FileRef(path="src/auth.py", action="edit"),
            FileRef(path="tests/test_auth.py", action="edit"),
        ],
        commands_to_rerun=[
            CommandRef(command="pytest tests/test_auth.py", outcome="unknown")
        ],
        tests_to_rerun=[TestRef(name="test_auth", outcome="unknown")],
        bootstrap_prompt=(
            "You are resuming a merged session. Auth middleware uses JWT httpOnly "
            "cookies. Re-run pytest tests/test_auth.py and continue refresh token work."
        ),
        sources=[
            SourceRef(
                side="a",
                source_label="session-a",
                session_id="sess-a",
                git_branch="feature-auth",
                leaf_uuid="a2-leaf",
            ),
            SourceRef(
                side="b",
                source_label="session-b",
                session_id="sess-b",
                git_branch="feature-auth",
                leaf_uuid="b9-leaf",
            ),
        ],
        warnings=["git_branch matched; no branch mismatch"],
    )


class MergedContextSerializationTests(unittest.TestCase):
    def test_to_dict_from_dict_roundtrip(self):
        original = _sample_merged()
        restored = MergedContext.from_dict(original.to_dict())
        self.assertEqual(restored, original)

    def test_json_roundtrip(self):
        original = _sample_merged()
        payload = json.dumps(original.to_dict())
        restored = MergedContext.from_dict(json.loads(payload))
        self.assertEqual(restored, original)

    def test_required_fields_present_in_dict(self):
        d = _sample_merged().to_dict()
        for key in (
            "schema_version",
            "merged_summary",
            "decisions",
            "conflicts",
            "assumptions",
            "unresolved_todos",
            "file_refs",
            "commands_to_rerun",
            "tests_to_rerun",
            "bootstrap_prompt",
            "sources",
        ):
            self.assertIn(key, d)

    def test_merged_decision_sources_are_side_list(self):
        d = _sample_merged().to_dict()
        shared = d["decisions"][0]
        self.assertEqual(shared["sources"], ["a", "b"])

    def test_source_ref_includes_side_and_leaf_uuid(self):
        d = _sample_merged().to_dict()
        src = d["sources"][0]
        self.assertEqual(src["side"], "a")
        self.assertEqual(src["leaf_uuid"], "a2-leaf")

    def test_schema_version_default(self):
        ctx = MergedContext(
            merged_summary="x",
            decisions=[],
            conflicts=[],
            assumptions=[],
            unresolved_todos=[],
            file_refs=[],
            commands_to_rerun=[],
            tests_to_rerun=[],
            bootstrap_prompt="go",
            sources=[],
        )
        self.assertEqual(ctx.schema_version, MERGE_SCHEMA_VERSION)

    def test_minimal_fixture_loads(self):
        path = FIXTURES / "merged_context_minimal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        ctx = MergedContext.from_dict(data)
        self.assertEqual(ctx.schema_version, MERGE_SCHEMA_VERSION)
        self.assertTrue(ctx.bootstrap_prompt)
        self.assertEqual(len(ctx.sources), 2)


if __name__ == "__main__":
    unittest.main()
