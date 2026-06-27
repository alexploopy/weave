"""Merge-layer errors for Cerebras integration."""


class MergeError(Exception):
    """Base error for merge failures."""


class MergeResponseError(MergeError):
    """Model output could not be parsed into a valid :class:`MergedContext`."""


class MergeClientError(MergeError):
    """Cerebras HTTP client or configuration failure."""
