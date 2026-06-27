"""Merge-layer plug-in point for future Cerebras (or stub) implementations."""

from __future__ import annotations

from typing import Protocol

from weave.context.types import ChatContext
from weave.merge.types import MergedContext


class ContextMerger(Protocol):
    """Merge two distilled session contexts into one semantic result."""

    def merge(
        self,
        context_a: ChatContext,
        context_b: ChatContext,
        *,
        feedback: str | None = None,
    ) -> MergedContext:
        """Return a merged context.

        ``feedback`` carries reprompt-loop rejection text from a prior attempt.
        """
        ...
