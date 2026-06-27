"""Weave orchestrator core: push/pull/merge Claude Code sessions, plus remote/ls.

Owns ALL policy (id choice, cwd/sessionId rewrite, config resolution,
validation). Delegates mechanics to claude_connector_api (byte I/O),
transcript_api (entry editing), and a lazily-loaded `server` collaborator
(byte transport). Stdlib only.
"""

import configparser
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

from weave.context.distill import distill_from_jsonl
from weave.merge.factory import default_merger
from weave.merge.protocols import ContextMerger
from weave.merge.types import MergedContext

_DEFAULT_CONFIG = ".weave/config"
_DEFAULT_MERGED_DIR = ".weave/merged"
_WEAVE_MERGE_VERSION = "1"
_COMPATIBILITY_NOTE = (
    "MergedContext sidecar only; Claude resume compatibility is unverified."
)


class WeaveError(ValueError):
    """Any weave-layer error (unknown remote, empty history)."""


@dataclass(frozen=True)
class MergeResult:
    merge_id: str
    sidecar_path: str
    source_a_path: str
    source_b_path: str
    jsonl_path: str | None = None


# --- config ------------------------------------------------------------------
def _read_config(*, path=None):
    cfg = configparser.ConfigParser()
    p = Path(path or _DEFAULT_CONFIG)
    if p.is_file():
        cfg.read(p, encoding="utf-8")
    return cfg


def _remote_url(name, *, path=None):
    cfg = _read_config(path=path)
    section = f'remote "{name}"'
    if not cfg.has_option(section, "url"):
        raise WeaveError(f"no remote {name!r}; add it with 'weave remote add'")
    return cfg.get(section, "url")


def remote_add(name, url, *, path=None):
    p = Path(path or _DEFAULT_CONFIG)
    cfg = _read_config(path=p)
    section = f'remote "{name}"'
    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg.set(section, "url", url)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        cfg.write(f)
    return p


def _load_server():
    return importlib.import_module("server")


# --- operations --------------------------------------------------------------
def _new_id():
    return str(uuid.uuid4())


def _rewrite_for_local(entries, new_id, cwd):
    return [{**e, "cwd": cwd, "sessionId": new_id} for e in entries]


def pull(remote, name, *, cwd=None, server=None, config_path=None):
    url = _remote_url(remote, path=config_path)
    text = (server or _load_server()).pull(url, name)
    entries = tx.from_text(text)
    if not entries:
        raise WeaveError(f"session {name!r} has no chat history")
    cwd = cwd or os.getcwd()
    new_id = _new_id()
    entries = _rewrite_for_local(entries, new_id, cwd)
    cc.write_text(cc.session_path(cwd, new_id), tx.to_text(entries))
    return new_id


def push(remote, name, session_id, *, server=None, config_path=None):
    text = cc.read_text(session_id)            # SessionNotFound/Ambiguous propagate
    url = _remote_url(remote, path=config_path)
    (server or _load_server()).push(url, name, text)


def ls(remote=None, *, cwd=None, server=None, config_path=None):
    if remote is None:
        enc = cc.encode_cwd(cwd or os.getcwd())
        return [sid for sid, path in cc.list_sessions()
                if path.parent.name == enc]
    url = _remote_url(remote, path=config_path)
    return (server or _load_server()).list(url)


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
