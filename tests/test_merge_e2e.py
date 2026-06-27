"""End-to-end tests for core.merge_contexts with mocked Cerebras."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from weave import core
from weave.context.distill import distill_from_jsonl
from weave.merge.cerebras import CerebrasMerger
from weave.merge.exceptions import MergeResponseError

from merge_test_fixtures import FakeCerebrasClient, merged_dict_for_contexts

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "merge"


class MergeE2ETests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.output_dir = self.tmp / "merged"
        self.path_a = self.tmp / "session_a.jsonl"
        self.path_b = self.tmp / "session_b.jsonl"
        shutil.copy(_FIXTURES / "session_a_minimal.jsonl", self.path_a)
        shutil.copy(_FIXTURES / "session_b_minimal.jsonl", self.path_b)

    def _fake_merger(self) -> CerebrasMerger:
        text_a = self.path_a.read_text(encoding="utf-8")
        text_b = self.path_b.read_text(encoding="utf-8")
        ctx_a = distill_from_jsonl(
            text_a, source_label="a", source_path=str(self.path_a)
        ).context
        ctx_b = distill_from_jsonl(
            text_b, source_label="b", source_path=str(self.path_b)
        ).context
        payload = merged_dict_for_contexts(ctx_a, ctx_b)
        client = FakeCerebrasClient(json.dumps(payload))
        return CerebrasMerger(client=client)

    def test_core_merge_reads_two_temp_files(self):
        merger = self._fake_merger()
        result = core.merge_contexts(
            str(self.path_a),
            str(self.path_b),
            output_dir=self.output_dir,
            merger=merger,
        )
        self.assertTrue(Path(result.sidecar_path).is_file())
        self.assertEqual(result.source_a_path, str(self.path_a.resolve()))
        self.assertEqual(result.source_b_path, str(self.path_b.resolve()))

    def test_core_merge_calls_cerebras_with_both_session_ids(self):
        merger = self._fake_merger()
        core.merge_contexts(
            str(self.path_a),
            str(self.path_b),
            output_dir=self.output_dir,
            merger=merger,
        )
        client = merger._client
        assert isinstance(client, FakeCerebrasClient)
        self.assertIn("sess-a-001", client.last_prompt or "")
        self.assertIn("sess-b-002", client.last_prompt or "")

    def test_invalid_fake_cerebras_output_raises_and_writes_no_sidecar(self):
        client = FakeCerebrasClient("{ broken")
        merger = CerebrasMerger(client=client)
        with self.assertRaises(MergeResponseError):
            core.merge_contexts(
                str(self.path_a),
                str(self.path_b),
                output_dir=self.output_dir,
                merger=merger,
            )
        self.assertEqual(list(self.output_dir.glob("*.json")), [])

    def test_happy_path_writes_sidecar_with_expected_fields(self):
        merger = self._fake_merger()
        result = core.merge_contexts(
            str(self.path_a),
            str(self.path_b),
            output_dir=self.output_dir,
            merger=merger,
        )
        payload = json.loads(Path(result.sidecar_path).read_text(encoding="utf-8"))
        self.assertFalse(payload["claude_jsonl_compatible"])
        self.assertIn("merged_context", payload)
        self.assertIn("sources", payload["merged_context"])
        self.assertEqual(
            {s["side"] for s in payload["merged_context"]["sources"]}, {"a", "b"}
        )
        self.assertIsNone(result.jsonl_path)

    def test_source_files_are_not_overwritten(self):
        before_a = self.path_a.read_text(encoding="utf-8")
        before_b = self.path_b.read_text(encoding="utf-8")
        mtime_a = os.path.getmtime(self.path_a)
        mtime_b = os.path.getmtime(self.path_b)

        core.merge_contexts(
            str(self.path_a),
            str(self.path_b),
            output_dir=self.output_dir,
            merger=self._fake_merger(),
        )

        self.assertEqual(self.path_a.read_text(encoding="utf-8"), before_a)
        self.assertEqual(self.path_b.read_text(encoding="utf-8"), before_b)
        self.assertEqual(os.path.getmtime(self.path_a), mtime_a)
        self.assertEqual(os.path.getmtime(self.path_b), mtime_b)


if __name__ == "__main__":
    unittest.main()
