"""Bounded, immutable traversal of opt-in relation facts in project memory."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mir.core.engine.memory import store
from mir.core.engine.memory.relation_facts import (
    RELATION_PREDICATES,
    RELATION_SCHEMA,
    parse_relation_document,
)
from mir.core.relations import (
    DEFAULT_DEPTH,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_EDGES,
    Edge,
    RelationError,
    _anchor_spelling_safe,
    _has_control_characters,
    _profile_protections,
    _protected,
    _resolve_root,
    _safe_relative_path,
    _validate_limits,
    bundle_relations,
    query_relations,
)

_MEMORY_RELATIONS_DB = ".mir/memory.db"
_MAX_DB_ROWS = 2048
_MAX_SOURCE_BYTES = 1024 * 1024
_MAX_TOTAL_SOURCE_BYTES = 4 * 1024 * 1024
_MAX_VALUE_CHARS = 4096
_MAX_METADATA_CHARS = 64 * 1024
_MAX_PROVENANCE_PER_EDGE = 8
_INACTIVE_DOCUMENT_STATUSES = frozenset(
    {
        "inactive",
        "archived",
        "rejected",
        "superseded",
        "superseded-design",
        "historical",
        "historical-snapshot",
        "historical-manual-snapshot",
        "historical-ledger",
        "applied-ledger-v1",
        "done",
        "candidate",
        "draft",
        "proposed",
    }
)
_PURPOSES = frozenset({"implementation", "impact", "verification", "dependencies"})


@dataclass(frozen=True)
class _SourceValidation:
    reason: str | None = None
    source_path: str | None = None
    source_hash: str | None = None
    source_text: str | None = None
    bytes_read: int = 0
    budget_exhausted: bool = False
    source_unstable: bool = False


def _source_stamp(entry: os.stat_result) -> tuple[int, int, int, int, int]:
    return (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns)


def _metadata_gate(root: Path, metadata: object) -> str | None:
    """Validate row-owned metadata before a shared source cache is consulted."""
    if not isinstance(metadata, dict):
        return "invalid relation metadata"
    if metadata.get("relation_schema") != RELATION_SCHEMA:
        return "unsupported relation schema"
    if metadata.get("relation_project_path") != str(root):
        return "relation source belongs to another root"
    status = metadata.get("relation_document_status")
    if not isinstance(status, str) or _has_control_characters(status):
        return "invalid relation document status"
    if status.strip().lower() in _INACTIVE_DOCUMENT_STATUSES:
        return "inactive relation document"
    return None


def _memory_db_path(root: Path) -> Path:
    """Return only the canonical project memory file.

    ``.mir/memory.db`` is normally protected. This narrowly-scoped immutable
    reader is its explicit gateway; it does not relax protection checks for any
    other path.
    """
    candidate = root / ".mir" / "memory.db"
    try:
        mode = candidate.lstat().st_mode
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise RelationError("memory database is unavailable") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise RelationError("memory database must be a regular canonical file")
    if relative.as_posix() != _MEMORY_RELATIONS_DB:
        raise RelationError("memory database escapes its canonical project path")
    return resolved


def _entity_value(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_VALUE_CHARS
        or _has_control_characters(value)
    ):
        return None
    return value


def _source_text(
    root: Path,
    metadata: object,
    expected_hash: object,
    protections: tuple[str, ...],
    remaining_bytes: int,
) -> _SourceValidation:
    """Return source path and ingester-compatible hash, or a safe skip reason."""
    metadata_issue = _metadata_gate(root, metadata)
    if metadata_issue:
        return _SourceValidation(reason=metadata_issue)
    assert isinstance(metadata, dict)
    source_path = metadata.get("path")
    try:
        relative = _safe_relative_path(source_path, label="relation source")
    except RelationError:
        return _SourceValidation(reason="unsafe relation source")
    if _protected(relative.parts, protections):
        return _SourceValidation(reason="protected relation source")
    candidate = root.joinpath(*relative.parts)
    try:
        parent = candidate.parent.resolve(strict=True)
        parent.relative_to(root)
        mode = candidate.lstat().st_mode
        resolved = candidate.resolve(strict=True)
        resolved_relative = resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        return _SourceValidation(reason="unavailable relation source")
    if not stat.S_ISREG(mode) or _protected(resolved_relative.parts, protections):
        return _SourceValidation(
            reason=(
                "protected relation source"
                if _protected(resolved_relative.parts, protections)
                else "unavailable relation source"
            )
        )
    try:
        expected_stamp = _source_stamp(resolved.stat())
    except OSError:
        return _SourceValidation(reason="unavailable relation source")
    source_size = expected_stamp[2]
    if source_size > _MAX_SOURCE_BYTES:
        return _SourceValidation(reason="relation source exceeds 1 MiB limit")
    if source_size > remaining_bytes:
        return _SourceValidation(
            reason="relation source validation byte limit", budget_exhausted=True
        )
    handle: Any | None = None
    try:
        handle = resolved.open("rb")
        try:
            opened_stamp = _source_stamp(os.fstat(handle.fileno()))
        except (AttributeError, OSError):
            opened_stamp = None
        if opened_stamp is not None and opened_stamp != expected_stamp:
            return _SourceValidation(
                reason="relation source changed while reading", source_unstable=True
            )
        try:
            raw = handle.read(source_size)
        finally:
            descriptor_after = (
                _source_stamp(os.fstat(handle.fileno())) if opened_stamp is not None else None
            )
    except OSError:
        bytes_read = 0
        if handle is not None:
            try:
                bytes_read = max(0, int(handle.tell()))
            except (AttributeError, OSError, ValueError):
                pass
        return _SourceValidation(reason="unavailable relation source", bytes_read=bytes_read)
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
    try:
        path_after = _source_stamp(resolved.stat())
    except OSError:
        return _SourceValidation(
            reason="relation source changed while reading",
            bytes_read=len(raw),
            source_unstable=True,
        )
    if (
        len(raw) != source_size
        or path_after != expected_stamp
        or (descriptor_after is not None and descriptor_after != expected_stamp)
    ):
        return _SourceValidation(
            reason="relation source changed while reading",
            bytes_read=len(raw),
            source_unstable=True,
        )
    try:
        text = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline=None).read()
    except UnicodeDecodeError:
        return _SourceValidation(reason="relation source is not UTF-8", bytes_read=len(raw))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not isinstance(expected_hash, str) or expected_hash != digest:
        return _SourceValidation(reason="stale relation source", bytes_read=len(raw))
    return _SourceValidation(
        source_path=relative.as_posix(),
        source_hash=digest,
        source_text=text,
        bytes_read=len(raw),
    )


def _provenance_is_current(
    conn: sqlite3.Connection, fact_id: int, content_id: int, declaration_quote: str
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM provenance
         WHERE fact_id = ? AND content_item_id = ? AND strength = 'stated'
           AND quote = ?
         LIMIT 1
        """,
        (fact_id, content_id, declaration_quote),
    ).fetchone()
    return row is not None


def _inactive_endpoint_sql(entity_id: str) -> str:
    return f"""
       AND NOT EXISTS (
            SELECT 1 FROM facts terminal
             WHERE terminal.subject_entity_id = {entity_id}
               AND terminal.predicate = 'status'
               AND terminal.status = 'active'
               AND terminal.polarity = 'asserted'
               AND (
                    lower(trim(terminal.object_literal)) IN
                        ('archived', 'rejected', 'superseded', 'superseded-design',
                         'historical', 'historical-snapshot',
                         'historical-manual-snapshot', 'historical-ledger',
                         'applied-ledger-v1', 'done', 'inactive', 'candidate', 'draft',
                         'proposed')
                    OR lower(trim(terminal.object_literal)) LIKE 'historical%'
                    OR lower(trim(terminal.object_literal)) LIKE 'superseded%'
               )
       )
    """


def _load_memory_edges(
    root: Path, protections: tuple[str, ...]
) -> tuple[list[Edge], list[str], set[str], bool]:
    db_path = _memory_db_path(root)
    try:
        with store.immutable_snapshot_guard(db_path):
            return _load_memory_edges_from_snapshot(db_path, root, protections)
    except (OSError, sqlite3.Error, RuntimeError, store.ReadOnlySnapshotUnavailable) as exc:
        raise RelationError("memory database cannot be read safely") from exc


def _load_memory_edges_from_snapshot(
    db_path: Path, root: Path, protections: tuple[str, ...]
) -> tuple[list[Edge], list[str], set[str], bool]:
    try:
        connection = store.connect_read_only(db_path, load_vec=False)
    except (OSError, sqlite3.Error, RuntimeError, store.ReadOnlySnapshotUnavailable) as exc:
        raise RelationError("memory database cannot be read safely") from exc
    try:
        predicates = tuple(sorted(RELATION_PREDICATES))
        predicate_marks = ", ".join("?" for _ in predicates)
        rows = connection.conn.execute(
            f"""
            SELECT f.id, subject.slug, f.predicate, object.slug, ci.id, ci.text_hash,
                   ci.metadata_json
              FROM facts f
              JOIN entities subject ON subject.id = f.subject_entity_id
              JOIN entities object ON object.id = f.object_entity_id
              JOIN content_items ci ON ci.id = f.created_from
             WHERE f.predicate IN ({predicate_marks})
               AND f.object_literal IS NULL
               AND f.polarity = 'asserted'
               AND f.status = 'active'
               AND f.valid_to IS NULL
               AND f.scope = 'project'
               AND f.project_path = ?
               AND ci.source = 'self_ingest_md'
               AND length(ci.metadata_json) <= ?
               AND length(ci.text_hash) <= 128
               AND length(subject.slug) <= ?
               AND length(object.slug) <= ?
               {store.current_fact_filter_sql("f")}
               {_inactive_endpoint_sql("f.subject_entity_id")}
               {_inactive_endpoint_sql("f.object_entity_id")}
             ORDER BY f.id
             LIMIT ?
            """,
            (
                *predicates,
                str(root),
                _MAX_METADATA_CHARS,
                _MAX_VALUE_CHARS,
                _MAX_VALUE_CHARS,
                _MAX_DB_ROWS + 1,
            ),
        ).fetchall()
        exceeded = len(rows) > _MAX_DB_ROWS
        rows = rows[:_MAX_DB_ROWS]
        skipped: Counter[str] = Counter()
        emitted: dict[tuple[str, str, str], Edge] = {}
        known_nodes: set[str] = set()
        source_cache: dict[tuple[str, str], _SourceValidation] = {}
        source_bytes = 0
        incomplete = exceeded
        proofs_omitted = 0
        for (
            fact_id,
            source,
            predicate,
            target,
            content_id,
            text_hash,
            metadata_json,
        ) in rows:
            source_value, target_value = _entity_value(source), _entity_value(target)
            if source_value is None or target_value is None:
                skipped["invalid relation endpoint"] += 1
                continue
            known_nodes.update((source_value, target_value))
            try:
                metadata = json.loads(metadata_json)
            except (TypeError, json.JSONDecodeError):
                skipped["invalid relation metadata"] += 1
                continue
            metadata_issue = _metadata_gate(root, metadata)
            if metadata_issue:
                skipped[metadata_issue] += 1
                continue
            metadata_path = metadata.get("path") if isinstance(metadata, dict) else None
            cache_key = (
                (metadata_path, text_hash)
                if isinstance(metadata_path, str) and isinstance(text_hash, str)
                else None
            )
            validated = source_cache.get(cache_key) if cache_key else None
            from_cache = validated is not None
            if validated is None:
                validated = _source_text(
                    root, metadata, text_hash, protections, _MAX_TOTAL_SOURCE_BYTES - source_bytes
                )
                if cache_key:
                    source_cache[cache_key] = validated
            if not from_cache:
                source_bytes += validated.bytes_read
            if validated.reason is not None:
                skipped[validated.reason] += 1
                incomplete = incomplete or validated.budget_exhausted or validated.source_unstable
                continue
            assert (
                validated.source_path is not None
                and validated.source_hash is not None
                and validated.source_text is not None
            )
            try:
                declaration = parse_relation_document(validated.source_text)
            except ValueError:
                skipped["invalid relation declaration"] += 1
                continue
            if declaration.document_status != metadata.get("relation_document_status"):
                skipped["relation document status changed"] += 1
                continue
            declarations = [
                item
                for item in declaration.declarations
                if item.subject == source_value
                and item.predicate == predicate
                and item.object == target_value
            ]
            if not declarations:
                skipped["undeclared relation fact"] += 1
                continue
            declared = next(
                (
                    item
                    for item in declarations
                    if _provenance_is_current(connection.conn, fact_id, content_id, item.quote)
                ),
                None,
            )
            if declared is None:
                skipped["missing relation provenance"] += 1
                continue
            authored_summary = getattr(declared, "summary", None)
            authored_reason = getattr(declared, "reason", None)
            summary = authored_summary or f"Declared {predicate.replace('_', ' ')} relationship."
            reason = authored_reason or "No authored rationale was supplied."
            key = (source_value, predicate, target_value)
            proof = {
                "database": _MEMORY_RELATIONS_DB,
                "fact_id": int(fact_id),
                "content_item_id": int(content_id),
                "source_path": validated.source_path,
                "source_hash": validated.source_hash,
                "source_line": getattr(declared, "source_line", None),
                "summary": summary,
                "summary_basis": (
                    "authored" if authored_summary else "deterministic predicate description"
                ),
                "reason": reason,
                "reason_basis": "authored" if authored_reason else "no authored rationale",
            }
            if key in emitted:
                existing = emitted[key]
                sources = (
                    existing.provenance.setdefault("sources", []) if existing.provenance else []
                )
                if len(sources) < _MAX_PROVENANCE_PER_EDGE:
                    sources.append(proof)
                else:
                    existing.provenance["sources_omitted"] = (
                        int(existing.provenance.get("sources_omitted", 0)) + 1
                    )
                    proofs_omitted += 1
            else:
                provenance = {
                    key: proof[key]
                    for key in (
                        "database",
                        "fact_id",
                        "content_item_id",
                        "source_path",
                        "source_hash",
                    )
                }
                provenance["sources"] = [proof]
                emitted[key] = Edge(
                    source_value,
                    predicate,
                    target_value,
                    None,
                    provenance,
                )
        notices = [
            *(f"skipped {reason}: {count} edge(s)" for reason, count in sorted(skipped.items()))
        ]
        if exceeded:
            notices.append("truncated: memory fact row limit reached; additional facts omitted")
        if proofs_omitted:
            notices.append(
                "truncated: per-edge source proof limit reached; "
                f"{proofs_omitted} proof(s) omitted"
            )
        return list(emitted.values()), notices, known_nodes, incomplete
    except sqlite3.Error as exc:
        raise RelationError("memory database schema is unavailable") from exc
    finally:
        connection.conn.close()


def _memory_source() -> dict[str, str]:
    return {"memory_db": _MEMORY_RELATIONS_DB, "mode": "immutable_read_only"}


def _search_hint(anchors: list[str], purposes: list[str], reason: str) -> dict[str, Any]:
    return {
        "route": "search",
        "anchors": anchors,
        "requested_purposes": purposes,
        "reason": reason,
        "scope": "declared_memory_relations_only",
        "edges": [],
        "notices": [],
        "truncated": False,
    }


def query_memory_relations(
    anchor: str,
    purpose: str,
    *,
    root: str | Path = ".",
    depth: int = DEFAULT_DEPTH,
    max_edges: int = DEFAULT_MAX_EDGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Return current, source-verified opt-in relation facts from project memory."""
    if not isinstance(purpose, str) or purpose not in _PURPOSES:
        raise RelationError("purpose must be implementation, impact, verification, or dependencies")
    _anchor_spelling_safe(anchor)
    _validate_limits(depth, max_edges, max_bytes)
    base = _resolve_root(root)
    protections = _profile_protections(base)
    edges, notices, nodes, incomplete = _load_memory_edges(base, protections)
    if incomplete:
        raise RelationError("memory relation view is incomplete; use ordinary search")
    result = query_relations(
        anchor,
        purpose,
        root=base,
        depth=depth,
        max_edges=max_edges,
        max_bytes=max_bytes,
        _graph=edges,
        _digest="memory",
        _source=_MEMORY_RELATIONS_DB,
        _protections=protections,
        _scope="declared_memory_relations_only",
        _source_metadata=_memory_source(),
        _nodes=nodes,
    )
    result["notices"] = [*notices, *result["notices"]]
    result["truncated"] = result["truncated"] or any(
        notice.startswith("truncated:") for notice in notices
    )
    return result


def bundle_memory_relations(
    anchors: list[str],
    purposes: list[str],
    *,
    root: str | Path = ".",
    depth: int = DEFAULT_DEPTH,
    max_edges: int = DEFAULT_MAX_EDGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Bundle compatible memory facets, or return an honest ordinary-search hint."""
    if (
        not isinstance(anchors, list)
        or not isinstance(purposes, list)
        or any(not isinstance(value, str) for value in [*anchors, *purposes])
    ):
        raise RelationError("anchors and purposes must be lists")
    _validate_limits(depth, max_edges, max_bytes)
    for anchor in anchors:
        _anchor_spelling_safe(anchor)
    unique_anchors, unique_purposes = list(dict.fromkeys(anchors)), list(dict.fromkeys(purposes))
    if len(unique_anchors) != 1:
        return _search_hint(unique_anchors, unique_purposes, "requires exactly one distinct anchor")
    if len(unique_purposes) < 2:
        return _search_hint(
            unique_anchors, unique_purposes, "requires at least two distinct purposes"
        )
    if any(
        purpose not in {"implementation", "impact", "verification", "dependencies"}
        for purpose in unique_purposes
    ):
        return _search_hint(unique_anchors, unique_purposes, "unknown purpose")
    base = _resolve_root(root)
    protections = _profile_protections(base)
    try:
        edges, notices, _, incomplete = _load_memory_edges(base, protections)
    except RelationError as exc:
        if "unavailable" in str(exc) or "cannot be read" in str(exc):
            result = _search_hint(unique_anchors, unique_purposes, "memory unavailable")
            result["notices"] = [str(exc)]
            return result
        raise
    if incomplete:
        result = _search_hint(unique_anchors, unique_purposes, "memory relation view is incomplete")
        result["notices"] = notices
        result["truncated"] = True
        return result
    result = bundle_relations(
        anchors,
        purposes,
        root=base,
        depth=depth,
        max_edges=max_edges,
        max_bytes=max_bytes,
        _graph=edges,
        _digest="memory",
        _source=_MEMORY_RELATIONS_DB,
        _protections=protections,
        _scope="declared_memory_relations_only",
        _source_metadata=_memory_source(),
        _route="memory",
    )
    result["scope"] = "declared_memory_relations_only"
    result["notices"] = list(dict.fromkeys([*notices, *result["notices"]]))
    result["truncated"] = result["truncated"] or any(
        notice.startswith("truncated:") for notice in notices
    )
    return result
