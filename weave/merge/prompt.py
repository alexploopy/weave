"""Prompt construction for the text-briefing merge layer."""

from __future__ import annotations

import json

from weave.context.types import ChatContext


def build_merge_prompt(
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
