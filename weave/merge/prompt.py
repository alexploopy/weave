"""Prompt construction for the text-briefing merge layer.

Branch turns are rendered as lean text -- role plus text/thinking plus tool
calls with truncated I/O -- rather than dumping the raw JSONL entries. The raw
entries carry a heavy envelope (uuid/parentUuid/sessionId/cwd/timestamp on every
turn, nested JSON, ``"``-escaping) that can be ~7x the actual conversation; for
a briefing the model only needs what was said and done, so we drop the plumbing
and trim bulky tool inputs/results to keep the prompt small.
"""

from __future__ import annotations

import json

from weave.context.types import ChatContext

# Tool inputs/results are evidence of actions, not data to reproduce -- cap them.
_TOOL_INPUT_CHAR_LIMIT = 200
_RESULT_CHAR_LIMIT = 200


def _truncate(value, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[+{len(text) - limit} chars elided]"


def _render_block(role: str, block: dict, lines: list[str]) -> None:
    ty = block.get("type")
    if ty == "text":
        lines.append(f"{role}: {block.get('text', '')}")
    elif ty == "thinking":
        lines.append(f"{role} (thinking): {block.get('thinking') or block.get('text', '')}")
    elif ty == "tool_use":
        args = _truncate(block.get("input", {}), _TOOL_INPUT_CHAR_LIMIT)
        lines.append(f"  > tool {block.get('name', '?')}({args})")
    elif ty == "tool_result":
        lines.append(f"  < result {_truncate(block.get('content', ''), _RESULT_CHAR_LIMIT)}")


def _render_turns(entries: list[dict]) -> str:
    """Render raw transcript entries as lean text, dropping the JSONL envelope."""
    lines: list[str] = []
    for entry in entries:
        msg = entry.get("message") or {}
        role = msg.get("role") or entry.get("type", "?")
        content = msg.get("content")
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    _render_block(role, block, lines)
    return "\n".join(lines)


def build_merge_prompt(
    shared_context: ChatContext | None,
    a_branch: list[dict],
    b_branch: list[dict],
) -> str:
    """Serialize the shared background + both rendered branches into a briefing prompt."""
    shared_block = (
        json.dumps(shared_context.to_dict(), sort_keys=True)
        if shared_context is not None
        else "(none -- the two sessions share no history)"
    )
    sections = [
        "You are merging two diverged Claude Code session branches into one.",
        "Write a SINGLE briefing document (plain prose / markdown) that a developer",
        "can read to resume the unified work: what each branch did, the decisions",
        "made, how any conflicts reconcile, the files touched, and the current state",
        "with next steps. Output the briefing text only -- no JSON, no code fences.",
        "Tool inputs and results below are truncated -- treat them as evidence of",
        "actions taken, not as complete data.",
        "",
        "Shared background (distilled):",
        shared_block,
        "",
        "Branch A (transcript turns):",
        _render_turns(a_branch),
        "",
        "Branch B (transcript turns):",
        _render_turns(b_branch),
    ]
    return "\n".join(sections)
