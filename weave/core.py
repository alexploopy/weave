"""Weave orchestrator core: push/pull Claude Code sessions, plus remote/ls.

Owns ALL policy (id choice, cwd/sessionId rewrite, config resolution,
validation). Delegates mechanics to claude_connector_api (byte I/O),
transcript_api (entry editing), and a lazily-loaded `server` collaborator
(byte transport). Stdlib only. (`merge` is intentionally not implemented yet.)
"""

import configparser
import importlib
import os
import uuid
from pathlib import Path

import claude_connector_api as cc
import transcript_api as tx

_DEFAULT_CONFIG = ".weave/config"


class WeaveError(ValueError):
    """Any weave-layer error (unknown remote, empty history)."""


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
