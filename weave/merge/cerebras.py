"""Cerebras-backed merge implementation."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Protocol

from weave.context.types import ChatContext
from weave.merge.exceptions import MergeClientError, MergeResponseError
from weave.merge.prompt import build_merge_prompt
from weave.merge.types import MergedContext
from weave.merge.validator import validate_merged_context

_DEFAULT_BASE_URL = "https://api.cerebras.ai/v1"
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


class CerebrasClient(Protocol):
    """Boundary for Cerebras completion calls (mockable in tests)."""

    def complete(self, prompt: str) -> str:
        """Return raw model text (expected to be JSON for MergedContext)."""
        ...


def _extract_json_text(raw: str) -> str:
    text = raw.strip()
    match = _FENCE_RE.match(text)
    if match:
        return match.group(1).strip()
    return text


def parse_merged_response(raw: str) -> MergedContext:
    """Parse model output into a :class:`MergedContext`."""
    try:
        data = json.loads(_extract_json_text(raw))
    except json.JSONDecodeError as exc:
        raise MergeResponseError(f"merge response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise MergeResponseError("merge response must be a JSON object")

    try:
        merged = MergedContext.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise MergeResponseError(
            f"merge response does not match MergedContext schema: {exc}"
        ) from exc

    if not merged.bootstrap_prompt.strip():
        raise MergeResponseError("merge response bootstrap_prompt must be non-empty")

    return merged


class HttpCerebrasClient:
    """Minimal Cerebras chat-completions client using stdlib HTTP."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        model: str,
        timeout_seconds: float | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def complete(self, prompt: str) -> str:
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as resp:
                response_body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MergeClientError(
                f"Cerebras API HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise MergeClientError(f"Cerebras API request failed: {exc.reason}") from exc

        try:
            parsed = json.loads(response_body)
            return parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise MergeClientError(
                f"Cerebras API returned unexpected response shape: {exc}"
            ) from exc


def default_cerebras_client() -> CerebrasClient:
    """Build an HTTP client from environment variables."""
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        raise MergeClientError("CEREBRAS_API_KEY is not set")

    model = os.environ.get("CEREBRAS_MODEL")
    if not model:
        raise MergeClientError("CEREBRAS_MODEL is not set")

    base_url = os.environ.get("CEREBRAS_BASE_URL", _DEFAULT_BASE_URL)

    timeout_raw = os.environ.get("WEAVE_MERGE_TIMEOUT_SECONDS")
    timeout_seconds: float | None = None
    if timeout_raw:
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise MergeClientError(
                f"WEAVE_MERGE_TIMEOUT_SECONDS must be a number, got {timeout_raw!r}"
            ) from exc

    return HttpCerebrasClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )


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
        client = self._client if self._client is not None else default_cerebras_client()
        prompt = build_merge_prompt(context_a, context_b, feedback=feedback)
        raw = client.complete(prompt)
        merged = parse_merged_response(raw)
        validate_merged_context(merged, context_a, context_b)
        if feedback and merged.reprompt_feedback is None:
            merged.reprompt_feedback = feedback
        return merged
