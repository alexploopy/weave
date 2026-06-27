"""Local-filesystem connector for Claude Code session JSONL.

A dumb I/O boundary: translate a Claude Code session id <-> a file path on a
unix ~/.claude, and move bytes in and out of those paths. No JSON parsing, no
field rewriting, no session-id generation -- those live in the weave layer.

Storage base honors $CLAUDE_CONFIG_DIR if set, else ~/.claude. Stdlib only.
"""

import os
import re
from pathlib import Path

_ENCODE_RE = re.compile(r"[^A-Za-z0-9]")


class SessionNotFound(ValueError):
    """A read target (session id or path) does not exist."""


class AmbiguousSession(ValueError):
    """A session id matches files in more than one project directory."""


# --- path mechanics (pure, no I/O) -------------------------------------------
def projects_root():
    """`$CLAUDE_CONFIG_DIR/projects` if the env var is set, else
    `~/.claude/projects` (expanded). Read at call time."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(base) if base else Path("~/.claude")
    return root.expanduser() / "projects"


def encode_cwd(cwd):
    """The Claude Code project-dir encoding: every non-alphanumeric character
    becomes '-' (e.g. '/Users/bob/myapp' -> '-Users-bob-myapp')."""
    return _ENCODE_RE.sub("-", cwd)


def session_path(cwd, session_id):
    """Where a session for `cwd` with id `session_id` lives on this machine."""
    return projects_root() / encode_cwd(cwd) / f"{session_id}.jsonl"


# --- resolution / enumeration ------------------------------------------------
def resolve(session_id):
    """The path of the session with this id, or None. Raises AmbiguousSession
    if the id exists in more than one project dir (e.g. after a copy)."""
    matches = sorted(projects_root().glob(f"*/{session_id}.jsonl"))
    if not matches:
        return None
    if len(matches) > 1:
        dirs = ", ".join(m.parent.name for m in matches)
        raise AmbiguousSession(
            f"session id {session_id!r} found in {len(matches)} project "
            f"dirs: {dirs}")
    return matches[0]


def list_sessions():
    """(session_id, path) for every session file under the root, sorted by
    path. session_id is the filename stem."""
    return sorted(
        ((p.stem, p) for p in projects_root().glob("*/*.jsonl")),
        key=lambda pair: str(pair[1]))
