"""Reproducible two-client smoke test, never using the owner's real files or AI accounts."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import AsyncExitStack
from pathlib import Path

from .common import LocusError, NOTE, PRIVATE_NOTE, STATUS
from .ipc import IPCClient
from .store import init_demo


class DemoDaemon:
    """Foreground child lifetime is always explicitly joined by this harness."""
    def __init__(self, home: Path):
        self.home = home
        self.fixture = init_demo(home)
        self.process: subprocess.Popen | None = None

    def client(self, label: str) -> IPCClient:
        return IPCClient(self.home, self.home / f"{label}.token")

    def start(self) -> None:
        if self.process is not None:
            raise RuntimeError("daemon is already started")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "locus", "--home", str(self.home), "serve"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                _, err = self.process.communicate()
                self.process = None
                raise RuntimeError("daemon failed to start: " + err.decode(errors="replace"))
            try:
                if self.client("owner").request("ping")["ready"]:
                    return
            except LocusError:
                time.sleep(0.03)
        self.stop()
        raise RuntimeError("daemon readiness timeout")

    def stop(self, *, kill: bool = False) -> None:
        if self.process is None:
            return
        process, self.process = self.process, None
        if process.poll() is None:
            process.kill() if kill else process.terminate()
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)
            raise RuntimeError("daemon did not shut down cleanly")


async def run_scenario(transport: str = "mcp") -> dict:
    async with AsyncExitStack() as stack:
        folder = stack.enter_context(tempfile.TemporaryDirectory(prefix="locus-m0-", dir="/tmp"))
        daemon = DemoDaemon(Path(folder) / "state")
        stack.callback(daemon.stop)
        daemon.start()
        fixture = daemon.fixture
        shared = fixture["entities"]["shared"]
        checks: list[str] = []
        sessions: dict = {}
        if transport == "mcp":
            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client
            except ImportError as exc:
                raise LocusError("MCP_NOT_INSTALLED", 'Install -e ".[dev]" to run SDK/stdio integration.') from exc
            for label in ("client-a", "client-b"):
                params = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "locus", "--home", str(daemon.home), "mcp", "--token-file",
                          str(daemon.home / f"{label}.token")],
                    env={"PYTHONPATH": str(Path(__file__).resolve().parents[1])})
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                sessions[label] = session
            checks.append("two_independent_sdk_stdio_sessions")

        async def call(label: str, name: str, params: dict) -> dict:
            if transport == "ipc":
                return await asyncio.to_thread(daemon.client(label).request, name, params)
            result = await sessions[label].call_tool(name, params)
            payload = result.structuredContent
            if payload is None:
                payload = json.loads(result.content[0].text)
            if not payload["ok"]:
                raise LocusError(payload["error"]["code"], payload["error"]["message"])
            assert not result.isError
            return payload["result"]

        note_args = {"subject_id": shared, "predicate": NOTE, "value": "M0 synthetic handoff note",
                     "idempotency_key": "demo-shared-note"}
        note = await call("client-a", "locus_record_claim", note_args)
        retry = await call("client-a", "locus_record_claim", note_args)
        assert note == retry
        checks.append("idempotent_write_receipt")
        state = await call("client-b", "locus_get_entity", {"entity_id": shared})
        assert note["claim_id"] in [c["claim_id"] for c in state["predicates"][NOTE]["claims"]]
        assert state["predicates"][NOTE]["claims"][0]["kind"] == "AGENT_INFERRED"
        checks.append("shared_note_with_provenance")
        await call("client-a", "locus_record_claim", {
            "subject_id": shared, "predicate": PRIVATE_NOTE, "value": "synthetic-private-marker",
            "idempotency_key": "demo-private-note"})
        visible = await call("client-b", "locus_get_entity", {"entity_id": shared})
        assert visible["snapshot_token"] == state["snapshot_token"]
        assert PRIVATE_NOTE not in visible["predicates"]
        checks.append("private_predicate_and_snapshot_isolation")
        try:
            await call("client-b", "locus_get_entity", {"entity_id": fixture["entities"]["private"]})
            raise AssertionError("hidden entity was disclosed")
        except LocusError as exc:
            assert exc.code == "NOT_FOUND"
        checks.append("hidden_entity_denied")
        for label, value in (("client-a", "in_progress"), ("client-b", "reported_complete")):
            await call(label, "locus_record_claim", {
                "subject_id": shared, "predicate": STATUS, "value": value,
                "evidence_refs": [note["claim_id"]], "idempotency_key": f"demo-status-{label}"})
        state = await call("client-b", "locus_get_entity", {"entity_id": shared})
        assert state["predicates"][STATUS]["resolution"] == "CONFLICTED"
        checks.append("conflicting_reports_preserved")
        daemon.stop(kill=True)  # Exercise WAL/crash recovery, not just clean shutdown.
        try:
            await call("client-a", "locus_get_entity", {"entity_id": shared})
            raise AssertionError("read should fail while daemon is down")
        except LocusError as exc:
            assert exc.code == "DAEMON_UNAVAILABLE"
        daemon.start()
        recovered = await call("client-b", "locus_get_entity", {"entity_id": shared})
        assert recovered["snapshot_token"] == state["snapshot_token"]
        assert await call("client-a", "locus_record_claim", note_args) == note
        checks.append("crash_restart_and_same_adapter_reconnect")
        owner = daemon.client("owner")
        bid = fixture["principals"]["client-b"]["id"]
        for pred in (NOTE, STATUS):
            owner.request("owner.set_grant", {"principal_id": bid, "subject_id": shared,
                                             "predicate": pred, "read": True, "write": False})
        if transport == "mcp":
            names = {t.name for t in (await sessions["client-b"].list_tools()).tools}
            assert "locus_record_claim" not in names
            checks.append("dynamic_read_only_tool_list")
        # Core enforces the same grant even when an old host caches tools/list.
        try:
            daemon.client("client-b").request("locus_record_claim", {
                **note_args, "idempotency_key": "forbidden-write"})
            raise AssertionError("read-only principal wrote a claim")
        except LocusError as exc:
            assert exc.code == "FORBIDDEN"
        checks.append("read_only_enforced_on_call")
        owner.request("owner.revoke", {"principal_id": bid})
        try:
            await call("client-b", "locus_get_entity", {"entity_id": shared})
            raise AssertionError("revoked credential read state")
        except LocusError as exc:
            assert exc.code == "UNAUTHENTICATED"
        checks.append("live_credential_revocation")
        return {"result": "PASS", "transport": transport, "checks": checks,
                "real_ai_host_integration": "NOT_TESTED", "source_files_collected": 0,
                "llm_calls": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("mcp", "ipc"), default="mcp")
    args = parser.parse_args()
    try:
        report = asyncio.run(run_scenario(args.transport))
    except LocusError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
