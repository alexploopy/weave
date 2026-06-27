"""Pure text-briefing merge layer.

Takes the distilled shared background plus the two raw divergent branches and
returns a single briefing document. No I/O, no transcript edits -- those live in
weave.core. This module will become the canonical merge layer once the old
MergedContext path is removed.
"""

from __future__ import annotations

import json

from weave.context.types import ChatContext
from weave.merge.client import CerebrasClient, default_cerebras_client
from weave.merge.env import cerebras_configured
from weave.merge.exceptions import MergeClientError, MergeResponseError


def build_briefing_prompt(
    shared_context: ChatContext | None,
    a_branch: list[dict],
    b_branch: list[dict],
) -> str:
    """Serialize the shared background + both raw branches into a briefing prompt."""
    shared_block = (
        json.dumps(shared_context.to_dict(), indent=2, sort_keys=True)
        if shared_context is not None
        else "(none -- the two sessions share no history)"
    )
    sections = [
        "You are merging two diverged Claude Code session branches into one.",
        "Write a SINGLE briefing document (plain prose / markdown) that a developer",
        "can read to resume the unified work: what each branch did, the decisions",
        "made, how any conflicts reconcile, the files touched, and the current state",
        "with next steps. Output the briefing text only -- no JSON, no code fences.",
        "",
        "Shared background (distilled):",
        shared_block,
        "",
        "Branch A (raw transcript turns):",
        json.dumps(a_branch, indent=2, sort_keys=True),
        "",
        "Branch B (raw transcript turns):",
        json.dumps(b_branch, indent=2, sort_keys=True),
    ]
    return "\n".join(sections)


class BriefingMerger:
    """Merge two branches into a briefing via Cerebras."""

    def __init__(self, client: CerebrasClient | None = None) -> None:
        self._client = client

    def merge(
        self,
        shared_context: ChatContext | None,
        a_branch: list[dict],
        b_branch: list[dict],
    ) -> str:
        client = self._client or default_cerebras_client()
        prompt = build_briefing_prompt(shared_context, a_branch, b_branch)
        text = client.complete(prompt).strip()
        if not text:
            raise MergeResponseError("merge response was empty")
        return text


class StubBriefingMerger:
    """Deterministic in-memory briefing merger for tests and local dev."""

    def merge(
        self,
        shared_context: ChatContext | None,
        a_branch: list[dict],
        b_branch: list[dict],
    ) -> str:
        shared_line = (
            shared_context.summary if shared_context is not None
            else "no shared history"
        )
        return (
            "MERGED SESSION BRIEFING\n"
            f"Shared background: {shared_line}\n"
            f"Branch A contributed {len(a_branch)} turn(s).\n"
            f"Branch B contributed {len(b_branch)} turn(s)."
        )


def default_briefing_merger(*, client: CerebrasClient | None = None) -> BriefingMerger:
    """Return a :class:`BriefingMerger` when Cerebras env vars are configured."""
    if client is None and not cerebras_configured():
        raise MergeClientError(
            "CEREBRAS_API_KEY and CEREBRAS_MODEL are required for merge"
        )
    return BriefingMerger(client=client)
