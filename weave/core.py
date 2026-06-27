"""Weave orchestrator core: push/pull/merge Claude Code sessions, plus remote/ls.

Owns ALL policy (id choice, cwd/sessionId rewrite, config resolution,
validation). Delegates mechanics to claude_connector_api (byte I/O),
transcript_api (entry editing), weave.config (remote resolution), the `server`
collaborator (byte transport backed by Supabase), and the merge layer
(distill + Cerebras). Stdlib only here; the Supabase dependency lives entirely
behind `server`.

Data pipeline for the remote operations:

    Supabase (weave_sessions) <--API--> server.py --text--> weave.core

`server` moves raw transcript text keyed by (remote_url, name); this module
applies every machine-specific policy (fresh id, cwd/sessionId rewrite) before
writing anything locally.
"""

import importlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import claude_connector_api as cc
import transcript_api as tx
from weave import config
from weave.context.distill import distill_from_jsonl
from weave.merge.factory import default_merger
from weave.merge.protocols import ContextMerger
from weave.merge.types import MergedContext

_DEFAULT_MERGED_DIR = ".weave/merged"
_WEAVE_MERGE_VERSION = "1"
_COMPATIBILITY_NOTE = (
    "MergedContext sidecar only; Claude resume compatibility is unverified."
)


class WeaveError(ValueError):
    """Any weave-layer error (unknown remote, empty history, remote transport)."""


@dataclass(frozen=True)
class MergeResult:
    merge_id: str
    sidecar_path: str
    source_a_path: str
    source_b_path: str
    jsonl_path: str | None = None


# --- config ------------------------------------------------------------------
def remote_add(name, url, *, path=None):
    config.add_remote(name, url, path=path)


def _remote_url(remote, *, path=None):
    """Resolve a remote name to its url, as a WeaveError on failure.

    Thin orchestrator-level adapter over :func:`weave.config.get_remote` so
    every weave-layer error shares the ``WeaveError`` (``ValueError``) base.
    """
    try:
        return config.get_remote(remote, path=path)
    except ValueError as e:
        raise WeaveError(str(e)) from e


def _load_server():
    return importlib.import_module("server")


def _remote_call(fn, *args, action, target):
    """Invoke a `server` transport call, mapping any failure to WeaveError.

    Keeps the original (actionable) message from the transport layer -- e.g.
    missing credentials or an absent remote session -- while tagging it with
    what was being attempted so the CLI surfaces a clear `weave: ...` line.
    """
    try:
        return fn(*args)
    except WeaveError:
        raise
    except ValueError as e:
        raise WeaveError(f"{action} {target}: {e}") from e


# --- operations --------------------------------------------------------------
def _new_id():
    return str(uuid.uuid4())


def _rewrite_for_local(entries, new_id, cwd):
    return [{**e, "cwd": cwd, "sessionId": new_id} for e in entries]


def pull(remote, name, *, cwd=None, server=None, config_path=None):
    """Download `name` from `remote` (Supabase) into a fresh local session.

    Pipeline: server.pull -> transcript_api parse -> local id/cwd rewrite ->
    connector write. Validates (unknown remote, transport failure, empty
    history) and fails before any local write.
    """
    url = _remote_url(remote, path=config_path)
    svr = server or _load_server()
    text = _remote_call(svr.pull, url, name, action="pull", target=f"{remote}/{name}")
    entries = tx.from_text(text)
    if not entries:
        raise WeaveError(f"session {name!r} has no chat history")
    cwd = cwd or os.getcwd()
    new_id = _new_id()
    entries = _rewrite_for_local(entries, new_id, cwd)
    cc.write_text(cc.session_path(cwd, new_id), tx.to_text(entries))
    return new_id


def push(remote, name, session_id, *, server=None, config_path=None):
    """Upload the local `session_id` to `remote` (Supabase) under `name`.

    Bytes are sent as-is; all machine-specific rewriting happens on `pull`.
    """
    text = cc.read_text(session_id)            # SessionNotFound/Ambiguous propagate
    url = _remote_url(remote, path=config_path)
    svr = server or _load_server()
    _remote_call(svr.push, url, name, text, action="push", target=f"{remote}/{name}")


def ls(remote=None, *, cwd=None, server=None, config_path=None):
    if remote is None:
        enc = cc.encode_cwd(cwd or os.getcwd())
        return [sid for sid, path in cc.list_sessions()
                if path.parent.name == enc]
    url = _remote_url(remote, path=config_path)
    svr = server or _load_server()
    return _remote_call(svr.list, url, action="ls", target=remote)


# --- merge -------------------------------------------------------------------
def _resolve_source_path(source: str) -> str:
    if os.sep in source or source.endswith(".jsonl"):
        return str(Path(source).resolve())
    resolved = cc.resolve(source)
    if resolved is not None:
        return str(resolved)
    return source


def _write_merge_sidecar(
    merged: MergedContext,
    *,
    merge_id: str,
    source_a_path: str,
    source_b_path: str,
    distill_warnings: dict[str, list[str]],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / f"{merge_id}.json"
    payload = {
        "weave_merge_version": _WEAVE_MERGE_VERSION,
        "claude_jsonl_compatible": False,
        "compatibility_note": _COMPATIBILITY_NOTE,
        "merge_id": merge_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "source_a_path": source_a_path,
        "source_b_path": source_b_path,
        "distill_warnings": distill_warnings,
        "merged_context": merged.to_dict(),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(
        dir=output_dir, prefix=sidecar_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, sidecar_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return sidecar_path


def merge_contexts(
    source_a: str,
    source_b: str,
    *,
    cwd: str | None = None,
    output_dir: str | Path | None = None,
    merger: ContextMerger | None = None,
) -> MergeResult:
    """Read two JSONL sessions, merge via Cerebras, write a sidecar JSON."""
    cwd = cwd or os.getcwd()
    source_a_path = _resolve_source_path(source_a)
    source_b_path = _resolve_source_path(source_b)

    text_a = cc.read_text(source_a)
    text_b = cc.read_text(source_b)

    try:
        distilled_a = distill_from_jsonl(
            text_a, source_label="a", source_path=source_a_path
        )
        distilled_b = distill_from_jsonl(
            text_b, source_label="b", source_path=source_b_path
        )
    except ValueError as exc:
        raise WeaveError(str(exc)) from exc

    active_merger = merger or default_merger()
    merged = active_merger.merge(distilled_a.context, distilled_b.context)

    merge_id = _new_id()
    out_dir = Path(output_dir) if output_dir is not None else Path(cwd) / _DEFAULT_MERGED_DIR
    sidecar_path = _write_merge_sidecar(
        merged,
        merge_id=merge_id,
        source_a_path=source_a_path,
        source_b_path=source_b_path,
        distill_warnings={
            "a": distilled_a.warnings,
            "b": distilled_b.warnings,
        },
        output_dir=out_dir,
    )
    return MergeResult(
        merge_id=merge_id,
        sidecar_path=str(sidecar_path),
        source_a_path=source_a_path,
        source_b_path=source_b_path,
        jsonl_path=None,
    )
