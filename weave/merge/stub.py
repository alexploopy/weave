"""Deterministic in-memory merger for tests and local development."""

from __future__ import annotations

from weave.context.types import ChatContext, CommandRef, FileRef, Side, TestRef, TodoItem
from weave.merge.types import (
    MergedContext,
    MergedDecision,
    SourceRef,
)


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _source_ref(context: ChatContext, side: Side) -> SourceRef:
    return SourceRef(
        side=side,
        source_label=context.source_label,
        session_id=context.session_id,
        git_branch=context.git_branch,
        leaf_uuid=context.leaf_uuid,
    )


def _merge_decisions(context_a: ChatContext, context_b: ChatContext) -> list[MergedDecision]:
    by_text: dict[str, MergedDecision] = {}
    order: list[str] = []

    for decision in context_a.decisions:
        key = _norm(decision.text)
        order.append(key)
        by_text[key] = MergedDecision(text=decision.text, sources=["a"])

    for decision in context_b.decisions:
        key = _norm(decision.text)
        if key in by_text:
            by_text[key].sources = ["a", "b"]
        else:
            order.append(key)
            by_text[key] = MergedDecision(text=decision.text, sources=["b"])

    return [by_text[k] for k in order]


def _dedupe_todos(items: list[TodoItem]) -> list[TodoItem]:
    seen: set[str] = set()
    out: list[TodoItem] = []
    for item in items:
        if item.status != "open":
            continue
        key = _norm(item.text)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _dedupe_file_refs(items: list[FileRef]) -> list[FileRef]:
    seen: set[str] = set()
    out: list[FileRef] = []
    for ref in items:
        if ref.path in seen:
            continue
        seen.add(ref.path)
        out.append(ref)
    return out


def _commands_to_rerun(context_a: ChatContext, context_b: ChatContext) -> list[CommandRef]:
    seen: set[str] = set()
    out: list[CommandRef] = []
    for cmd in (*context_a.commands, *context_b.commands):
        if cmd.command in seen:
            continue
        seen.add(cmd.command)
        out.append(CommandRef(command=cmd.command, outcome="unknown", note=cmd.note))
    return out


def _tests_to_rerun(context_a: ChatContext, context_b: ChatContext) -> list[TestRef]:
    seen: set[str] = set()
    out: list[TestRef] = []
    for test in (*context_a.tests, *context_b.tests):
        if test.name in seen:
            continue
        seen.add(test.name)
        out.append(
            TestRef(name=test.name, command=test.command, outcome="unknown")
        )
    return out


def _assumptions(context_a: ChatContext, context_b: ChatContext) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for text in (*context_a.assumptions, *context_b.assumptions):
        key = _norm(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _bootstrap_prompt(
    context_a: ChatContext,
    context_b: ChatContext,
    todos: list[TodoItem],
    *,
    feedback: str | None,
) -> str:
    parts = [
        "Resume merged session work.",
        f"Session A ({context_a.source_label}): {context_a.summary}",
        f"Session B ({context_b.source_label}): {context_b.summary}",
    ]
    if todos:
        parts.append("Open todos: " + "; ".join(t.text for t in todos))
    if feedback:
        parts.append(f"Reviewer feedback: {feedback}")
    return " ".join(parts)


class StubMerger:
    """In-memory merge stub implementing :class:`~weave.merge.protocols.ContextMerger`."""

    def merge(
        self,
        context_a: ChatContext,
        context_b: ChatContext,
        *,
        feedback: str | None = None,
    ) -> MergedContext:
        unresolved = _dedupe_todos([*context_a.todos, *context_b.todos])
        warnings: list[str] = []
        if (
            context_a.git_branch is not None
            and context_b.git_branch is not None
            and context_a.git_branch != context_b.git_branch
        ):
            warnings.append(
                f"git_branch mismatch: a={context_a.git_branch!r}, b={context_b.git_branch!r}"
            )

        return MergedContext(
            merged_summary=f"{context_a.summary} | {context_b.summary}",
            decisions=_merge_decisions(context_a, context_b),
            conflicts=[],
            assumptions=_assumptions(context_a, context_b),
            unresolved_todos=unresolved,
            file_refs=_dedupe_file_refs([*context_a.file_refs, *context_b.file_refs]),
            commands_to_rerun=_commands_to_rerun(context_a, context_b),
            tests_to_rerun=_tests_to_rerun(context_a, context_b),
            bootstrap_prompt=_bootstrap_prompt(
                context_a, context_b, unresolved, feedback=feedback
            ),
            sources=[_source_ref(context_a, "a"), _source_ref(context_b, "b")],
            warnings=warnings,
            reprompt_feedback=feedback,
        )
