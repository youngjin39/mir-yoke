"""SQLite store — connection + migration runner + audit chain helpers.

BORROWED-FROM: codenamev/claude_memory@d0e523cd06d6adeae4744d89736f79564d9db41d
  lib/claude_memory/store/sqlite_store.rb#SqliteStore
License: MIT
Changes:
  - Ruby store and migration runner adapted to Python sqlite3.
  - facts/content/audit tables split for Mir Engine policy boundaries.
  - sqlite-vec loading is best-effort with FTS5 fallback.

design §5 (schema) · §9.8 (migration path) · §9.9 (sqlite-vec degradation) ·
§9.10 (WAL + Engine-only write lock) · §5.3 (audit_log hash chain · R6).

All paths come from `ResolvedConfig` or explicit caller arguments — never
hard-coded here. sqlite-vec loading is best-effort; a missing extension
falls back to FTS5-only mode and records the reason on the connection.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

log = logging.getLogger("mir.memory.store")

# A migration filename = NNN_snake_name.sql. Anything else is ignored so
# developers can drop README.md / notes into the package without breaking
# discovery.
_MIGRATION_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


# --- Connection management ---

def _load_sqlite_vec(conn: sqlite3.Connection) -> tuple[bool, str | None]:
    """Try to load sqlite-vec extension. Returns (loaded, reason_if_not).

    Graceful degradation per §9.9: callers can still do FTS5 keyword queries.
    """
    try:
        import sqlite_vec  # type: ignore[import-untyped]
    except ImportError as e:
        return False, f"sqlite-vec package not installed: {e}"
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    except Exception as e:  # sqlite without SQLITE_ENABLE_LOAD_EXTENSION etc.
        return False, f"load_extension failed: {e}"
    finally:
        try:
            conn.enable_load_extension(False)  # F4: no further ext loading
        except Exception:
            pass
    return True, None


@dataclass(frozen=True)
class Connection:
    """Thin wrapper so callers can inspect vec availability without coupling
    to the raw sqlite3 module."""

    conn: sqlite3.Connection
    vec_available: bool
    vec_reason: str | None


def connect(
    db_path: Path,
    *,
    load_vec: bool = True,
    timeout: float | None = None,
) -> Connection:
    """Open `db_path`, apply PRAGMAs, optionally load sqlite-vec.

    The caller is responsible for `close()` via `conn.conn.close()`.

    ``timeout`` is forwarded to :func:`sqlite3.connect` when supplied.
    Default (``None``) keeps sqlite3's built-in 5 s busy-wait. Pass ``0``
    to fail immediately on ``SQLITE_BUSY`` — CLI commands that must not
    hang (e.g. ``mir phase advance``) set this explicitly (wave 2 SM5).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if timeout is not None:
        raw = sqlite3.connect(db_path, timeout=timeout)
    else:
        raw = sqlite3.connect(db_path)
    raw.execute("PRAGMA journal_mode = WAL")
    raw.execute("PRAGMA synchronous = NORMAL")
    raw.execute("PRAGMA foreign_keys = ON")
    if load_vec:
        ok, reason = _load_sqlite_vec(raw)
        if not ok:
            log.warning("sqlite-vec unavailable, FTS5-only mode: %s", reason)
        return Connection(raw, ok, reason)
    return Connection(raw, False, "vec loading disabled by caller")


# --- Migration runner ---

@dataclass(frozen=True)
class MigrationEntry:
    version: str
    name: str
    body: str


def _iter_migrations() -> Iterable[MigrationEntry]:
    root = files("mir.core.engine.memory.migrations")
    pairs: list[tuple[str, str, str]] = []
    for res in root.iterdir():  # type: ignore[union-attr]
        m = _MIGRATION_RE.match(res.name)
        if not m:
            continue
        pairs.append((m.group(1), res.name, res.read_text(encoding="utf-8")))
    pairs.sort(key=lambda row: row[0])
    for version, name, body in pairs:
        yield MigrationEntry(version=version, name=name, body=body)


_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  applied_at TEXT NOT NULL
);
""".strip()


def _iter_complete_statements(body: str) -> Iterator[str]:
    """Split a migration body into complete SQL statements.

    ``sqlite3.complete_statement`` knows when a ``BEGIN … END;`` block
    (CREATE TRIGGER bodies etc.) is closed, which a naive ``body.split(';')``
    does not. We need this because we apply migrations via per-statement
    ``execute()`` rather than ``executescript()`` — the latter issues an
    implicit ``COMMIT`` before running, which silently breaks the
    rollback-on-failure contract.
    """
    buffer = ""
    for line in body.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            stmt = buffer.strip()
            if stmt:
                yield stmt
            buffer = ""
    tail = buffer.strip()
    if tail:
        yield tail


def apply_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply any pending migrations in version order. Returns the versions
    that were newly applied this call (empty = already up to date).

    Each migration runs inside a manual BEGIN/COMMIT. A failure inside the
    migration body → ``ROLLBACK`` → ``schema_migrations`` row is not written
    → the next call retries from a clean slate. This requires we *not* use
    ``executescript()`` (which auto-commits), so statements are split via
    ``_iter_complete_statements`` and fed through ``execute()``.
    """
    # schema_migrations table is created up front (idempotent). Safe to
    # ``executescript`` here because there is nothing to roll back.
    conn.executescript(_SCHEMA_MIGRATIONS_DDL)
    applied_before = {
        row[0]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    newly_applied: list[str] = []
    for mig in _iter_migrations():
        if mig.version in applied_before:
            continue
        try:
            conn.execute("BEGIN")
            for stmt in _iter_complete_statements(mig.body):
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) "
                "VALUES (?, ?, ?)",
                (mig.version, mig.name, _now_iso()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        newly_applied.append(mig.version)
    return newly_applied


def schema_version(conn: sqlite3.Connection) -> str | None:
    """Return the highest applied migration version, or None if none."""
    row = conn.execute(
        "SELECT MAX(version) FROM schema_migrations"
    ).fetchone()
    return row[0] if row else None


# --- Audit log hash chain (design §5.3 R6) ---

_GENESIS_HASH = "0" * 64


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds")


def _canonical_json(obj: dict) -> str:
    """RFC 8785-leaning canonical JSON: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def audit_append(
    conn: sqlite3.Connection,
    event: str,
    payload: dict,
    *,
    commit: bool = True,
) -> str:
    """Append one hash-linked audit row. Returns the new row's hash.

    Wraps the SELECT-then-INSERT in ``BEGIN IMMEDIATE`` so two concurrent
    callers cannot read the same ``prev_hash`` and fork the chain.

    If a transaction is already active (``conn.in_transaction``), the caller
    owns the lock; we skip BEGIN IMMEDIATE and *do not commit* — the audit
    row participates in the caller's atomic transaction. ``commit=False``
    forces this caller-owned mode regardless of state, used by
    ``distill.ingest_markdown_file`` to keep all per-ingest writes (entity,
    facts, supersede UPDATE, audit row) atomic. Default ``commit=True`` is
    the historical contract: open lock, append, commit.
    """
    in_transaction = bool(getattr(conn, "in_transaction", False))
    if not in_transaction:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            # Another writer holds the immediate lock; sqlite will retry per
            # busy_timeout. Fall through and rely on the engine's ordering.
            pass
    prev = conn.execute(
        "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = prev[0] if prev else _GENESIS_HASH
    ts = _now_iso()
    body = _canonical_json(payload)
    digest = hashlib.sha256(
        f"{prev_hash}|{ts}|{event}|{body}".encode()
    ).hexdigest()
    conn.execute(
        "INSERT INTO audit_log(ts, event, payload, prev_hash, hash) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts, event, body, prev_hash, digest),
    )
    if commit and not in_transaction:
        conn.commit()
    return digest


@dataclass(frozen=True)
class AuditVerifyResult:
    ok: bool
    checked: int
    first_bad_id: int | None
    reason: str | None


def audit_verify(conn: sqlite3.Connection) -> AuditVerifyResult:
    """Replay the chain; return the first break (if any)."""
    prev_hash = _GENESIS_HASH
    count = 0
    cur = conn.execute(
        "SELECT id, ts, event, payload, prev_hash, hash FROM audit_log "
        "ORDER BY id ASC"
    )
    for row_id, ts, event, body, prev_recorded, hash_recorded in cur:
        if prev_recorded != prev_hash:
            return AuditVerifyResult(
                False, count, row_id,
                f"row {row_id}: prev_hash mismatch "
                f"(recorded={prev_recorded[:12]}..., expected={prev_hash[:12]}...)",
            )
        expected = hashlib.sha256(
            f"{prev_hash}|{ts}|{event}|{body}".encode()
        ).hexdigest()
        if hash_recorded != expected:
            return AuditVerifyResult(
                False, count, row_id,
                f"row {row_id}: hash mismatch",
            )
        prev_hash = hash_recorded
        count += 1
    return AuditVerifyResult(True, count, None, None)


def gc_scan(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    """Scan for expired facts and update their status.

    Lifetime rules (design §5.1 + memory_entry.schema.json valid_until field):
    - active + valid_to < TODAY  ->  status = 'expired'
    - dry_run=True               ->  SELECT only, no UPDATE

    Returns counts: {expired, kept_active}.
    Uses parameterised SQL only — no string interpolation of user data.
    """
    today = datetime.now(tz=UTC).date().isoformat()
    expire_rows = conn.execute(
        """
        SELECT id FROM facts
         WHERE status = 'active'
           AND valid_to IS NOT NULL
           AND valid_to < ?
        """,
        (today,),
    ).fetchall()
    expire_ids = [r[0] for r in expire_rows]
    if not dry_run and expire_ids:
        placeholders = ",".join("?" * len(expire_ids))
        conn.execute(
            f"UPDATE facts SET status = 'expired' WHERE id IN ({placeholders})",
            expire_ids,
        )
        conn.commit()
    kept_active = conn.execute(
        "SELECT COUNT(*) FROM facts WHERE status = 'active'",
    ).fetchone()[0]
    return {
        "expired": len(expire_ids),
        "kept_active": kept_active,
    }


# Public API for sliding_window_n consumer (R25-T04)
def recall_recent(
    conn: sqlite3.Connection,
    n: int,
    *,
    include_history: bool = False,
) -> list[dict]:
    """Return the n most-recent facts from the facts table, ordered by id DESC.

    By default only returns facts with status='active'.
    Pass include_history=True to include expired and superseded facts.

    Sliding window consumer for sliding_window_n schema field
    (docs/templates/_schema/task_state.schema.json §sliding_window_n).
    Phase-3 §8-1: sliding_window_n range 5-100 drives context window scoping.

    Args:
        conn: raw sqlite3.Connection (not the Connection dataclass wrapper).
        n: window size. Must be >= 1. Values > 100 are clamped to 100.

    Returns:
        List of dicts (column-name -> value), newest first.

    Raises:
        ValueError: if n < 1.
    """
    if n < 1:
        raise ValueError(f"recall_recent: n must be >= 1, got {n}")
    effective_n = min(n, 100)
    where_clause = "" if include_history else "WHERE status = 'active'"
    cur = conn.execute(
        f"SELECT id, subject_entity_id, predicate, object_entity_id, object_literal, "
        f"polarity, valid_from, valid_to, status, confidence, created_from, scope, "
        f"project_path, vec_indexed_at "
        f"FROM facts {where_clause} ORDER BY id DESC LIMIT ?",
        (effective_n,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def recall_for_task_state(
    conn: sqlite3.Connection,
    task_state: dict,
    *,
    include_history: bool = False,
) -> list[dict]:
    """Wire-up point: read sliding_window_n from a task_state dict and call recall_recent.

    If sliding_window_n is absent or None, defaults to 20.
    If present and invalid (< 1 or non-integer), logs a warning and defaults to 20.
    """
    raw = task_state.get("sliding_window_n")
    if raw is None:
        return recall_recent(conn, 20, include_history=include_history)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        log.warning("recall_for_task_state: invalid sliding_window_n=%r, defaulting to 20", raw)
        return recall_recent(conn, 20, include_history=include_history)
    if n < 1:
        log.warning("recall_for_task_state: sliding_window_n=%d < 1, defaulting to 20", n)
        return recall_recent(conn, 20, include_history=include_history)
    return recall_recent(conn, n, include_history=include_history)
