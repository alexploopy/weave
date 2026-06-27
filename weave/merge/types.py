"""Semantic merge output consumed by the synthesizer/writer.

The Cerebras merge layer owns ``ChatContext`` + ``ChatContext`` → :class:`MergedContext`.
This is not raw Claude JSONL; the synthesizer turns it into ``transcript_api`` specs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from weave.context.types import CommandRef, FileRef, Side, TestRef, TodoItem

MERGE_SCHEMA_VERSION = "1"


def _omit_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _from_dict(cls: type, data: dict[str, Any]) -> Any:
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class MergedDecision:
    text: str
    sources: list[Side]
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none({"text": self.text, "sources": self.sources, "note": self.note})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MergedDecision:
        return _from_dict(cls, data)


@dataclass
class Conflict:
    topic: str
    side_a: str
    side_b: str
    resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "topic": self.topic,
                "side_a": self.side_a,
                "side_b": self.side_b,
                "resolution": self.resolution,
            }
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conflict:
        return _from_dict(cls, data)


@dataclass
class SourceRef:
    side: Side
    source_label: str
    session_id: str
    git_branch: str | None
    leaf_uuid: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "source_label": self.source_label,
            "session_id": self.session_id,
            "git_branch": self.git_branch,
            "leaf_uuid": self.leaf_uuid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRef:
        return _from_dict(cls, data)


@dataclass
class MergedContext:
    """Unified semantic context after merging two distilled sessions."""

    merged_summary: str
    decisions: list[MergedDecision]
    conflicts: list[Conflict]
    assumptions: list[str]
    unresolved_todos: list[TodoItem]
    file_refs: list[FileRef]
    commands_to_rerun: list[CommandRef]
    tests_to_rerun: list[TestRef]
    bootstrap_prompt: str
    sources: list[SourceRef]
    schema_version: str = MERGE_SCHEMA_VERSION
    dedup_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reprompt_feedback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "schema_version": self.schema_version,
                "merged_summary": self.merged_summary,
                "decisions": [d.to_dict() for d in self.decisions],
                "conflicts": [c.to_dict() for c in self.conflicts],
                "assumptions": self.assumptions,
                "unresolved_todos": [t.to_dict() for t in self.unresolved_todos],
                "file_refs": [f.to_dict() for f in self.file_refs],
                "commands_to_rerun": [c.to_dict() for c in self.commands_to_rerun],
                "tests_to_rerun": [t.to_dict() for t in self.tests_to_rerun],
                "bootstrap_prompt": self.bootstrap_prompt,
                "sources": [s.to_dict() for s in self.sources],
                "dedup_notes": self.dedup_notes or None,
                "warnings": self.warnings or None,
                "reprompt_feedback": self.reprompt_feedback,
            }
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MergedContext:
        return cls(
            schema_version=data.get("schema_version", MERGE_SCHEMA_VERSION),
            merged_summary=data["merged_summary"],
            decisions=[MergedDecision.from_dict(d) for d in data.get("decisions", [])],
            conflicts=[Conflict.from_dict(c) for c in data.get("conflicts", [])],
            assumptions=list(data.get("assumptions", [])),
            unresolved_todos=[
                TodoItem.from_dict(t) for t in data.get("unresolved_todos", [])
            ],
            file_refs=[FileRef.from_dict(f) for f in data.get("file_refs", [])],
            commands_to_rerun=[
                CommandRef.from_dict(c) for c in data.get("commands_to_rerun", [])
            ],
            tests_to_rerun=[
                TestRef.from_dict(t) for t in data.get("tests_to_rerun", [])
            ],
            bootstrap_prompt=data["bootstrap_prompt"],
            sources=[SourceRef.from_dict(s) for s in data.get("sources", [])],
            dedup_notes=list(data.get("dedup_notes", [])),
            warnings=list(data.get("warnings", [])),
            reprompt_feedback=data.get("reprompt_feedback"),
        )
