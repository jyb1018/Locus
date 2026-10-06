"""Explicit owner bootstrap/admin CLI, separate from the agent tool surface."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from .common import LocusError, encode
from .ipc import IPCClient, serve
from .local import home_path
from .store import init_demo


def main() -> None:
    parser = argparse.ArgumentParser(prog="locus", description="Locus M0 local shared-state spike")
    parser.add_argument("--home", default=os.environ.get("LOCUS_HOME", "~/.locus-m0"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-demo", help="Create synthetic fixtures and restricted credentials; never overwrite")
    sub.add_parser("serve", help="Run the one foreground local daemon")
    adapter = sub.add_parser("mcp", help="Run one MCP stdio adapter; requires the mcp extra")
    adapter.add_argument("--token-file", default=os.environ.get("LOCUS_TOKEN_FILE"))
    config = sub.add_parser("config", help="Print a generic MCP host configuration, without secret values")
    config.add_argument("--client", choices=["client-a", "client-b"], required=True)
    call = sub.add_parser("call", help="Call a core method over IPC (diagnostics, not an AI host)")
    call.add_argument("--token-file", required=True)
    call.add_argument("method")
    call.add_argument("params", nargs="?", default="{}")
    owner = sub.add_parser("owner", help="Owner-only local administration")
    owner_sub = owner.add_subparsers(dest="operation", required=True)
    revoke = owner_sub.add_parser("revoke")
    revoke.add_argument("principal_id")
    grant = owner_sub.add_parser("set-grant")
    grant.add_argument("principal_id")
    grant.add_argument("subject_id")
    grant.add_argument("predicate")
    grant.add_argument("--read", action="store_true")
    grant.add_argument("--write", action="store_true")
    args = parser.parse_args()
    home = home_path(args.home)
    try:
        if args.command == "init-demo":
            result = init_demo(home)
        elif args.command == "serve":
            asyncio.run(serve(home))
            return
        elif args.command == "mcp":
            if not args.token_file:
                raise LocusError("CONFIG_REQUIRED", "Provide --token-file or LOCUS_TOKEN_FILE.")
            from .mcp_adapter import run
            asyncio.run(run(home, home_path(args.token_file)))
            return
        elif args.command == "config":
            result = {"mcpServers": {"locus": {
                "command": sys.executable,
                "args": ["-m", "locus", "--home", str(home), "mcp", "--token-file",
                         str(home / f"{args.client}.token")],
            }}}
        elif args.command == "call":
            result = IPCClient(home, args.token_file).request(args.method, json.loads(args.params))
        elif args.command == "owner":
            client = IPCClient(home, home / "owner.token")
            if args.operation == "revoke":
                result = client.request("owner.revoke", {"principal_id": args.principal_id})
            else:
                result = client.request("owner.set_grant", {
                    "principal_id": args.principal_id, "subject_id": args.subject_id,
                    "predicate": args.predicate, "read": args.read, "write": args.write})
        else:
            raise AssertionError("unreachable CLI command")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except LocusError as exc:
        print(encode(exc.wire()).decode(), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError):
        print('Invalid local path, permissions or JSON input. No credentials were logged.', file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
