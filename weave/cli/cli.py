"""argparse CLI for weave: push / pull / remote add / ls / merge.

Thin marshalling over weave.core.
"""

import argparse
import sys

from weave import core
from weave.merge.exceptions import MergeError


def _build_parser():
    p = argparse.ArgumentParser(prog="weave")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("push", help="upload a local session to a remote")
    sp.add_argument("remote", nargs="?", default=None,
                    help="remote name (optional when only one is configured)")
    sp.add_argument("name")
    sp.add_argument("--session", required=True, dest="session_id")

    pl = sub.add_parser("pull", help="download a remote session locally")
    pl.add_argument("remote", nargs="?", default=None,
                    help="remote name (optional when only one is configured)")
    pl.add_argument("name")

    rm = sub.add_parser("remote", help="manage remotes")
    rmsub = rm.add_subparsers(dest="remote_cmd", required=True)
    rma = rmsub.add_parser("add", help="register a remote")
    rma.add_argument("name")
    rma.add_argument("url")

    lsp = sub.add_parser("ls", help="list local (or remote) sessions")
    lsp.add_argument("remote", nargs="?", default=None)

    mg = sub.add_parser("merge", help="merge two sessions into a new resumable session")
    mg.add_argument("source_a")
    mg.add_argument("source_b")

    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "push":
            core.push(args.remote, args.name, args.session_id)
            print(f"pushed {args.session_id} -> {args.remote}/{args.name}")
        elif args.cmd == "pull":
            new_id = core.pull(args.remote, args.name)
            print(f"pulled into {new_id}\n  resume: claude --resume {new_id}")
        elif args.cmd == "remote":
            core.remote_add(args.name, args.url)
            print(f"remote {args.name!r} set")
        elif args.cmd == "ls":
            for sid in core.ls(args.remote):
                print(sid)
        elif args.cmd == "merge":
            result = core.merge(args.source_a, args.source_b)
            print(f"merged into {result.session_id}\n"
                  f"  resume: claude --resume {result.session_id}")
    except (ValueError, MergeError) as e:
        print(f"weave: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
