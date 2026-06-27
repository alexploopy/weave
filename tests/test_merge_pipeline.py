"""High-value tests for the merge pipeline (Cerebras, validator, stub)."""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from weave.context.types import CommandRef, Decision, FileRef, TestRef
from weave.merge.cerebras import CerebrasMerger
from weave.merge.exceptions import MergeResponseError
from weave.merge.stub import StubMerger
from weave.merge.types import MergedContext
from weave.merge.validator import validate_merged_context

from merge_test_fixtures import (
    FakeCerebrasClient,
    minimal_merged,
    minimal_merged_dict,
    sample_context_a,
    sample_context_b,
)

_WEAVE_ROOT = Path(__file__).resolve().parent.parent / "weave"


class CerebrasMergerPipelineTests(unittest.TestCase):
    def test_happy_path_returns_merged_context(self):
        payload = minimal_merged_dict()
        client = FakeCerebrasClient(json.dumps(payload))
        merged = CerebrasMerger(client=client).merge(
            sample_context_a(), sample_context_b()
        )
        self.assertEqual(merged, MergedContext.from_dict(payload))
        self.assertIn("session-a", client.last_prompt or "")

    def test_rejects_invalid_json(self):
        merger = CerebrasMerger(client=FakeCerebrasClient("{ broken"))
        with self.assertRaises(MergeResponseError) as ctx:
            merger.merge(sample_context_a(), sample_context_b())
        self.assertIn("not valid JSON", str(ctx.exception))


class ValidateMergedContextTests(unittest.TestCase):
    def test_rejects_invented_evidence(self):
        base = minimal_merged()
        cases = [
            (
                "file",
                lambda m: setattr(m, "file_refs", [FileRef(path="src/invented.py", action="edit")]),
                "file_refs",
            ),
            (
                "command",
                lambda m: setattr(
                    m, "commands_to_rerun", [CommandRef(command="npm test", outcome="unknown")]
                ),
                "commands_to_rerun",
            ),
            (
                "test",
                lambda m: setattr(
                    m, "tests_to_rerun", [TestRef(name="test_invented", outcome="unknown")]
                ),
                "tests_to_rerun",
            ),
        ]
        context_a = sample_context_a()
        context_b = sample_context_b()
        for label, mutate, needle in cases:
            with self.subTest(invented=label):
                merged = minimal_merged()
                mutate(merged)
                with self.assertRaises(MergeResponseError) as ctx:
                    validate_merged_context(merged, context_a, context_b)
                self.assertIn(needle, str(ctx.exception))


class StubMergerTests(unittest.TestCase):
    def test_output_passes_validator_with_branch_mismatch(self):
        context_a = sample_context_a(git_branch="feature-auth")
        context_b = sample_context_b(git_branch="feature-login")
        merged = StubMerger().merge(context_a, context_b)
        validate_merged_context(merged, context_a, context_b)
        self.assertTrue(any("branch" in w.casefold() for w in merged.warnings))

    def test_merges_deterministically(self):
        shared = Decision(id="d1", text="Use JWT in httpOnly cookies")
        context_a = sample_context_a()
        context_a.decisions = [shared, Decision(id="d3", text="Only from A")]
        context_b = sample_context_b()
        context_b.decisions = [Decision(id="d2", text="Use JWT in httpOnly cookies")]

        first = StubMerger().merge(context_a, context_b)
        second = StubMerger().merge(context_a, context_b)

        self.assertEqual(first, second)
        self.assertEqual(first.sources[0].session_id, "sess-a-001")
        self.assertEqual(first.sources[1].session_id, "sess-b-002")
        by_text = {d.text: d.sources for d in first.decisions}
        self.assertEqual(by_text["Use JWT in httpOnly cookies"], ["a", "b"])
        self.assertEqual(by_text["Only from A"], ["a"])


class WeaveImportBoundaryTests(unittest.TestCase):
    def test_only_transcript_package_imports_private_engine(self):
        """The private transcript engine is reachable only through the public
        ``weave.transcript`` surface -- no other weave module may import
        ``weave.transcript.engine`` (nor the legacy top-level ``transcript``)."""
        private = "weave.transcript.engine"
        legacy = "transcript"

        def is_private(name):
            return (
                name == private
                or name == legacy
                or name.startswith(legacy + ".")
            )

        offenders: list[str] = []
        for path in _WEAVE_ROOT.rglob("*.py"):
            # weave/transcript/* legitimately wires the engine to its façade.
            if path.parent.name == "transcript":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if is_private(alias.name):
                            offenders.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if is_private(node.module):
                        offenders.append(f"{path}: from {node.module}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
