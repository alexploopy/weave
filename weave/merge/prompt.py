"""Prompt construction for Cerebras session merge."""

from __future__ import annotations

import json

from weave.context.types import ChatContext

_MERGE_OUTPUT_SCHEMA = """
Return a single JSON object matching this MergedContext schema (schema_version "1"):

Required top-level keys:
  merged_summary, decisions, conflicts, assumptions, unresolved_todos,
  file_refs, commands_to_rerun, tests_to_rerun, bootstrap_prompt, sources

Field notes:
  - decisions[].sources: each value is ["a"], ["b"], or ["a", "b"] (never "both")
  - sources[]: side "a" or "b" with source_label, session_id, git_branch, leaf_uuid
  - bootstrap_prompt: non-empty seed text for the resumed session
  - conflicts[]: topic, side_a, side_b, optional resolution
  - unresolved_todos[]: text and status ("open", "done", "blocked")
  - file_refs[]: path, action ("read"|"edit"|"create"|"delete"|"mention")
  - commands_to_rerun[]: command, outcome ("success"|"failure"|"unknown")
  - tests_to_rerun[]: name, optional command, outcome

Respond with JSON only. No markdown fences or commentary.
""".strip()


def build_merge_prompt(
    context_a: ChatContext,
    context_b: ChatContext,
    *,
    feedback: str | None = None,
) -> str:
    """Serialize both contexts and instructions into a merge prompt."""
    sections = [
        "Merge two distilled Claude Code session contexts into one unified MergedContext.",
        "",
        _MERGE_OUTPUT_SCHEMA,
        "",
        "Session A (side a):",
        json.dumps(context_a.to_dict(), indent=2, sort_keys=True),
        "",
        "Session B (side b):",
        json.dumps(context_b.to_dict(), indent=2, sort_keys=True),
    ]
    if feedback:
        sections.extend(
            [
                "",
                "Reviewer feedback on a prior merge attempt (incorporate this):",
                feedback,
            ]
        )
    return "\n".join(sections)
