"""Private, bounded JSON-over-Unix-socket transport (not an HTTP endpoint)."""
from __future__ import annotations

import asyncio
import os
import signal
import socket
import stat
from pathlib import Path
from typing import Any

from .common import LocusError, MAX_REQUEST, MAX_RESPONSE, TIMEOUT, decode, encode
from .local import check_private, exclusive_lock, home_path, read_secret, socket_path
from .store import Store


class IPCClient:
    def __init__(self, home: str | Path, token_file: str | Path):
        self.home = home_path(home)
        self.token_file = home_path(token_file)

    def request(self, method: str, params: dict | None = None) -> dict[str, Any]:
        check_private(self.home, directory=True)
        token = read_secret(self.token_file)
        raw = encode({"token": token, "method": method, "params": {} if params is None else params}) + b"\n"
        if len(raw) > MAX_REQUEST:
            raise LocusError("REQUEST_TOO_LARGE", "IPC request exceeds 32 KiB.")
        path = socket_path(self.home)
        sent = False
        try:
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise LocusError("UNSAFE_PATH", "Unsafe daemon socket.")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(TIMEOUT)
                sock.connect(str(path))
                # Once transmission starts, mutation outcome might be unknown on disconnect.
                sent = True
                sock.sendall(raw)
                with sock.makefile("rb") as file:
                    response = file.readline(MAX_RESPONSE + 2)
            if not response.endswith(b"\n") or len(response) > MAX_RESPONSE + 1:
                raise OSError("invalid daemon response")
            result = decode(response)
            if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                raise OSError("invalid daemon response")
            if not result["ok"]:
                raise LocusError(result["error"]["code"], result["error"]["message"])
            return result["result"]
        except (OSError, ValueError, KeyError) as exc:
            mutation = method == "locus_record_claim" or method.startswith("owner.")
            code = "OUTCOME_UNKNOWN" if sent and mutation else "DAEMON_UNAVAILABLE"
            raise LocusError(code, "Daemon unavailable; retry claims only with the original idempotency key.") from exc


async def serve(directory: str | Path) -> None:
    home = home_path(directory)
    path = socket_path(home)
    os.umask(0o077)
    with exclusive_lock(home):
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise LocusError("UNSAFE_PATH", "Refusing to replace a non-socket path.")
            path.unlink()  # Owner lock proves that this is a stale daemon socket.
        store = Store(home)
        tasks: set[asyncio.Task] = set()
        stopping = asyncio.Event()
        loop = asyncio.get_running_loop()
        bound = False

        async def connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            current = asyncio.current_task()
            assert current is not None
            tasks.add(current)
            try:
                if len(tasks) > 64:
                    return
                try:
                    raw = await asyncio.wait_for(reader.readline(), timeout=TIMEOUT)
                    if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST:
                        raise LocusError("REQUEST_TOO_LARGE", "Expected one bounded newline-delimited request.")
                    result = store.handle(decode(raw))
                except LocusError as exc:
                    result = exc.wire()
                except (ValueError, UnicodeError, RecursionError, asyncio.TimeoutError):
                    result = LocusError("INVALID_REQUEST", "Malformed, oversized or incomplete request.").wire()
                except Exception:
                    # Never serialize exceptions, SQL, credentials or note text to clients/logs.
                    result = LocusError("INTERNAL_ERROR", "Request failed; no partial transaction was committed.").wire()
                writer.write(encode(result) + b"\n")
                await asyncio.wait_for(writer.drain(), timeout=TIMEOUT)
            except (OSError, asyncio.TimeoutError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
                tasks.discard(current)

        try:
            server = await asyncio.start_unix_server(connection, path=str(path), limit=MAX_REQUEST)
            bound = True
            os.chmod(path, 0o600)
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, stopping.set)
            async with server:
                await stopping.wait()
            # Stop admission, then drain bounded in-flight calls before closing SQLite.
            if tasks:
                _, pending = await asyncio.wait(tasks, timeout=TIMEOUT + 1)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
            if bound and path.exists():
                path.unlink()
            store.close()
