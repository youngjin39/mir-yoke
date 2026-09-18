"""Bounded, immutable traversal of opt-in relation facts in project memory."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import stat
from collections import Counter
from copy import deepcopy
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
    _FILE_ENDPOINT_RELATIONS,
    _FORWARD,
    _REVERSE,
    DEFAULT_DEPTH,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_EDGES,
    MAX_EDGES,
    Edge,
    RelationError,
    _anchor_spelling_safe,
    _endpoint_path,
    _has_control_characters,
    _normalized_locator,
    _profile_protections,
    _protected,
    _resolve_root,
    _safe_relative_path,
    _validate_endpoint,
    _validate_limits,
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


@dataclass
class _SelectionState:
    """Request-scoped validation and selected-fact accounting."""

    source_cache: dict[tuple[str, str], _SourceValidation]
    fact_cache: dict[int, tuple[Edge | None, str | None]]
    selected_fact_ids: set[int]
    source_bytes: int = 0
    incomplete: bool = False
    proofs_omitted: int = 0


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


_MEMORY_ROW_COLUMNS = """
    f.id, subject.slug, f.predicate, object.slug, ci.id, ci.text_hash, ci.metadata_json
"""


def _relation_rows(
    conn: sqlite3.Connection,
    root: Path,
    frontier: set[str],
    purpose: str,
    *,
    fact_ids: set[int] | None = None,
    excluded_fact_ids: set[int] | None = None,
    limit: int,
) -> list[tuple[Any, ...]]:
    """Read one purpose-compatible SQL frontier in stable fact order."""
    forward = tuple(sorted(_FORWARD[purpose] & RELATION_PREDICATES))
    reverse = tuple(sorted(_REVERSE[purpose] & RELATION_PREDICATES))
    if not frontier or (not forward and not reverse):
        return []
    frontier_values = tuple(sorted(frontier))
    frontier_marks = ", ".join("?" for _ in frontier_values)
    directions: list[str] = []
    parameters: list[Any] = []
    if forward:
        predicate_marks = ", ".join("?" for _ in forward)
        directions.append(
            f"(subject.slug IN ({frontier_marks}) AND f.predicate IN ({predicate_marks}))"
        )
        parameters.extend(frontier_values)
        parameters.extend(forward)
    if reverse:
        predicate_marks = ", ".join("?" for _ in reverse)
        directions.append(
            f"(object.slug IN ({frontier_marks}) AND f.predicate IN ({predicate_marks}))"
        )
        parameters.extend(frontier_values)
        parameters.extend(reverse)
    id_clause = ""
    if fact_ids:
        id_marks = ", ".join("?" for _ in fact_ids)
        id_clause = f" AND f.id IN ({id_marks})"
        parameters.extend(sorted(fact_ids))
    elif excluded_fact_ids:
        id_marks = ", ".join("?" for _ in excluded_fact_ids)
        id_clause = f" AND f.id NOT IN ({id_marks})"
        parameters.extend(sorted(excluded_fact_ids))
    rows = conn.execute(
        f"""
        SELECT {_MEMORY_ROW_COLUMNS}
          FROM facts f
          JOIN entities subject ON subject.id = f.subject_entity_id
          JOIN entities object ON object.id = f.object_entity_id
          JOIN content_items ci ON ci.id = f.created_from
         WHERE f.object_literal IS NULL
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
           AND ({" OR ".join(directions)})
           {id_clause}
           {store.current_fact_filter_sql("f")}
           {_inactive_endpoint_sql("f.subject_entity_id")}
           {_inactive_endpoint_sql("f.object_entity_id")}
         ORDER BY f.id
         LIMIT ?
        """,
        (
            str(root),
            _MAX_METADATA_CHARS,
            _MAX_VALUE_CHARS,
            _MAX_VALUE_CHARS,
            *parameters,
            limit,
        ),
    ).fetchall()
    return [tuple(row) for row in rows]


def _has_relation_row(
    conn: sqlite3.Connection, root: Path, frontier: set[str], purpose: str
) -> bool:
    """A metadata-only depth probe; it never validates or expands an edge."""
    return bool(_relation_rows(conn, root, frontier, purpose, limit=1))


def _eligible_nodes(conn: sqlite3.Connection, root: Path, anchor: str) -> list[str]:
    """Resolve exact logical nodes without reading source documents."""
    predicates = tuple(sorted(RELATION_PREDICATES))
    marks = ", ".join("?" for _ in predicates)
    rows = conn.execute(
        f"""
        SELECT DISTINCT entity.slug
          FROM entities entity
         WHERE entity.slug = ?
           AND length(entity.slug) <= ?
           AND EXISTS (
                SELECT 1
                  FROM facts f
                  JOIN entities subject ON subject.id = f.subject_entity_id
                  JOIN entities object ON object.id = f.object_entity_id
                  JOIN content_items ci ON ci.id = f.created_from
                 WHERE f.predicate IN ({marks})
                   AND f.object_literal IS NULL
                   AND f.polarity = 'asserted'
                   AND f.status = 'active'
                   AND f.valid_to IS NULL
                   AND f.scope = 'project'
                   AND f.project_path = ?
                   AND ci.source = 'self_ingest_md'
                   AND length(ci.metadata_json) <= ?
                   AND length(ci.text_hash) <= 128
                   AND (f.subject_entity_id = entity.id OR f.object_entity_id = entity.id)
                   {store.current_fact_filter_sql("f")}
                   {_inactive_endpoint_sql("f.subject_entity_id")}
                   {_inactive_endpoint_sql("f.object_entity_id")}
           )
         LIMIT 1
        """,
        (anchor, _MAX_VALUE_CHARS, *predicates, str(root), _MAX_METADATA_CHARS),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _locator_path_sql(column: str) -> str:
    return f"mir_locator_path({column})"


def _register_locator_normalizer(conn: sqlite3.Connection) -> None:
    conn.create_function(
        "mir_locator_path",
        1,
        lambda value: _normalized_locator(str(value)).split("::", 1)[0],
        deterministic=True,
    )
    conn.create_function("mir_normalized_locator", 1, lambda value: _normalized_locator(str(value)))


def _locator_nodes(conn: sqlite3.Connection, root: Path, anchor: str) -> list[str]:
    """Resolve normalized path/symbol aliases with case-sensitive literal SQL equality."""
    normalized = _normalized_locator(anchor)
    normalized_path = normalized.split("::", 1)[0]
    _register_locator_normalizer(conn)
    exact = _eligible_nodes(conn, root, normalized)
    predicates = tuple(sorted(RELATION_PREDICATES))
    marks = ", ".join("?" for _ in predicates)
    rows = conn.execute(
        f"""
        SELECT DISTINCT entity.slug
          FROM entities entity
         WHERE {_locator_path_sql("entity.slug")} = ?
           AND instr(entity.slug, '::') > 0
           AND (instr(?, '::') = 0 OR mir_normalized_locator(entity.slug) = ?)
           AND length(entity.slug) <= ?
           AND EXISTS (
                SELECT 1
                  FROM facts f
                  JOIN entities subject ON subject.id = f.subject_entity_id
                  JOIN entities object ON object.id = f.object_entity_id
                  JOIN content_items ci ON ci.id = f.created_from
                 WHERE f.predicate IN ({marks})
                   AND f.object_literal IS NULL
                   AND f.polarity = 'asserted'
                   AND f.status = 'active'
                   AND f.valid_to IS NULL
                   AND f.scope = 'project'
                   AND f.project_path = ?
                   AND ci.source = 'self_ingest_md'
                   AND length(ci.metadata_json) <= ?
                   AND length(ci.text_hash) <= 128
                   AND (f.subject_entity_id = entity.id OR f.object_entity_id = entity.id)
                   {store.current_fact_filter_sql("f")}
                   {_inactive_endpoint_sql("f.subject_entity_id")}
                   {_inactive_endpoint_sql("f.object_entity_id")}
           )
         ORDER BY entity.slug
         LIMIT ?
        """,
        (
            normalized_path,
            normalized,
            normalized,
            _MAX_VALUE_CHARS,
            *predicates,
            str(root),
            _MAX_METADATA_CHARS,
            MAX_EDGES + 1,
        ),
    ).fetchall()
    aliases = [str(row[0]) for row in rows]
    return aliases or exact


def _validate_memory_row(
    conn: sqlite3.Connection,
    root: Path,
    protections: tuple[str, ...],
    row: tuple[Any, ...],
    state: _SelectionState,
) -> tuple[Edge | None, str | None]:
    """Validate selected evidence before it can extend a traversal frontier."""
    fact_id, source, predicate, target, content_id, text_hash, metadata_json = row
    cached = state.fact_cache.get(int(fact_id))
    if cached is not None:
        edge, reason = cached
        return (
            Edge(
                edge.source, edge.relation, edge.target, edge.source_line, deepcopy(edge.provenance)
            )
            if edge is not None
            else None,
            reason,
        )
    source_value, target_value = _entity_value(source), _entity_value(target)
    if source_value is None or target_value is None:
        result = (None, "invalid relation endpoint")
        state.fact_cache[int(fact_id)] = result
        return result
    source_path = source_value.split("::", 1)[0]
    issue = (
        _validate_endpoint(source_value, root, protections=protections)
        if "/" in source_path or source_path.startswith(".")
        else None
    )
    issue = issue or _validate_endpoint(
        target_value,
        root,
        force_file=predicate in _FILE_ENDPOINT_RELATIONS,
        protections=protections,
    )
    if issue:
        result = (None, issue)
        state.fact_cache[int(fact_id)] = result
        return result
    try:
        metadata = json.loads(metadata_json)
    except (TypeError, json.JSONDecodeError):
        result = (None, "invalid relation metadata")
        state.fact_cache[int(fact_id)] = result
        return result
    metadata_issue = _metadata_gate(root, metadata)
    if metadata_issue:
        result = (None, metadata_issue)
        state.fact_cache[int(fact_id)] = result
        return result
    assert isinstance(metadata, dict)
    metadata_path = metadata.get("path")
    cache_key = (
        (metadata_path, text_hash)
        if isinstance(metadata_path, str) and isinstance(text_hash, str)
        else None
    )
    validated = state.source_cache.get(cache_key) if cache_key else None
    from_cache = validated is not None
    if validated is None:
        validated = _source_text(
            root, metadata, text_hash, protections, _MAX_TOTAL_SOURCE_BYTES - state.source_bytes
        )
        if cache_key:
            state.source_cache[cache_key] = validated
    if not from_cache:
        state.source_bytes += validated.bytes_read
    if validated.reason is not None:
        state.incomplete = (
            state.incomplete or validated.budget_exhausted or validated.source_unstable
        )
        result = (None, validated.reason)
        state.fact_cache[int(fact_id)] = result
        return result
    assert (
        validated.source_path is not None
        and validated.source_hash is not None
        and validated.source_text is not None
    )
    try:
        declaration = parse_relation_document(validated.source_text)
    except ValueError:
        result = (None, "invalid relation declaration")
        state.fact_cache[int(fact_id)] = result
        return result
    if declaration.document_status != metadata.get("relation_document_status"):
        result = (None, "relation document status changed")
        state.fact_cache[int(fact_id)] = result
        return result
    declarations = [
        item
        for item in declaration.declarations
        if item.subject == source_value
        and item.predicate == predicate
        and item.object == target_value
    ]
    declared = next(
        (
            item
            for item in declarations
            if _provenance_is_current(conn, int(fact_id), int(content_id), item.quote)
        ),
        None,
    )
    if declared is None:
        result = (
            None,
            "missing relation provenance" if declarations else "undeclared relation fact",
        )
        state.fact_cache[int(fact_id)] = result
        return result
    authored_summary = getattr(declared, "summary", None)
    authored_reason = getattr(declared, "reason", None)
    proof = {
        "database": _MEMORY_RELATIONS_DB,
        "fact_id": int(fact_id),
        "content_item_id": int(content_id),
        "source_path": validated.source_path,
        "source_hash": validated.source_hash,
        "source_line": getattr(declared, "source_line", None),
        "summary": authored_summary or f"Declared {predicate.replace('_', ' ')} relationship.",
        "summary_basis": "authored" if authored_summary else "deterministic predicate description",
        "reason": authored_reason or "No authored rationale was supplied.",
        "reason_basis": "authored" if authored_reason else "no authored rationale",
    }
    provenance = {
        key: proof[key]
        for key in ("database", "fact_id", "content_item_id", "source_path", "source_hash")
    }
    provenance["sources"] = [proof]
    edge = Edge(source_value, predicate, target_value, None, provenance)
    state.fact_cache[int(fact_id)] = (
        Edge(edge.source, edge.relation, edge.target, edge.source_line, deepcopy(edge.provenance)),
        None,
    )
    return edge, None


def _append_edge(
    emitted: dict[tuple[str, str, str], Edge], edge: Edge, state: _SelectionState
) -> bool:
    """Coalesce source proofs exactly as the former full-memory loader did."""
    key = (edge.source, edge.relation, edge.target)
    if key not in emitted:
        emitted[key] = edge
        return True
    existing = emitted[key]
    sources = existing.provenance.setdefault("sources", []) if existing.provenance else []
    proof = edge.provenance["sources"][0] if edge.provenance else None
    if isinstance(proof, dict):
        if len(sources) < _MAX_PROVENANCE_PER_EDGE:
            sources.append(proof)
        else:
            existing.provenance["sources_omitted"] = (
                int(existing.provenance.get("sources_omitted", 0)) + 1
            )
            state.proofs_omitted += 1
    return False


def _traverse_memory_rows(
    conn: sqlite3.Connection,
    root: Path,
    protections: tuple[str, ...],
    resolved: list[str],
    purpose: str,
    *,
    depth: int,
    max_edges: int,
    state: _SelectionState,
) -> tuple[list[Edge], list[str]]:
    """Select and validate a single purpose's SQL BFS without mixing frontiers."""
    emitted: dict[tuple[str, str, str], Edge] = {}
    notices: list[str] = []
    skipped: Counter[str] = Counter()
    frontier, seen_nodes, seen_fact_ids = set(resolved), set(resolved), set()
    for level in range(depth):
        remaining = _MAX_DB_ROWS - len(state.selected_fact_ids)
        cached_rows = (
            _relation_rows(
                conn, root, frontier, purpose, fact_ids=state.selected_fact_ids, limit=_MAX_DB_ROWS
            )
            if state.selected_fact_ids
            else []
        )
        fresh_rows = _relation_rows(
            conn,
            root,
            frontier,
            purpose,
            excluded_fact_ids=state.selected_fact_ids or None,
            limit=max(1, remaining + 1),
        )
        overflow = len(fresh_rows) > remaining
        state.incomplete = state.incomplete or overflow
        fresh_rows = fresh_rows[:remaining]
        state.selected_fact_ids.update(int(row[0]) for row in fresh_rows)
        next_frontier: set[str] = set()
        for row in sorted([*cached_rows, *fresh_rows], key=lambda value: int(value[0])):
            fact_id, source, predicate, target, *_ = row
            if int(fact_id) in seen_fact_ids:
                continue
            seen_fact_ids.add(int(fact_id))
            if int(fact_id) not in state.selected_fact_ids:
                state.selected_fact_ids.add(int(fact_id))
            source_value, target_value = _entity_value(source), _entity_value(target)
            if source_value is None or target_value is None:
                skipped["invalid relation endpoint"] += 1
                continue
            key = (source_value, str(predicate), target_value)
            if key not in emitted and len(emitted) >= max_edges:
                notices.append("truncated: max-edges reached; frontier remains unexplored")
                return list(emitted.values()), [
                    *(
                        f"skipped {reason}: {count} edge(s)"
                        for reason, count in sorted(skipped.items())
                    ),
                    *notices,
                ]
            edge, reason = _validate_memory_row(conn, root, protections, row, state)
            if reason:
                skipped[reason] += 1
                continue
            assert edge is not None
            added = _append_edge(emitted, edge, state)
            forward = edge.source in frontier and edge.relation in _FORWARD[purpose]
            neighbour = edge.target if forward else edge.source
            if added and neighbour not in seen_nodes:
                seen_nodes.add(neighbour)
                next_frontier.add(neighbour)
        if overflow:
            state.incomplete = True
            notices.append("truncated: memory fact row limit reached; frontier remains unexplored")
            break
        frontier = next_frontier
        if not frontier:
            break
        if level + 1 == depth and _has_relation_row(conn, root, frontier, purpose):
            notices.append("truncated: depth reached; frontier remains unexplored")
            break
    return list(emitted.values()), [
        *(f"skipped {reason}: {count} edge(s)" for reason, count in sorted(skipped.items())),
        *notices,
    ]


def _resolve_query_anchor(
    conn: sqlite3.Connection, root: Path, protections: tuple[str, ...], anchor: str
) -> list[str]:
    exact = _eligible_nodes(conn, root, anchor)
    if _endpoint_path(anchor) is None:
        if not exact:
            raise RelationError("unknown anchor")
        return exact
    issue = _validate_endpoint(anchor, root, force_file=True, protections=protections)
    if issue:
        raise RelationError(f"anchor {issue}")
    resolved = _locator_nodes(conn, root, anchor)
    if not resolved:
        raise RelationError("unknown anchor")
    return resolved


def _implemented_in_rows(
    conn: sqlite3.Connection, root: Path, anchor: str
) -> list[tuple[Any, ...]]:
    normalized = _normalized_locator(anchor).split("::", 1)[0]
    _register_locator_normalizer(conn)
    rows = conn.execute(
        f"""
        SELECT {_MEMORY_ROW_COLUMNS}
          FROM facts f
          JOIN entities subject ON subject.id = f.subject_entity_id
          JOIN entities object ON object.id = f.object_entity_id
          JOIN content_items ci ON ci.id = f.created_from
         WHERE f.predicate = 'implemented_in'
           AND {_locator_path_sql("object.slug")} = ?
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
            normalized,
            str(root),
            _MAX_METADATA_CHARS,
            _MAX_VALUE_CHARS,
            _MAX_VALUE_CHARS,
            _MAX_DB_ROWS + 1,
        ),
    ).fetchall()
    return [tuple(row) for row in rows]


def _proof_notices(state: _SelectionState) -> list[str]:
    if not state.proofs_omitted:
        return []
    return [
        f"truncated: per-edge source proof limit reached; {state.proofs_omitted} proof(s) omitted"
    ]


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
    db_path = _memory_db_path(base)
    state = _SelectionState({}, {}, set())
    try:
        with store.immutable_snapshot_guard(db_path):
            connection = store.connect_read_only(db_path, load_vec=False)
            try:
                resolved = _resolve_query_anchor(connection.conn, base, protections, anchor)
                if len(resolved) > max_edges:
                    notices = [
                        "truncated: anchor expansion limit reached; "
                        "additional locators remain unexamined"
                    ]
                    resolved = resolved[:max_edges]
                else:
                    notices = []
                edges, traversal_notices = _traverse_memory_rows(
                    connection.conn,
                    base,
                    protections,
                    resolved,
                    purpose,
                    depth=depth,
                    max_edges=max_edges,
                    state=state,
                )
                notices.extend(traversal_notices)
            finally:
                connection.conn.close()
    except RelationError:
        raise
    except (OSError, sqlite3.Error, RuntimeError, store.ReadOnlySnapshotUnavailable) as exc:
        raise RelationError("memory database cannot be read safely") from exc
    if state.incomplete:
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
        _nodes=set(resolved),
    )
    result["notices"] = [*notices, *_proof_notices(state), *result["notices"]]
    result["truncated"] = result["truncated"] or any(
        notice.startswith("truncated:") for notice in result["notices"]
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
    state = _SelectionState({}, {}, set())
    try:
        db_path = _memory_db_path(base)
        with store.immutable_snapshot_guard(db_path):
            connection = store.connect_read_only(db_path, load_vec=False)
            try:
                anchor = unique_anchors[0]
                owner_edges: dict[tuple[str, str, str], Edge] = {}
                owner_notices: Counter[str] = Counter()
                resolution: dict[str, Any] | None = None
                if _endpoint_path(anchor) is not None:
                    issue = _validate_endpoint(
                        anchor, base, force_file=True, protections=protections
                    )
                    if issue:
                        if issue == "unavailable endpoint":
                            return _search_hint(unique_anchors, unique_purposes, "unknown anchor")
                        raise RelationError(f"anchor {issue}")
                    rows = _implemented_in_rows(connection.conn, base, anchor)
                    if len(rows) > _MAX_DB_ROWS:
                        result = _search_hint(
                            unique_anchors,
                            unique_purposes,
                            "memory relation view is incomplete",
                        )
                        result["notices"] = [
                            "truncated: memory fact row limit reached; "
                            "implementation owner frontier remains unexplored"
                        ]
                        result["truncated"] = True
                        return result
                    for row in rows:
                        fact_id = int(row[0])
                        state.selected_fact_ids.add(fact_id)
                        edge, reason = _validate_memory_row(
                            connection.conn, base, protections, row, state
                        )
                        if reason:
                            owner_notices[reason] += 1
                        if edge is not None:
                            _append_edge(owner_edges, edge, state)
                    if state.incomplete:
                        result = _search_hint(
                            unique_anchors, unique_purposes, "memory relation view is incomplete"
                        )
                        result["notices"] = [
                            *(
                                f"skipped {reason}: {count} edge(s)"
                                for reason, count in owner_notices.items()
                            )
                        ]
                        result["truncated"] = True
                        return result
                    owner_ids = list(dict.fromkeys(edge.source for edge in owner_edges.values()))
                    if len(owner_ids) != 1:
                        result = _search_hint(
                            unique_anchors,
                            unique_purposes,
                            "ambiguous implementation owner" if owner_edges else "unknown anchor",
                        )
                        result["notices"] = [
                            *(
                                f"skipped {reason}: {count} edge(s)"
                                for reason, count in owner_notices.items()
                            )
                        ]
                        return result
                    resolved_anchor = owner_ids[0]
                    resolution = next(iter(owner_edges.values())).as_dict()
                else:
                    exact = _eligible_nodes(connection.conn, base, anchor)
                    if not exact:
                        return _search_hint(unique_anchors, unique_purposes, "unknown anchor")
                    resolved_anchor = exact[0]
                facet_edges: dict[str, list[Edge]] = {}
                facet_notices: dict[str, list[str]] = {}
                for purpose in unique_purposes:
                    edges, notices = _traverse_memory_rows(
                        connection.conn,
                        base,
                        protections,
                        [resolved_anchor],
                        purpose,
                        depth=depth,
                        max_edges=max_edges,
                        state=state,
                    )
                    facet_edges[purpose] = edges
                    facet_notices[purpose] = notices
            finally:
                connection.conn.close()
    except RelationError as exc:
        if "unavailable" in str(exc) or "cannot be read" in str(exc):
            result = _search_hint(unique_anchors, unique_purposes, "memory unavailable")
            result["notices"] = [str(exc)]
            return result
        raise
    except (OSError, sqlite3.Error, RuntimeError, store.ReadOnlySnapshotUnavailable):
        result = _search_hint(unique_anchors, unique_purposes, "memory unavailable")
        result["notices"] = ["memory database cannot be read safely"]
        return result
    if state.incomplete:
        result = _search_hint(unique_anchors, unique_purposes, "memory relation view is incomplete")
        result["notices"] = [
            *(f"skipped {reason}: {count} edge(s)" for reason, count in owner_notices.items()),
            *(notice for values in facet_notices.values() for notice in values),
            *_proof_notices(state),
        ]
        result["truncated"] = True
        return result
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    facets: list[dict[str, Any]] = []
    notices = [f"skipped {reason}: {count} edge(s)" for reason, count in owner_notices.items()]
    omitted = False
    for purpose in unique_purposes:
        item = query_relations(
            resolved_anchor,
            purpose,
            root=base,
            depth=depth,
            max_edges=max_edges,
            max_bytes=max_bytes,
            _graph=facet_edges[purpose],
            _digest="memory",
            _source=_MEMORY_RELATIONS_DB,
            _protections=protections,
            _scope="declared_memory_relations_only",
            _source_metadata=_memory_source(),
            _nodes={resolved_anchor},
        )
        item_notices = [*facet_notices[purpose], *item["notices"]]
        available, contributed = len(item["edges"]), 0
        for edge in item["edges"]:
            key = (edge["source"], edge["relation"], edge["target"])
            if key in seen:
                next(
                    candidate
                    for candidate in merged
                    if (candidate["source"], candidate["relation"], candidate["target"]) == key
                )["purposes"].append(purpose)
            elif len(merged) < max_edges:
                merged.append({**edge, "purposes": [purpose]})
                seen.add(key)
                contributed += 1
            else:
                omitted = True
        facets.append(
            {
                "purpose": purpose,
                "available_count": available,
                "edge_count": contributed,
                "coverage": "truncated"
                if any(notice.startswith("truncated:") for notice in item_notices) or omitted
                else "empty"
                if not available
                else "bounded",
                "notices": item_notices,
            }
        )
        notices.extend(item_notices)
    if any(facet["available_count"] == 0 for facet in facets):
        result = _search_hint(
            unique_anchors,
            unique_purposes,
            "one or more requested facets have no declared evidence",
        )
        result["notices"] = list(dict.fromkeys([*notices, *_proof_notices(state)]))
        result["truncated"] = any(notice.startswith("truncated:") for notice in result["notices"])
        return result
    if omitted:
        notices.append("truncated: global max-edges reached; facet coverage incomplete")
    result = {
        "route": "memory",
        "anchor": unique_anchors[0],
        "resolved_anchor": resolved_anchor,
        "resolution": resolution,
        "requested_purposes": unique_purposes,
        "facets": facets,
        "scope": "declared_memory_relations_only",
        "source": _memory_source(),
        "edges": merged,
        "notices": list(dict.fromkeys([*notices, *_proof_notices(state)])),
        "truncated": False,
    }
    emitted = {facet["purpose"]: 0 for facet in facets}
    for edge in merged:
        for purpose in edge["purposes"]:
            emitted[purpose] += 1
    for facet in facets:
        facet["edge_count"] = emitted[facet["purpose"]]
        if facet["edge_count"] < facet["available_count"]:
            facet["coverage"] = "truncated"
    result["truncated"] = any(notice.startswith("truncated:") for notice in result["notices"])
    return result
