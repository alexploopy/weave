"""Validate merged outputs against input session contexts."""

from __future__ import annotations

from weave.context.types import ChatContext, Side
from weave.merge.exceptions import MergeResponseError
from weave.merge.types import MergedContext, SourceRef

_VALID_SIDES: frozenset[Side] = frozenset({"a", "b"})


def _input_file_paths(context_a: ChatContext, context_b: ChatContext) -> set[str]:
    return {ref.path for ref in context_a.file_refs} | {
        ref.path for ref in context_b.file_refs
    }


def _input_commands(context_a: ChatContext, context_b: ChatContext) -> set[str]:
    return {cmd.command for cmd in context_a.commands} | {
        cmd.command for cmd in context_b.commands
    }


def _input_test_names(context_a: ChatContext, context_b: ChatContext) -> set[str]:
    return {test.name for test in context_a.tests} | {test.name for test in context_b.tests}


def _input_test_commands(context_a: ChatContext, context_b: ChatContext) -> set[str]:
    return {
        test.command
        for test in (*context_a.tests, *context_b.tests)
        if test.command
    }


def _mentions_branch_mismatch(text: str) -> bool:
    lowered = text.casefold()
    return "branch" in lowered and ("mismatch" in lowered or "differ" in lowered)


def _validate_source_ref(ref: SourceRef, context: ChatContext) -> None:
    side = ref.side
    if ref.session_id != context.session_id:
        raise MergeResponseError(
            f"merged.sources session_id {ref.session_id!r} does not match "
            f"input side {side!r} session_id {context.session_id!r}"
        )
    if ref.source_label != context.source_label:
        raise MergeResponseError(
            f"merged.sources source_label {ref.source_label!r} does not match "
            f"input side {side!r} source_label {context.source_label!r}"
        )
    if ref.leaf_uuid != context.leaf_uuid:
        raise MergeResponseError(
            f"merged.sources leaf_uuid {ref.leaf_uuid!r} does not match "
            f"input side {side!r} leaf_uuid {context.leaf_uuid!r}"
        )
    if ref.git_branch != context.git_branch:
        raise MergeResponseError(
            f"merged.sources git_branch {ref.git_branch!r} does not match "
            f"input side {side!r} git_branch {context.git_branch!r}"
        )


def validate_merged_context(
    merged: MergedContext,
    context_a: ChatContext,
    context_b: ChatContext,
) -> None:
    """Ensure merge output does not invent evidence beyond the input contexts."""
    if not merged.bootstrap_prompt.strip():
        raise MergeResponseError("merged bootstrap_prompt must be non-empty")

    contexts = {"a": context_a, "b": context_b}

    for decision in merged.decisions:
        for side in decision.sources:
            if side not in _VALID_SIDES:
                raise MergeResponseError(
                    f"merged decision sources must be 'a' or 'b', got {side!r}"
                )

    sides_seen: set[Side] = set()
    for ref in merged.sources:
        if ref.side not in _VALID_SIDES:
            raise MergeResponseError(
                f"merged.sources side must be 'a' or 'b', got {ref.side!r}"
            )
        _validate_source_ref(ref, contexts[ref.side])
        sides_seen.add(ref.side)

    if sides_seen != _VALID_SIDES:
        raise MergeResponseError(
            "merged.sources must include provenance for both side 'a' and side 'b'"
        )

    allowed_paths = _input_file_paths(context_a, context_b)
    for ref in merged.file_refs:
        if ref.path not in allowed_paths:
            raise MergeResponseError(
                f"merged file_refs path {ref.path!r} not present in input contexts"
            )

    allowed_commands = _input_commands(context_a, context_b)
    for cmd in merged.commands_to_rerun:
        if cmd.command not in allowed_commands:
            raise MergeResponseError(
                f"merged commands_to_rerun command {cmd.command!r} "
                "not present in input contexts"
            )

    allowed_test_names = _input_test_names(context_a, context_b)
    allowed_test_commands = _input_test_commands(context_a, context_b)
    for test in merged.tests_to_rerun:
        if test.name in allowed_test_names:
            continue
        if test.command and test.command in allowed_test_commands:
            continue
        raise MergeResponseError(
            f"merged tests_to_rerun item {test.name!r} does not match "
            "any input test by name or command"
        )

    if context_a.git_branch != context_b.git_branch:
        notes = [*merged.warnings, *merged.assumptions]
        if not any(_mentions_branch_mismatch(note) for note in notes):
            raise MergeResponseError(
                "git_branch differs between input contexts; merged output must "
                "include a warning or assumption mentioning branch mismatch"
            )
