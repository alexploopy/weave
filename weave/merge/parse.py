"""Parse Cerebras model text into :class:`MergedContext`."""

from __future__ import annotations

import json
import re

from weave.merge.exceptions import MergeResponseError
from weave.merge.types import MergedContext

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


def _extract_json_text(raw: str) -> str:
    text = raw.strip()
    match = _FENCE_RE.match(text)
    if match:
        return match.group(1).strip()
    return text


def parse_merged_response(raw: str) -> MergedContext:
    """Load model output JSON (optionally fenced) into a :class:`MergedContext`."""
    try:
        data = json.loads(_extract_json_text(raw))
    except json.JSONDecodeError as exc:
        raise MergeResponseError(f"merge response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise MergeResponseError("merge response must be a JSON object")

    try:
        merged = MergedContext.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise MergeResponseError(
            f"merge response does not match MergedContext schema: {exc}"
        ) from exc

    if not merged.bootstrap_prompt.strip():
        raise MergeResponseError("merge response bootstrap_prompt must be non-empty")

    return merged
