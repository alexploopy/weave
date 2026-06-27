"""Live Cerebras merge verification (network; skipped unless env is configured)."""

from __future__ import annotations

import re
import unittest

from weave.merge.cerebras import CerebrasMerger
from weave.merge.env import cerebras_configured, describe_cerebras_config, ensure_dotenv_loaded
from weave.merge.exceptions import MergeClientError, MergeResponseError
from weave.merge.types import MERGE_SCHEMA_VERSION, MergedContext
from weave.merge.validator import validate_merged_context

from merge_test_fixtures import sample_context_a, sample_context_b

ensure_dotenv_loaded()


def _http_status_from_error(exc: MergeClientError) -> int | None:
    match = re.search(r"HTTP (\d{3})", str(exc))
    return int(match.group(1)) if match else None


@unittest.skipUnless(
    cerebras_configured(),
    "Set CEREBRAS_API_KEY and CEREBRAS_MODEL in the environment or repo .env",
)
class CerebrasLiveIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        print(f"\nCerebras config:\n{describe_cerebras_config()}")

    def test_http_merge_returns_valid_merged_context(self):
        context_a = sample_context_a()
        context_b = sample_context_b()

        try:
            merged = CerebrasMerger().merge(context_a, context_b)
        except MergeClientError as exc:
            status = _http_status_from_error(exc)
            if status in (401, 403):
                self.skipTest(f"Cerebras auth/forbidden (HTTP {status}): {exc}")
            if status == 404:
                self.skipTest(f"Cerebras model or endpoint not found (HTTP 404): {exc}")
            self.skipTest(f"Cerebras HTTP call failed: {exc}")
        except MergeResponseError as exc:
            self.fail(f"Cerebras returned output that failed merge validation: {exc}")

        self.assertIsInstance(merged, MergedContext)
        self.assertEqual(merged.schema_version, MERGE_SCHEMA_VERSION)
        self.assertTrue(merged.bootstrap_prompt.strip())
        self.assertEqual({s.side for s in merged.sources}, {"a", "b"})
        validate_merged_context(merged, context_a, context_b)


if __name__ == "__main__":
    ensure_dotenv_loaded()
    if not cerebras_configured():
        print("Cerebras config missing:")
        print(describe_cerebras_config())
        print("\nSkipped: set CEREBRAS_API_KEY and CEREBRAS_MODEL to run live verification.")
    unittest.main()
