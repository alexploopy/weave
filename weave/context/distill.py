"""Tolerant JSONL → :class:`ChatContext` distillation for merge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from weave.context.types import ChatContext, CommandRef, FileRef

_MAX_SUMMARY_CHARS = 4000
_FILE_TOOL_NAMES = frozenset({"Read", "Edit", "Write", "MultiEdit"})
_BASH_TOOL_NAMES = frozenset({"Bash", "Shell"})


@dataclass
class DistillResult:
    context: ChatContext
    warnings: list[str]


def distill_from_jsonl(
    text: str,
    *,
    source_label: str,
    source_path: str,
    max_summary_messages: int = 20,
) -> DistillResult:
    """Parse Claude Code JSONL into a minimal :class:`ChatContext`."""
    warnings: list[str] = []
    entries_with_uuid: list[dict] = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            warnings.append(f"line {line_no}: invalid JSON, skipped")
            continue
        if not isinstance(entry, dict):
            warnings.append(f"line {line_no}: expected JSON object, skipped")
            continue
        if entry.get("uuid"):
            entries_with_uuid.append(entry)

    branch = _linearize_active_branch(entries_with_uuid)
    if not branch:
        raise ValueError(f"no uuid-bearing chat history in {source_path!r}")

    leaf = branch[-1]
    session_id = leaf.get("sessionId") or Path(source_path).stem
    leaf_uuid = leaf["uuid"]
    git_branch = leaf.get("gitBranch")
    cwd = leaf.get("cwd")

    summary = _build_summary(branch, max_messages=max_summary_messages)
    file_refs = _extract_file_refs(branch)
    commands = _extract_commands(branch)

    context = ChatContext(
        session_id=session_id,
        source_label=source_label,
        leaf_uuid=leaf_uuid,
        git_branch=git_branch,
        summary=summary,
        file_refs=file_refs,
        commands=commands,
        cwd=cwd,
        entry_count=len(branch),
        source_path=source_path,
    )
    return DistillResult(context=context, warnings=warnings)


def _linearize_active_branch(entries_with_uuid: list[dict]) -> list[dict]:
    """Active branch: last-appended uuid entry is leaf, walk parentUuid to root."""
    if not entries_with_uuid:
        return []

    by_uuid = {entry["uuid"]: entry for entry in entries_with_uuid}
    leaf = entries_with_uuid[-1]
    path: list[dict] = []
    seen: set[str] = set()
    cur: dict | None = leaf
    while cur is not None and cur.get("uuid") not in seen:
        seen.add(cur["uuid"])
        path.append(cur)
        parent_uuid = cur.get("parentUuid")
        cur = by_uuid.get(parent_uuid) if parent_uuid else None
    path.reverse()
    return path


def _build_summary(branch: list[dict], *, max_messages: int) -> str:
    texts: list[str] = []
    for entry in branch:
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _message_text(msg.get("content"))
        if text:
            texts.append(text.strip())

    recent = texts[-max_messages:] if max_messages > 0 else texts
    summary = " ".join(recent).strip()
    if len(summary) > _MAX_SUMMARY_CHARS:
        summary = summary[: _MAX_SUMMARY_CHARS - 3] + "..."
    return summary or "(no message text in active branch)"


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return " ".join(parts)


def _extract_file_refs(branch: list[dict]) -> list[FileRef]:
    seen: set[str] = set()
    refs: list[FileRef] = []
    for entry in branch:
        msg = entry.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            if name not in _FILE_TOOL_NAMES:
                continue
            inp = block.get("input")
            if not isinstance(inp, dict):
                continue
            path = inp.get("file_path") or inp.get("path")
            if not isinstance(path, str) or not path or path in seen:
                continue
            seen.add(path)
            action = "read" if name == "Read" else "edit"
            refs.append(FileRef(path=path, action=action))
    return refs


def _extract_commands(branch: list[dict]) -> list[CommandRef]:
    seen: set[str] = set()
    commands: list[CommandRef] = []
    for entry in branch:
        msg = entry.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in _BASH_TOOL_NAMES:
                continue
            inp = block.get("input")
            if not isinstance(inp, dict):
                continue
            command = inp.get("command")
            if not isinstance(command, str) or not command or command in seen:
                continue
            seen.add(command)
            commands.append(CommandRef(command=command, outcome="unknown"))
    return commands
