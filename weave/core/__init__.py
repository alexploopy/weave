"""Weave orchestrator core: push/pull/merge Claude Code sessions, plus remote/ls.

Owns all weave-layer policy (id choice, cwd/sessionId rewrite, config
resolution, validation). Implementation lives in :mod:`weave.core.core`; import
from this package (``from weave import core``) for the stable surface.
"""

from weave.core.core import (
    MergeResult,
    MergedSession,
    WeaveError,
    ls,
    merge,
    merge_contexts,
    pull,
    push,
    remote_add,
)

__all__ = [
    "MergeResult",
    "MergedSession",
    "WeaveError",
    "ls",
    "merge",
    "merge_contexts",
    "pull",
    "push",
    "remote_add",
]
