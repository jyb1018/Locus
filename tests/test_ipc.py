import asyncio
import json
import os
import socket
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from locus.common import LocusError, NOTE, MAX_REQUEST, decode, encode
from locus.demo import run_scenario
from locus.local import read_secret
from locus.store import init_demo


def test_complete_ipc_scenario():
    result = asyncio.run(run_scenario("ipc"))
    assert result["result"] == "PASS"
    assert result["real_ai_host_integration"] == "NOT_TESTED"
    assert len(result["checks"]) >= 8


def test_two_concurrent_writes_with_one_revision_only_one_wins(daemon):
    a = daemon.client("client-a")
    sid = daemon.fixture["entities"]["shared"]
    rev = a.request("locus_get_entity", {"entity_id": sid})["predicates"][NOTE]["revision"]
    def write(index):
        try:
            return a.request("locus_record_claim", {"subject_id": sid, "predicate": NOTE,
                "value": f"writer-{index}", "idempotency_key": f"writer-{index}",
                "expected_subject_revision": rev})
        except LocusError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (1, 2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "VERSION_CONFLICT" in results


def test_second_daemon_does_not_unlink_live_socket(daemon):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run([sys.executable, "-m", "locus", "--home", str(daemon.home), "serve"],
                            env=env, capture_output=True, timeout=8)
    assert result.returncode != 0
    assert b"DAEMON_RUNNING" in result.stderr
    assert daemon.client("client-a").request("ping")["ready"]


def test_initializer_never_overwrites_running_or_existing_state(daemon):
    with pytest.raises(LocusError, match="DAEMON_RUNNING"):
        init_demo(daemon.home)
    daemon.stop()
    with pytest.raises(LocusError, match="ALREADY_INITIALIZED"):
        init_demo(daemon.home)


def raw_request(daemon, raw):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(6)
        sock.connect(str(daemon.home / "locus.sock"))
        sock.sendall(raw)
        with sock.makefile("rb") as file:
            return decode(file.readline())


@pytest.mark.parametrize("raw", [b"not-json\n", b"[]\n", b'{"token":null}\n',
                                  b'{"a":1,"a":2}\n', b'{"x":NaN}\n'])
def test_invalid_frames_do_not_crash_daemon(daemon, raw):
    result = raw_request(daemon, raw)
    assert result["ok"] is False
    assert daemon.client("client-a").request("ping")["ready"]


def test_oversized_frame_is_bounded_and_connection_closes(daemon):
    result = raw_request(daemon, b"x" * (MAX_REQUEST + 64) + b"\n")
    assert result["ok"] is False
    assert daemon.client("client-a").request("ping")["ready"]


def test_file_modes_are_private(daemon):
    assert stat.S_IMODE(daemon.home.stat().st_mode) == 0o700
    for name in ("state.sqlite3", "state.sqlite3-wal", "state.sqlite3-shm", "client-a.token",
                 "client-b.token", "owner.token", "fixture.json", "daemon.lock", "locus.sock"):
        path = daemon.home / name
        if path.exists():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600, name


def test_world_readable_token_is_rejected(daemon):
    path = daemon.home / "client-a.token"
    path.chmod(0o644)
    with pytest.raises(LocusError, match="UNSAFE_PATH"):
        daemon.client("client-a").request("ping")


def test_symlink_token_is_rejected(daemon):
    path = daemon.home / "alias.token"
    path.symlink_to(daemon.home / "client-a.token")
    with pytest.raises(LocusError, match="UNSAFE_PATH"):
        read_secret(path)


def test_reconnect_after_graceful_restart(daemon):
    client = daemon.client("client-a")
    daemon.stop()
    with pytest.raises(LocusError, match="DAEMON_UNAVAILABLE"):
        client.request("ping")
    daemon.start()
    assert client.request("ping")["ready"]


def test_unknown_credentials_do_not_leak_identity(daemon):
    result = raw_request(daemon, encode({"token": "x" * 43, "method": "locus_search", "params": {}}) + b"\n")
    assert result["error"]["code"] == "UNAUTHENTICATED"
    assert "principal_" not in json.dumps(result)
