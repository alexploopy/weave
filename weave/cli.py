"""argparse CLI for weave: push / pull / remote add / ls.

Thin marshalling over weave.core. (`merge` is deferred.)
"""

import argparse
import sys

from weave import core


def _build_parser():
    p = argparse.ArgumentParser(prog="weave")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("push", help="upload a local session to a remote")
    sp.add_argument("remote")
    sp.add_argument("name")
    sp.add_argument("--session", required=True, dest="session_id")

    pl = sub.add_parser("pull", help="download a remote session locally")
    pl.add_argument("remote")
    pl.add_argument("name")

    rm = sub.add_parser("remote", help="manage remotes")
    rmsub = rm.add_subparsers(dest="remote_cmd", required=True)
    rma = rmsub.add_parser("add", help="register a remote")
    rma.add_argument("name")
    rma.add_argument("url")

    lsp = sub.add_parser("ls", help="list local (or remote) sessions")
    lsp.add_argument("remote", nargs="?", default=None)

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
    except ValueError as e:
        print(f"weave: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
