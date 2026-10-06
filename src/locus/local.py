"""POSIX local boundary. This does NOT isolate malicious code under the same UID."""
from __future__ import annotations

import fcntl
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .common import LocusError


def home_path(value: str | Path) -> Path:
    # Do not resolve a final symlink silently. Parent path is owner-controlled.
    return Path(os.path.abspath(Path(value).expanduser()))


def check_private(path: Path, *, directory: bool = False) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise LocusError("NOT_INITIALIZED", "Run init-demo in a new private directory first.") from exc
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise LocusError("UNSAFE_PATH", "Expected an owner-only directory/file, without symlinks.")
    if not directory and info.st_nlink != 1:
        raise LocusError("UNSAFE_PATH", "Hard-linked state or credential files are not accepted.")


def create_private(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())


def read_secret(path: Path) -> str:
    check_private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as file:
        info = os.fstat(file.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise LocusError("UNSAFE_PATH", "Unsafe credential file.")
        raw = file.read(513)
    try:
        value = raw.decode("ascii").strip()
    except UnicodeError as exc:
        raise LocusError("UNAUTHENTICATED", "Invalid credential file.") from exc
    if not 32 <= len(value) <= 128:
        raise LocusError("UNAUTHENTICATED", "Invalid credential file.")
    return value


def socket_path(home: Path) -> Path:
    path = home / "locus.sock"
    if len(os.fsencode(path)) > 100:
        raise LocusError("SOCKET_PATH_TOO_LONG", "Choose a shorter LOCUS_HOME (Unix socket limit).")
    return path


@contextmanager
def exclusive_lock(home: Path) -> Iterator[None]:
    check_private(home, directory=True)
    path = home / "daemon.lock"
    if path.exists() or path.is_symlink():
        check_private(path)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise LocusError("UNSAFE_PATH", "Unsafe lock file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LocusError("DAEMON_RUNNING", "Another daemon or initializer owns this directory.") from exc
        yield
    finally:
        os.close(fd)  # Never unlink the lock inode: would break concurrent ownership.
