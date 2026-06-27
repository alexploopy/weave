"""Tests for deterministic stub merge implementation."""

import unittest

from weave.context.types import (
    ChatContext,
    CommandRef,
    Decision,
    FileRef,
    TestRef,
    TodoItem,
)
from weave.merge.stub import StubMerger
from weave.merge.types import MERGE_SCHEMA_VERSION


def _context(
    *,
    session_id: str,
    source_label: str,
    leaf_uuid: str,
    summary: str,
    git_branch: str | None = "main",
    decisions: list[Decision] | None = None,
    todos: list[TodoItem] | None = None,
    file_refs: list[FileRef] | None = None,
    commands: list[CommandRef] | None = None,
    tests: list[TestRef] | None = None,
    assumptions: list[str] | None = None,
) -> ChatContext:
    return ChatContext(
        session_id=session_id,
        source_label=source_label,
        leaf_uuid=leaf_uuid,
        git_branch=git_branch,
        summary=summary,
        decisions=decisions or [],
        todos=todos or [],
        file_refs=file_refs or [],
        commands=commands or [],
        tests=tests or [],
        assumptions=assumptions or [],
    )


class StubMergerTests(unittest.TestCase):
    def setUp(self):
        self.merger = StubMerger()

    def test_merge_returns_valid_merged_context(self):
        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="Worked on auth middleware.",
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="Added login tests.",
        )

        merged = self.merger.merge(a, b)
        d = merged.to_dict()

        self.assertEqual(merged.schema_version, MERGE_SCHEMA_VERSION)
        for key in (
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
        self.assertTrue(merged.bootstrap_prompt)

    def test_sources_carry_session_metadata(self):
        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="A",
            git_branch="feature-auth",
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="B",
            git_branch="feature-auth",
        )

        merged = self.merger.merge(a, b)
        self.assertEqual(len(merged.sources), 2)
        self.assertEqual(merged.sources[0].side, "a")
        self.assertEqual(merged.sources[0].session_id, "sess-a")
        self.assertEqual(merged.sources[0].leaf_uuid, "leaf-a")
        self.assertEqual(merged.sources[1].side, "b")

    def test_shared_decisions_tagged_with_both_sides(self):
        shared = Decision(id="d1", text="Use JWT in httpOnly cookies")
        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="A",
            decisions=[shared],
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="B",
            decisions=[Decision(id="d2", text="Use JWT in httpOnly cookies")],
        )

        merged = self.merger.merge(a, b)
        self.assertEqual(len(merged.decisions), 1)
        self.assertEqual(merged.decisions[0].sources, ["a", "b"])

    def test_side_specific_decisions_preserved(self):
        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="A",
            decisions=[Decision(id="d1", text="Only from A")],
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="B",
            decisions=[Decision(id="d2", text="Only from B")],
        )

        merged = self.merger.merge(a, b)
        by_text = {d.text: d.sources for d in merged.decisions}
        self.assertEqual(by_text["Only from A"], ["a"])
        self.assertEqual(by_text["Only from B"], ["b"])

    def test_open_todos_deduped_across_sessions(self):
        todo = TodoItem(text="Add refresh token rotation", status="open")
        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="A",
            todos=[todo],
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="B",
            todos=[TodoItem(text="Add refresh token rotation", status="open")],
        )

        merged = self.merger.merge(a, b)
        self.assertEqual(len(merged.unresolved_todos), 1)

    def test_feedback_round_trips(self):
        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="A",
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="B",
        )

        merged = self.merger.merge(a, b, feedback="Keep session B redirect URL.")
        self.assertEqual(merged.reprompt_feedback, "Keep session B redirect URL.")
        self.assertIn("Keep session B redirect URL.", merged.bootstrap_prompt)

    def test_merge_is_deterministic(self):
        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="A",
            commands=[CommandRef(command="pytest", outcome="pass")],
            tests=[TestRef(name="test_auth", outcome="pass")],
            file_refs=[FileRef(path="src/auth.py", action="edit")],
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="B",
        )

        first = self.merger.merge(a, b)
        second = self.merger.merge(a, b)
        self.assertEqual(first, second)

    def test_json_roundtrip_after_merge(self):
        import json

        from weave.merge.types import MergedContext

        a = _context(
            session_id="sess-a",
            source_label="session-a",
            leaf_uuid="leaf-a",
            summary="A",
        )
        b = _context(
            session_id="sess-b",
            source_label="session-b",
            leaf_uuid="leaf-b",
            summary="B",
        )

        merged = self.merger.merge(a, b)
        restored = MergedContext.from_dict(json.loads(json.dumps(merged.to_dict())))
        self.assertEqual(restored, merged)


if __name__ == "__main__":
    unittest.main()
