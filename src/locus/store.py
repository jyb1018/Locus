"""M0's deliberately small SQLite state store (one daemon owns all writes)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from .common import (
    LocusError, NOTE, PRIVATE_NOTE, STATUS, PREDICATES, STATUS_VALUES,
    bounded, encode, fields, now, text,
)
from .local import check_private, create_private, exclusive_lock, home_path, socket_path

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE principals (
    id TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL UNIQUE, role TEXT NOT NULL CHECK(role IN ('owner','agent')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE entities (id TEXT PRIMARY KEY, type TEXT NOT NULL, label TEXT NOT NULL);
CREATE TABLE grants (
    principal_id TEXT NOT NULL REFERENCES principals(id),
    subject_id TEXT NOT NULL REFERENCES entities(id), predicate TEXT NOT NULL,
    can_read INTEGER NOT NULL CHECK(can_read IN (0,1)),
    can_write INTEGER NOT NULL CHECK(can_write IN (0,1) AND can_write <= can_read),
    PRIMARY KEY(principal_id,subject_id,predicate)
);
CREATE TABLE claims (
    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES entities(id),
    predicate TEXT NOT NULL, value TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind='AGENT_INFERRED'),
    created_by TEXT NOT NULL REFERENCES principals(id), recorded_at TEXT NOT NULL,
    evidence_json TEXT NOT NULL, lifecycle TEXT NOT NULL CHECK(lifecycle IN ('ACTIVE','SUPERSEDED')),
    supersedes_claim_id TEXT REFERENCES claims(id)
);
CREATE INDEX claims_subject ON claims(subject_id,predicate,lifecycle);
CREATE TABLE receipts (
    principal_id TEXT NOT NULL REFERENCES principals(id), key TEXT NOT NULL,
    payload_digest TEXT NOT NULL, response_json TEXT NOT NULL,
    PRIMARY KEY(principal_id,key)
);
CREATE TABLE journal (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL, principal_id TEXT NOT NULL,
    subject_id TEXT, claim_id TEXT, recorded_at TEXT NOT NULL
);
"""


def new_id(prefix: str) -> str:
    return prefix + "_" + secrets.token_hex(12)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def init_demo(directory: str | Path) -> dict[str, Any]:
    """Owner-only, non-overwriting bootstrap. No real user data is collected."""
    home = home_path(directory)
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    check_private(home, directory=True)
    socket_path(home)
    with exclusive_lock(home):
        if any(p.name != "daemon.lock" for p in home.iterdir()):
            raise LocusError("ALREADY_INITIALIZED", "Refusing to overwrite a nonempty state directory.")
        create_private(home / "state.sqlite3", b"")
        db = sqlite3.connect(home / "state.sqlite3")
        result: dict[str, Any] = {"home": str(home), "principals": {}, "entities": {}}
        try:
            db.executescript(SCHEMA)
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            db.execute("INSERT INTO meta VALUES ('revision_key',?)", (secrets.token_hex(32),))
            for label, role in (("owner", "owner"), ("client-a", "agent"), ("client-b", "agent")):
                identifier, token = new_id("principal"), secrets.token_urlsafe(32)
                db.execute("INSERT INTO principals(id,label,token_hash,role) VALUES (?,?,?,?)",
                           (identifier, label, digest(token), role))
                filename = f"{label}.token"
                create_private(home / filename, (token + "\n").encode("ascii"))
                result["principals"][label] = {"id": identifier, "token_file": str(home / filename)}
            for label in ("shared", "private"):
                identifier = new_id("entity")
                db.execute("INSERT INTO entities VALUES (?,?,?)",
                           (identifier, "locus.demo.project", f"Locus M0 {label} fixture"))
                result["entities"][label] = identifier
            a = result["principals"]["client-a"]["id"]
            b = result["principals"]["client-b"]["id"]
            shared = result["entities"]["shared"]
            for principal, entity, predicate in [
                (a, shared, NOTE), (b, shared, NOTE),
                (a, shared, STATUS), (b, shared, STATUS),
                (a, shared, PRIVATE_NOTE), (a, result["entities"]["private"], NOTE),
            ]:
                db.execute("INSERT INTO grants VALUES (?,?,?,1,1)", (principal, entity, predicate))
            db.commit()
            create_private(home / "fixture.json", encode(result) + b"\n")
        finally:
            db.close()
    return result


class Store:
    """Synchronous core. Production callers are serialized by the daemon event loop."""

    def __init__(self, directory: str | Path):
        self.home = home_path(directory)
        check_private(self.home, directory=True)
        for filename in ("state.sqlite3", "state.sqlite3-wal", "state.sqlite3-shm", "state.sqlite3-journal"):
            path = self.home / filename
            if filename == "state.sqlite3" or path.exists() or path.is_symlink():
                check_private(path)
        self.db = sqlite3.connect(self.home / "state.sqlite3", timeout=3, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            self.db.close()
            raise LocusError("SCHEMA_MISMATCH", "Unsupported database version; no automatic reset.")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.key = bytes.fromhex(self.db.execute(
            "SELECT value FROM meta WHERE key='revision_key'").fetchone()[0])

    def close(self) -> None:
        self.db.close()

    def _authenticate(self, token: Any) -> sqlite3.Row:
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise LocusError("UNAUTHENTICATED", "Credential is invalid or revoked.")
        principal = self.db.execute(
            "SELECT id,role FROM principals WHERE token_hash=? AND enabled=1", (digest(token),)
        ).fetchone()
        if principal is None:
            raise LocusError("UNAUTHENTICATED", "Credential is invalid or revoked.")
        return principal

    def _allowed(self, pid: str, sid: str, predicate: str, write: bool = False) -> bool:
        column = "can_write" if write else "can_read"
        return self.db.execute(
            f"SELECT 1 FROM grants WHERE principal_id=? AND subject_id=? AND predicate=? AND {column}=1",
            (pid, sid, predicate),
        ).fetchone() is not None

    def _grants(self, pid: str, sid: str | None = None) -> list[sqlite3.Row]:
        query = "SELECT subject_id,predicate,can_write FROM grants WHERE principal_id=? AND can_read=1"
        args: tuple = (pid,)
        if sid is not None:
            query += " AND subject_id=?"
            args += (sid,)
        return self.db.execute(query + " ORDER BY subject_id,predicate", args).fetchall()

    def _opaque(self, value: Any) -> str:
        return hmac.new(self.key, encode(value), hashlib.sha256).hexdigest()

    def _readable_claim(self, pid: str, claim: sqlite3.Row, seen: set[str] | None = None) -> bool:
        # Re-check dependency ACLs on every read, including after a grant changes.
        if not self._allowed(pid, claim["subject_id"], claim["predicate"]):
            return False
        seen = set() if seen is None else seen
        if claim["id"] in seen or len(seen) >= 16:
            return False
        seen = seen | {claim["id"]}
        for ref in json.loads(claim["evidence_json"]):
            parent = self.db.execute("SELECT * FROM claims WHERE id=?", (ref,)).fetchone()
            if parent is None or not self._readable_claim(pid, parent, seen):
                return False
        return True

    def _visible_claims(self, pid: str, sid: str, predicate: str) -> list[sqlite3.Row]:
        rows = self.db.execute(
            "SELECT * FROM claims WHERE subject_id=? AND predicate=? ORDER BY recorded_at,id",
            (sid, predicate),
        ).fetchall()
        return [r for r in rows if self._readable_claim(pid, r)]

    def _revision(self, pid: str, sid: str, predicate: str) -> str:
        claims = self._visible_claims(pid, sid, predicate)
        return self._opaque({"principal": pid, "subject": sid, "predicate": predicate,
                             "write": self._allowed(pid, sid, predicate, True),
                             "claims": [[c["id"], c["lifecycle"]] for c in claims]})

    def _policy(self, pid: str) -> str:
        return self._opaque({"principal": pid, "grants": [dict(g) for g in self._grants(pid)]})

    def _project(self, pid: str, sid: str, predicate: str) -> dict[str, Any]:
        records = self._visible_claims(pid, sid, predicate)
        active = [c for c in records if c["lifecycle"] == "ACTIVE"]
        values = sorted({c["value"] for c in active})
        resolution = "UNKNOWN" if not values else (
            "CONFLICTED" if predicate == STATUS and len(values) > 1 else "RESOLVED")
        return {"resolution": resolution, "values": values,
                "revision": self._revision(pid, sid, predicate),
                "freshness": "UNKNOWN", "authority": "agent_reports_only",
                "claims": [{"claim_id": c["id"], "value": c["value"], "kind": c["kind"],
                            "created_by": c["created_by"], "recorded_at": c["recorded_at"],
                            "evidence_refs": json.loads(c["evidence_json"])} for c in active]}

    def _get_entity(self, pid: str, params: dict) -> dict:
        fields(params, {"entity_id"}, {"predicate"})
        sid = text(params["entity_id"], "entity_id")
        grants = self._grants(pid, sid)
        if "predicate" in params:
            selected = text(params["predicate"], "predicate")
            grants = [g for g in grants if g["predicate"] == selected]
        row = self.db.execute("SELECT * FROM entities WHERE id=?", (sid,)).fetchone()
        if not grants or row is None:
            raise LocusError("NOT_FOUND", "Entity was not found in your permitted scope.")
        body = {"entity": dict(row), "predicates": {
            g["predicate"]: self._project(pid, sid, g["predicate"]) for g in grants}}
        return {**body, "snapshot_token": self._opaque({"pid": pid, "view": body}),
                "policy_token": self._policy(pid), "generated_at": now(),
                "projection_version": "m0-agent-reports/1", "coverage": "PARTIAL",
                "freshness": "UNKNOWN", "reasons": ["synthetic_scope", "no_source_provider"],
                "truncated": False}

    def _search(self, pid: str, params: dict) -> dict:
        fields(params, set(), {"query", "limit"})
        query = text(params.get("query", ""), "query", 128, empty=True).casefold()
        limit = params.get("limit", 20)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise LocusError("INVALID_ARGUMENT", "limit must be an integer between 1 and 20.")
        # M0 is metadata-only. Filter ACLs before matching, counting or limiting.
        rows = self.db.execute(
            "SELECT DISTINCT e.* FROM entities e JOIN grants g ON e.id=g.subject_id "
            "WHERE g.principal_id=? AND g.can_read=1 ORDER BY e.label,e.id", (pid,)
        ).fetchall()
        visible = [dict(r) for r in rows if query in r["label"].casefold() or query in r["id"].casefold()]
        return {"items": visible[:limit], "truncated": len(visible) > limit,
                "next_cursor": None, "query_scope": "entity_metadata_only",
                "policy_token": self._policy(pid), "coverage": "PARTIAL", "freshness": "UNKNOWN",
                "reasons": ["narrow_query_if_truncated" ] if len(visible) > limit else []}

    def _audience(self, sid: str, predicate: str) -> set[str]:
        return {r[0] for r in self.db.execute(
            "SELECT principal_id FROM grants WHERE subject_id=? AND predicate=? AND can_read=1",
            (sid, predicate))}

    def _record(self, pid: str, params: dict) -> dict:
        fields(params, {"subject_id", "predicate", "value", "idempotency_key"},
               {"evidence_refs", "expected_subject_revision", "supersedes_claim_id"})
        sid = text(params["subject_id"], "subject_id")
        pred = text(params["predicate"], "predicate")
        value = text(params["value"], "value", 512)
        if len(encode(value)) > 512:
            raise LocusError("INVALID_ARGUMENT", "value exceeds 512 serialized UTF-8 bytes.")
        key = text(params["idempotency_key"], "idempotency_key")
        refs = params.get("evidence_refs", [])
        if not isinstance(refs, list) or len(refs) > 8:
            raise LocusError("INVALID_ARGUMENT", "evidence_refs must contain at most 8 claim IDs.")
        refs = [text(ref, "evidence_ref") for ref in refs]
        if len(refs) != len(set(refs)):
            raise LocusError("INVALID_ARGUMENT", "Duplicate evidence references.")
        expected, supersedes = params.get("expected_subject_revision"), params.get("supersedes_claim_id")
        if expected is not None:
            text(expected, "expected_subject_revision")
        if supersedes is not None:
            text(supersedes, "supersedes_claim_id")
        if pred not in PREDICATES:
            raise LocusError("UNKNOWN_PREDICATE", "Predicate is not registered in M0.")
        if not self._allowed(pid, sid, pred, True):
            raise LocusError("FORBIDDEN", "Claim write is not permitted.")
        if pred == STATUS and (value not in STATUS_VALUES or not refs):
            raise LocusError("INVALID_ARGUMENT", "Implementation status requires a supported value and evidence.")
        semantic = {"subject_id": sid, "predicate": pred, "value": value,
                    "evidence_refs": sorted(refs), "expected_subject_revision": expected,
                    "supersedes_claim_id": supersedes}
        payload_hash = hashlib.sha256(encode(semantic)).hexdigest()
        # Recheck present permissions before returning any cached receipt.
        for ref in refs:
            parent = self.db.execute("SELECT * FROM claims WHERE id=?", (ref,)).fetchone()
            if (parent is None or parent["subject_id"] != sid
                    or not self._readable_claim(pid, parent)):
                raise LocusError("INVALID_EVIDENCE", "Evidence is unavailable in the permitted scope.")
            if not self._audience(sid, pred) <= self._audience(sid, parent["predicate"]):
                raise LocusError("EVIDENCE_SCOPE", "Derived claim cannot have a broader audience than evidence.")
        receipt = self.db.execute("SELECT * FROM receipts WHERE principal_id=? AND key=?", (pid, key)).fetchone()
        if receipt:
            if receipt["payload_digest"] != payload_hash:
                raise LocusError("IDEMPOTENCY_CONFLICT", "Key was already used for another semantic input.")
            return json.loads(receipt["response_json"])
        if expected is not None and expected != self._revision(pid, sid, pred):
            raise LocusError("VERSION_CONFLICT", "Predicate revision changed or belongs to another scope.")
        if supersedes is not None:
            if expected is None:
                raise LocusError("INVALID_ARGUMENT", "Supersession requires expected_subject_revision.")
            old = self.db.execute("SELECT * FROM claims WHERE id=?", (supersedes,)).fetchone()
            if (old is None or old["subject_id"] != sid or old["predicate"] != pred
                    or old["created_by"] != pid or old["lifecycle"] != "ACTIVE"):
                raise LocusError("FORBIDDEN", "Only an active claim of your own in this predicate can be replaced.")
            if supersedes in refs:
                raise LocusError("INVALID_EVIDENCE", "A replaced claim cannot justify its replacement.")
            self.db.execute("UPDATE claims SET lifecycle='SUPERSEDED' WHERE id=?", (supersedes,))
        total = self.db.execute(
            "SELECT count(*) FROM claims WHERE subject_id=? AND predicate=?", (sid, pred)).fetchone()[0]
        if total >= 16:
            raise LocusError("RESOURCE_LIMIT", "M0 limits each entity/predicate to 16 reports; use a new demo directory.")
        cid = new_id("claim")
        self.db.execute("INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (cid, sid, pred, value, "AGENT_INFERRED", pid, now(),
                         json.dumps(sorted(refs)), "ACTIVE", supersedes))
        self._journal("locus.core.claim_recorded", pid, sid, cid)
        projection = self._project(pid, sid, pred)
        result = {"accepted": True, "claim_id": cid, "kind": "AGENT_INFERRED", "created_by": pid,
                  "write_receipt": new_id("receipt"), "subject_revision": projection["revision"],
                  "projection_status": projection["resolution"], "truth_verified": False}
        self.db.execute("INSERT INTO receipts VALUES (?,?,?,?)", (pid, key, payload_hash, encode(result).decode()))
        return result

    def _journal(self, event: str, pid: str, sid: str | None = None, cid: str | None = None) -> None:
        # Refer to canonical records; never log credential values or duplicate note text.
        self.db.execute(
            "INSERT INTO journal(event_id,event_type,principal_id,subject_id,claim_id,recorded_at) VALUES (?,?,?,?,?,?)",
            (new_id("event"), event, pid, sid, cid, now()))

    def _owner(self, pid: str, method: str, params: dict) -> dict:
        if method == "owner.revoke":
            fields(params, {"principal_id"})
            target = text(params["principal_id"], "principal_id")
            row = self.db.execute("SELECT role FROM principals WHERE id=?", (target,)).fetchone()
            if row is None or row["role"] != "agent":
                raise LocusError("NOT_FOUND", "Agent principal not found.")
            self.db.execute("UPDATE principals SET enabled=0 WHERE id=?", (target,))
            self._journal("locus.core.credential_revoked", pid, target)
            return {"revoked": target}
        if method == "owner.set_grant":
            fields(params, {"principal_id", "subject_id", "predicate", "read", "write"})
            target = text(params["principal_id"], "principal_id")
            sid = text(params["subject_id"], "subject_id")
            pred = text(params["predicate"], "predicate")
            read, write = params["read"], params["write"]
            if type(read) is not bool or type(write) is not bool or (write and not read) or pred not in PREDICATES:
                raise LocusError("INVALID_ARGUMENT", "Invalid exact-scope grant.")
            target_row = self.db.execute("SELECT role FROM principals WHERE id=?", (target,)).fetchone()
            if target_row is None or target_row["role"] != "agent":
                raise LocusError("NOT_FOUND", "Agent principal not found.")
            if self.db.execute("SELECT 1 FROM entities WHERE id=?", (sid,)).fetchone() is None:
                raise LocusError("NOT_FOUND", "Entity not found.")
            self.db.execute(
                "INSERT INTO grants VALUES (?,?,?,?,?) ON CONFLICT(principal_id,subject_id,predicate) "
                "DO UPDATE SET can_read=excluded.can_read,can_write=excluded.can_write",
                (target, sid, pred, int(read), int(write)))
            self._journal("locus.core.grant_changed", pid, sid)
            return {"updated": True}
        raise LocusError("METHOD_NOT_FOUND", "Unknown owner operation.")

    def handle(self, request: Any) -> dict:
        fields(request, {"token", "method", "params"})
        method = text(request["method"], "method")
        if not isinstance(request["params"], dict):
            raise LocusError("INVALID_ARGUMENT", "params must be an object.")
        # A single transaction includes validation, projection, journal and receipt.
        self.db.execute("BEGIN IMMEDIATE" if method in (
            "locus_record_claim", "owner.revoke", "owner.set_grant") else "BEGIN")
        try:
            principal = self._authenticate(request["token"])
            pid, role = principal["id"], principal["role"]
            params = request["params"]
            if method == "ping":
                fields(params, set())
                result = {"ready": True, "schema_version": SCHEMA_VERSION}
            elif method.startswith("owner."):
                if role != "owner":
                    raise LocusError("FORBIDDEN", "Owner credential required.")
                result = self._owner(pid, method, params)
            else:
                if role != "agent":
                    raise LocusError("FORBIDDEN", "Use a restricted agent credential for MCP.")
                if method == "tools.list":
                    fields(params, set())
                    grants = self._grants(pid)
                    names = ["locus_get_entity", "locus_search"] if grants else []
                    if any(g["can_write"] for g in grants):
                        names.append("locus_record_claim")
                    result = {"tools": names}
                elif method == "locus_get_entity":
                    result = self._get_entity(pid, params)
                elif method == "locus_search":
                    result = self._search(pid, params)
                elif method == "locus_record_claim":
                    result = self._record(pid, params)
                else:
                    raise LocusError("METHOD_NOT_FOUND", "Unsupported operation.")
            response = bounded({"ok": True, "result": result})
            self.db.commit()
            return response
        except BaseException:
            self.db.rollback()
            raise
