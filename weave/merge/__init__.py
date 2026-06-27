"""Merge layer: stub and Cerebras implementations of :class:`ContextMerger`."""

from weave.merge.briefing import (
    BriefingMerger,
    StubBriefingMerger,
    build_briefing_prompt,
    default_briefing_merger,
)
from weave.merge.cerebras import CerebrasMerger
from weave.merge.exceptions import MergeClientError, MergeError, MergeResponseError
from weave.merge.factory import default_merger
from weave.merge.protocols import ContextMerger
from weave.merge.stub import StubMerger
from weave.merge.types import (
    MERGE_SCHEMA_VERSION,
    Conflict,
    MergedContext,
    MergedDecision,
    SourceRef,
)
from weave.merge.validator import validate_merged_context

__all__ = [
    "MERGE_SCHEMA_VERSION",
    "BriefingMerger",
    "CerebrasMerger",
    "Conflict",
    "ContextMerger",
    "default_briefing_merger",
    "default_merger",
    "MergeClientError",
    "MergeError",
    "MergeResponseError",
    "MergedContext",
    "MergedDecision",
    "SourceRef",
    "StubBriefingMerger",
    "StubMerger",
    "build_briefing_prompt",
    "validate_merged_context",
]
