"""Small, shared wire contract; never accept authority from request content."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

MAX_REQUEST = 32 * 1024
MAX_RESPONSE = 48 * 1024  # SDK structured + text representation stays below 128 KiB.
TIMEOUT = 5.0
NOTE = "locus.note"
PRIVATE_NOTE = "locus.private.note"
STATUS = "locus.project.implementation_status"
PREDICATES = (NOTE, PRIVATE_NOTE, STATUS)
STATUS_VALUES = ("not_started", "in_progress", "blocked", "reported_complete")


class LocusError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def wire(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": self.message}}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError("non-finite JSON number")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LocusError("INVALID_REQUEST", "Expected bounded, valid JSON.") from exc


def fields(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or not required <= value.keys():
        raise LocusError("INVALID_ARGUMENT", "Required fields are missing.")
    if value.keys() - required - (optional or set()):
        raise LocusError("INVALID_ARGUMENT", "Unknown fields are not accepted.")
    return value


def text(value: Any, name: str, maximum: int = 128, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise LocusError("INVALID_ARGUMENT", f"{name} must be a string.")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise LocusError("INVALID_ARGUMENT", f"{name} is not valid UTF-8.") from exc
    if size > maximum or (not empty and not value.strip()) or "\x00" in value:
        raise LocusError("INVALID_ARGUMENT", f"{name} is empty or exceeds its limit.")
    return value


def bounded(result: dict[str, Any]) -> dict[str, Any]:
    if len(encode(result)) > MAX_RESPONSE:
        raise LocusError("RESPONSE_TOO_LARGE", "Narrow the query; no partial claim projection returned.")
    return result
