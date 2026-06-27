"""Cerebras merge orchestration: prompt → client → parse → validate."""

from __future__ import annotations

from weave.context.types import ChatContext
from weave.merge.client import CerebrasClient, default_cerebras_client
from weave.merge.parse import parse_merged_response
from weave.merge.prompt import build_merge_prompt
from weave.merge.types import MergedContext
from weave.merge.validator import validate_merged_context


class CerebrasMerger:
    """Merge via Cerebras; implements :class:`~weave.merge.protocols.ContextMerger`."""

    def __init__(self, client: CerebrasClient | None = None) -> None:
        self._client = client

    def merge(
        self,
        context_a: ChatContext,
        context_b: ChatContext,
        *,
        feedback: str | None = None,
    ) -> MergedContext:
        client = self._client or default_cerebras_client()
        prompt = build_merge_prompt(context_a, context_b, feedback=feedback)
        raw_response = client.complete(prompt)
        merged = parse_merged_response(raw_response)
        validate_merged_context(merged, context_a, context_b)
        if feedback and merged.reprompt_feedback is None:
            merged.reprompt_feedback = feedback
        return merged
