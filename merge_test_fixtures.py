"""Shared fixtures for merge pipeline tests (not a test module)."""

from __future__ import annotations

import json
from pathlib import Path

from weave.context.types import (
    ChatContext,
    CommandRef,
    Decision,
    FileRef,
    TestRef,
    TodoItem,
)
from weave.merge.types import MergedContext

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "merge"


class FakeCerebrasClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def sample_context_a(*, git_branch: str | None = "feature-auth") -> ChatContext:
    return ChatContext(
        session_id="sess-a-001",
        source_label="session-a",
        leaf_uuid="uuid-a-leaf",
        git_branch=git_branch,
        summary="Explored JWT auth middleware.",
        decisions=[Decision(id="d1", text="Use JWT in httpOnly cookies")],
        file_refs=[FileRef(path="src/auth.py", action="edit")],
        commands=[CommandRef(command="pytest tests/test_auth.py", outcome="pass")],
        tests=[TestRef(name="test_auth", command="pytest tests/test_auth.py", outcome="pass")],
        todos=[TodoItem(text="Add refresh token rotation", status="open")],
        assumptions=["Local Postgres on port 5432"],
    )


def sample_context_b(*, git_branch: str | None = "feature-auth") -> ChatContext:
    return ChatContext(
        session_id="sess-b-002",
        source_label="session-b",
        leaf_uuid="uuid-b-leaf",
        git_branch=git_branch,
        summary="Added pytest coverage for auth.",
        decisions=[Decision(id="d2", text="Use JWT in httpOnly cookies")],
    )


def minimal_merged_dict() -> dict:
    data = json.loads((_FIXTURES / "merged_context_minimal.json").read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


def minimal_merged() -> MergedContext:
    return MergedContext.from_dict(minimal_merged_dict())
