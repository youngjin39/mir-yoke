"""Distill — turn raw text into sanitized facts.

BORROWED-FROM: codenamev/claude_memory@d0e523cd06d6adeae4744d89736f79564d9db41d
  lib/claude_memory/distill/json_schema.md#schema
License: MIT
Changes:
  - claude-memory entities/facts schema adapted to Mir facts.predicate.
  - deterministic ADR frontmatter ingest replaces Ruby knowledge rows.
  - FTS5 user query sanitization is shared by fact and external search.

Phase 1 scope is intentionally minimal: we take an entity-predicate-object
triple + source content_item, run it through sanitize + predicate
canonicalization, and insert. Real LLM-driven fact extraction is Phase 2.

ADR-05 S1 (2026-05-10) extends distill with deterministic frontmatter
ingest for ``docs/decisions/adr-*.md`` — no LLM call, frontmatter
key/value pairs become triples. R1 (valid_from) + R2 (confidence) supersede
rules close older facts when newer ones arrive on the same (subject,
predicate). audit_log carries every state transition.

design §9.19 (canonicalize) · §7.7 (sanitize) · §5.1 (facts schema).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .predicates import canonicalize
from .sanitize import sanitize


@dataclass(frozen=True)
class Triple:
    subject_slug: str
    predicate: str
    object_literal: str
    source_content_id: int | None = None
    scope: str = "global"
    project_path: str | None = None
    polarity: str = "asserted"
    confidence: float = 1.0
    is_list_member: bool = False


@dataclass(frozen=True)
class IngestResult:
    """Outcome of ``ingest_markdown_file()``. All counts are non-negative.

    ``no_op_reason`` distinguishes the three skip paths so operators can
    tell *why* a call returned without writing:

    * ``""`` — not a no-op (real ingest, ``no_op=False``)
    * ``"whitelist"`` — path did not match the whitelist
    * ``"unchanged"`` — file_hash already in ``content_items``
    * ``"empty_frontmatter"`` — frontmatter block missing or unparseable
    """

    facts_inserted: int
    facts_superseded: int
    fact_links_added: int
    file_hash: str
    no_op: bool
    no_op_reason: str = ""


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds")


def _upsert_entity(conn, slug: str, *, entity_type: str | None = None) -> int:
    cur = conn.execute("SELECT id FROM entities WHERE slug = ?", (slug,))
    row = cur.fetchone()
    if row:
        if entity_type is not None:
            conn.execute(
                "UPDATE entities SET type = ? WHERE slug = ? AND type IS NULL", (entity_type, slug)
            )
        return row[0]
    conn.execute(
        "INSERT INTO entities(type, canonical_name, slug) VALUES (?, ?, ?)",
        (entity_type, slug, slug),
    )
    return conn.execute(
        "SELECT id FROM entities WHERE slug = ?", (slug,)
    ).fetchone()[0]


def insert_triple(conn, triple: Triple, *, consent_scope: str = "ephemeral") -> int:
    """Insert a sanitized + canonicalized fact. Returns the new ``facts.id``."""
    subject_id = _upsert_entity(conn, triple.subject_slug)
    predicate = canonicalize(triple.predicate)
    body = sanitize(triple.object_literal, consent_scope=consent_scope)
    conn.execute(
        """
        INSERT INTO facts (
          subject_entity_id, predicate, object_literal, polarity,
          valid_from, status, confidence, created_from, scope, project_path
        ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """,
        (
            subject_id, predicate, body, triple.polarity,
            _now_iso(), triple.confidence, triple.source_content_id,
            triple.scope, triple.project_path,
        ),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return row[0]


_FTS5_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u00C0-\uFFFF]+")
_FTS5_QUOTED_PHRASE_RE = re.compile(r'"([^"]+)"')


def _quote_fts_phrase(raw: str) -> str | None:
    tokens = _FTS5_TOKEN_RE.findall(raw)
    if not tokens:
        return None
    return '"' + " ".join(tokens) + '"'


def sanitize_fts_query(query: str) -> str:
    """Wrap raw user input as FTS5 quoted terms and phrases.

    FTS5 treats unquoted ``-`` as the NOT operator and certain digits as
    column references, so a literal token like ``adr-99`` raises
    ``sqlite3.OperationalError: no such column: 99``. Word-like tokens
    (Unicode letters / digits / underscore) are quoted so the parser sees
    them as literals. User-provided quoted phrases are kept as one FTS5
    phrase after token normalization. Empty input falls back to a sentinel
    that matches nothing.
    """
    parts: list[str] = []
    query = query or ""
    cursor = 0
    for match in _FTS5_QUOTED_PHRASE_RE.finditer(query):
        prefix = query[cursor:match.start()]
        parts.extend(f'"{t}"' for t in _FTS5_TOKEN_RE.findall(prefix))
        phrase = _quote_fts_phrase(match.group(1))
        if phrase is not None:
            parts.append(phrase)
        cursor = match.end()
    suffix = query[cursor:]
    parts.extend(f'"{t}"' for t in _FTS5_TOKEN_RE.findall(suffix))
    if not parts:
        return '"__noop__"'
    return " ".join(parts)


_sanitize_fts_query = sanitize_fts_query


def fts_search(
    conn,
    query: str,
    *,
    limit: int = 10,
    include_history: bool = False,
) -> list[tuple[int, str, str]]:
    """FTS5 keyword search. Returns (facts.id, predicate, object_literal).

    By default only returns facts with status='active'.
    Pass include_history=True to include expired and superseded facts.
    """
    safe_query = sanitize_fts_query(query)
    status_clause = "" if include_history else "AND f.status = 'active'"
    cur = conn.execute(
        f"""
        SELECT f.id, f.predicate, f.object_literal
          FROM facts_fts s
          JOIN facts f ON f.id = s.rowid
         WHERE facts_fts MATCH ?
           {status_clause}
         ORDER BY bm25(facts_fts)
         LIMIT ?
        """,
        (safe_query, limit),
    )
    return list(cur.fetchall())


# ----------------------------------------------------------------------------
# ADR-05 S1 — markdown frontmatter ingest (deterministic, no LLM)
# ----------------------------------------------------------------------------

DEFAULT_WHITELIST: tuple[str, ...] = (
    "docs/decisions/adr-*.md",
    "docs/**/*.md",
)
_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_INLINE_LIST_RE = re.compile(r"^\[(.*)\]$")
_LINK_RE = re.compile(r"docs/[A-Za-z0-9_./-]+\.md")


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Tiny YAML-like parser for Mir ADR frontmatter.

    Supports ``key: scalar``, ``key: [a, b, c]``, and multi-line block lists
    (``key:\\n  - item``). Nested mappings and quoted multi-lines are out of
    scope. Returns ``{}`` when the file has no ``---`` block.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    raw = m.group(1)
    out: dict[str, object] = {}
    pending_key: str | None = None
    pending_list: list[str] | None = None
    for line in raw.splitlines():
        if pending_key is not None and line.startswith(("  - ", "  -\t")):
            if pending_list is None:
                pending_list = []
            pending_list.append(line[4:].strip().strip('"').strip("'"))
            continue
        if pending_key is not None:
            out[pending_key] = pending_list or []
            pending_key = None
            pending_list = None
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            pending_key = key
            pending_list = []
            continue
        list_match = _INLINE_LIST_RE.match(value)
        if list_match:
            items = [
                p.strip().strip('"').strip("'")
                for p in list_match.group(1).split(",")
                if p.strip()
            ]
            out[key] = items
        else:
            out[key] = value.strip('"').strip("'")
    if pending_key is not None:
        out[pending_key] = pending_list or []
    return out


def _adr_slug(path: Path) -> str:
    """``docs/decisions/adr-05-foo.md`` -> ``adr-05-foo``."""
    return path.stem


def _matches_whitelist(rel_path: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(rel_path, g) for g in globs)


def _frontmatter_to_triples(slug: str, fm: dict[str, object]) -> list[Triple]:
    """Flatten the frontmatter dict into one Triple per (key, value).

    Each Triple carries ``is_list_member=True`` when the source value was a
    list, so the ingest pipeline can treat list items as independent set
    members instead of replacing each other via R1 supersede.
    """
    triples: list[Triple] = []
    for key, value in fm.items():
        if isinstance(value, list):
            for item in value:
                if not item:
                    continue
                triples.append(
                    Triple(
                        subject_slug=slug,
                        predicate=str(key),
                        object_literal=str(item),
                        is_list_member=True,
                    )
                )
        else:
            text_val = str(value).strip()
            if not text_val:
                continue
            triples.append(
                Triple(
                    subject_slug=slug,
                    predicate=str(key),
                    object_literal=text_val,
                )
            )
    return triples


def _supersede_existing(
    conn,
    *,
    subject_id: int,
    predicate: str,
    new_object: str,
    new_confidence: float,
    new_valid_from: str,
    new_fact_id: int,
    current_content_id: int | None = None,
) -> tuple[int, list[int]]:
    """Apply R1 (newer valid_from) and R2 (higher confidence) supersede rules.

    Cascade order, per ADR-05 §2.4:

    * **R1** — whichever fact has the more recent ``valid_from`` wins.
    * **R2** — when ``valid_from`` ties exactly, the higher ``confidence`` wins.
    * **R4** — when both tie, *both rows stay active*; an S2 ``conflicts``
      row will surface them later.

    Returns ``(superseded_count, superseded_fact_ids)``. The id list always
    refers to facts whose ``status`` was just flipped to ``'superseded'`` —
    that may include ``new_fact_id`` itself when the loser is the new fact
    (the ``winner == "old"`` branch).

    ``current_content_id`` filters out facts inserted by the same ingest
    batch (same ``content_items.id``). This prevents *list-valued*
    frontmatter predicates (e.g. ``keywords: [a, b, c]``) from cascading
    supersedes within a single ingest — each list item is conceptually a
    *set* member, not a sequence step.
    """
    if current_content_id is None:
        rows = conn.execute(
            """
            SELECT id, object_literal, confidence, valid_from
              FROM facts
             WHERE subject_entity_id = ?
               AND predicate          = ?
               AND status             = 'active'
               AND id                != ?
            """,
            (subject_id, canonicalize(predicate), new_fact_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, object_literal, confidence, valid_from
              FROM facts
             WHERE subject_entity_id = ?
               AND predicate          = ?
               AND status             = 'active'
               AND id                != ?
               AND (created_from IS NULL OR created_from != ?)
            """,
            (subject_id, canonicalize(predicate), new_fact_id, current_content_id),
        ).fetchall()
    superseded_ids: list[int] = []
    for fid, old_obj, old_conf, old_vf in rows:
        if old_obj == new_object:
            continue
        winner: str | None = None
        if (new_valid_from or "") > (old_vf or ""):
            winner = "new"  # R1
        elif (old_vf or "") > (new_valid_from or ""):
            winner = "old"  # R1 (other side)
        elif new_confidence > (old_conf or 0):
            winner = "new"  # R2: equal valid_from, higher confidence
        elif (old_conf or 0) > new_confidence:
            winner = "old"  # R2 (other side)
        # else: full tie -> R4 -> both stay active
        if winner == "new":
            conn.execute(
                "UPDATE facts SET status = 'superseded', valid_to = ? WHERE id = ?",
                (_now_iso(), fid),
            )
            superseded_ids.append(fid)
        elif winner == "old":
            conn.execute(
                "UPDATE facts SET status = 'superseded', valid_to = ? WHERE id = ?",
                (_now_iso(), new_fact_id),
            )
            superseded_ids.append(new_fact_id)
            # The new fact already lost; stop scanning further candidates.
            return len(superseded_ids), superseded_ids
    return len(superseded_ids), superseded_ids


def _audit_supersede(conn, fact_id: int, subject_slug: str, predicate: str) -> None:
    """Best-effort audit_log row via ``store.audit_append``."""
    try:
        from .store import audit_append
    except Exception:
        return
    try:
        audit_append(
            conn,
            event="distill.supersede",
            payload={
                "fact_id": fact_id,
                "subject_slug": subject_slug,
                "predicate": predicate,
            },
            commit=False,
        )
    except Exception:
        pass


def _link_cross_refs(conn, raw: str, subject_id: int) -> int:
    """Insert ``fact_links`` rows for every ``docs/.../adr-*.md`` mention
    whose target slug already has an entity. Returns the count of new links.
    """
    targets = {m.group(0) for m in _LINK_RE.finditer(raw)}
    added = 0
    for path_text in targets:
        target_slug = Path(path_text).stem
        if not target_slug:
            continue
        row = conn.execute(
            "SELECT id FROM entities WHERE slug = ?", (target_slug,)
        ).fetchone()
        if not row:
            continue
        target_id = row[0]
        if target_id == subject_id:
            continue
        from_fact = conn.execute(
            "SELECT id FROM facts WHERE subject_entity_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (subject_id,),
        ).fetchone()
        to_fact = conn.execute(
            "SELECT id FROM facts WHERE subject_entity_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (target_id,),
        ).fetchone()
        if not from_fact or not to_fact:
            continue
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO fact_links(from_fact_id, to_fact_id, link_type) "
                "VALUES (?, ?, ?)",
                (from_fact[0], to_fact[0], "adr-cross-ref"),
            )
            if cur.rowcount:
                added += 1
        except Exception:
            pass
    return added


def ingest_markdown_file(
    path: Path,
    *,
    conn,
    whitelist_globs: tuple[str, ...] = DEFAULT_WHITELIST,
    project_root: Path | None = None,
) -> IngestResult:
    """ADR-05 S1 entry point. Read ``path`` and ingest its frontmatter.

    Whitelist matching is performed on the path *relative to* ``project_root``
    (default: ``Path.cwd()``). Non-whitelist paths are silently skipped and
    return a ``no_op`` result so the hook can stay non-blocking.

    file_hash dedup — re-ingesting an unchanged file is a no-op.
    """
    path = Path(path)
    root = project_root or Path.cwd()
    try:
        rel = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = str(path)
    if not _matches_whitelist(rel, whitelist_globs):
        return IngestResult(0, 0, 0, "", True, "whitelist")

    # ``utf-8-sig`` strips the optional BOM; the regex anchor ``\A---`` would
    # otherwise miss BOM-prefixed files and silently return no_op (R2.5).
    raw = path.read_text(encoding="utf-8-sig")
    file_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    existing = conn.execute(
        "SELECT id FROM content_items WHERE source = ? AND text_hash = ? LIMIT 1",
        ("self_ingest_md", file_hash),
    ).fetchone()
    if existing:
        return IngestResult(0, 0, 0, file_hash, True, "unchanged")

    fm = _parse_frontmatter(raw)
    if not fm:
        return IngestResult(0, 0, 0, file_hash, True, "empty_frontmatter")

    # Single-transaction ingest: BEGIN IMMEDIATE serializes against
    # concurrent writers and audit_append is invoked in commit=False mode so
    # the audit row participates in this transaction (atomic with the facts
    # supersede UPDATE).
    in_outer_tx = bool(getattr(conn, "in_transaction", False))
    if not in_outer_tx:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            # Another writer holds the lock; sqlite3 busy_timeout retries the
            # subsequent statements. Fall through.
            pass
    try:
        conn.execute(
            """
            INSERT INTO content_items
              (source, occurred_at, ingested_at, text_hash, byte_len, raw_text, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "self_ingest_md",
                _now_iso(),
                _now_iso(),
                file_hash,
                len(raw.encode("utf-8")),
                raw,
                json.dumps({"path": rel}, ensure_ascii=False),
            ),
        )
        content_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        slug = _adr_slug(path)
        entity_type = fm.get('type') if isinstance(fm.get('type'), str) else None
        subject_id = _upsert_entity(conn, slug, entity_type=entity_type)
        facts_inserted = 0
        facts_superseded = 0
        for triple in _frontmatter_to_triples(slug, fm):
            canon_pred = canonicalize(triple.predicate)
            existing = conn.execute(
                "SELECT id FROM facts WHERE subject_entity_id = ? AND predicate = ? "
                "AND object_literal = ? AND status = 'active' LIMIT 1",
                (subject_id, canon_pred, triple.object_literal),
            ).fetchone()
            if existing:
                continue
            new_fact_id = insert_triple(
                conn,
                Triple(
                    subject_slug=triple.subject_slug,
                    predicate=triple.predicate,
                    object_literal=triple.object_literal,
                    source_content_id=content_id,
                    confidence=triple.confidence,
                ),
            )
            facts_inserted += 1
            new_vf = conn.execute(
                "SELECT valid_from FROM facts WHERE id = ?", (new_fact_id,)
            ).fetchone()[0]
            if triple.is_list_member:
                # List items are set members; each one is independent — skip
                # supersede so siblings (and prior list values) stay active.
                # Cross-batch deletion of a dropped list item is deferred to
                # ADR-05 S2 (lint pass).
                n_super = 0
                superseded_ids: list[int] = []
            else:
                n_super, superseded_ids = _supersede_existing(
                    conn,
                    subject_id=subject_id,
                    predicate=triple.predicate,
                    new_object=triple.object_literal,
                    new_confidence=triple.confidence,
                    new_valid_from=new_vf,
                    new_fact_id=new_fact_id,
                    current_content_id=content_id,
                )
            if n_super:
                facts_superseded += n_super
                for fid in superseded_ids:
                    _audit_supersede(conn, fid, slug, triple.predicate)
                # When the new fact lost the supersede race (winner=="old"),
                # ``new_fact_id`` is itself in superseded_ids — undo the
                # earlier increment so ``facts_inserted`` reflects net new
                # active rows (R2.5 finding 2).
                if new_fact_id in superseded_ids:
                    facts_inserted -= 1

        fact_links_added = _link_cross_refs(conn, raw, subject_id)

        # Link facts to external_documents by relative path match (ADR-53 Phase 2)
        ext_doc_row = conn.execute(
            "SELECT id FROM external_documents WHERE relative_path = ?",
            (rel,),
        ).fetchone()
        if ext_doc_row is not None:
            ext_doc_id = ext_doc_row[0]
            fact_rows = conn.execute(
                "SELECT id FROM facts WHERE created_from = ?",
                (content_id,),
            ).fetchall()
            for (fact_id,) in fact_rows:
                conn.execute(
                    "INSERT OR IGNORE INTO fact_documents(fact_id, document_id) VALUES (?, ?)",
                    (fact_id, ext_doc_id),
                )

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    return IngestResult(
        facts_inserted=facts_inserted,
        facts_superseded=facts_superseded,
        fact_links_added=fact_links_added,
        file_hash=file_hash,
        no_op=False,
    )

# ----------------------------------------------------------------------------
# P50-B — DB read helpers for projection (recall_ingested_index, recall_lessons)
# ----------------------------------------------------------------------------


def recall_ingested_index(conn) -> list[dict]:
    """Return a list of dicts describing ingested documents for memory-map projection.

    Each dict has: slug, title, keywords, path.
    - slug: entity slug from entities table
    - title: object_literal from facts where predicate='title' (empty string if absent)
    - keywords: list of object_literal values from facts where predicate='keywords'
    - path: JSON-decoded metadata_json path field from content_items (or empty string)

    Only entities that have a matching content_items row (source='self_ingest_md') are
    included, so this reflects actually-ingested documents.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT e.slug,
               ci.metadata_json
          FROM entities e
          JOIN facts f ON f.subject_entity_id = e.id
          JOIN content_items ci ON ci.id = f.created_from
         WHERE ci.source = 'self_ingest_md'
           AND f.status = 'active'
        """
    ).fetchall()

    result = []
    seen: set[str] = set()
    for slug, meta_json in rows:
        if slug in seen:
            continue
        seen.add(slug)
        try:
            meta = json.loads(meta_json or "{}")
        except Exception:
            meta = {}
        path = meta.get("path", "")

        title_row = conn.execute(
            """
            SELECT object_literal FROM facts
             WHERE subject_entity_id = (SELECT id FROM entities WHERE slug = ?)
               AND predicate = 'title'
               AND status = 'active'
             LIMIT 1
            """,
            (slug,),
        ).fetchone()
        title = title_row[0] if title_row else ""

        kw_rows = conn.execute(
            """
            SELECT object_literal FROM facts
             WHERE subject_entity_id = (SELECT id FROM entities WHERE slug = ?)
               AND predicate = 'keywords'
               AND status = 'active'
            ORDER BY id
            """,
            (slug,),
        ).fetchall()
        # Deduplicate keywords while preserving first-occurrence order.
        # list-member facts are not superseded across ingest batches (set
        # semantics by design), so the same keyword value may appear as
        # multiple active rows after repeated ingests of an edited doc.
        kw_seen: set[str] = set()
        keywords: list[str] = []
        for (kw,) in kw_rows:
            if kw not in kw_seen:
                kw_seen.add(kw)
                keywords.append(kw)

        result.append({"slug": slug, "title": title, "keywords": keywords, "path": path})

    result.sort(key=lambda r: r["slug"])
    return result


# ----------------------------------------------------------------------------
# B2-FOLLOWUP — reconcile_missing_source
# Expire active facts whose source content_item path no longer exists on disk.
# ----------------------------------------------------------------------------


def reconcile_missing_source(
    conn,
    *,
    project_root: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Expire active facts sourced from content_items whose file path is missing.

    Rules:
    - Only processes content_items with source='self_ingest_md' (ingest-md facts).
    - Only touches facts with status='active'.
    - Path resolution: metadata_json['path'] is tested as an absolute path first;
      if relative, it is resolved against project_root (default: Path.cwd()).
    - Facts whose source path STILL EXISTS are not touched.
    - Facts with no created_from (manual inserts) are not touched.
    - Operation is idempotent: already-expired facts are skipped.
    - dry_run=True reports the count without writing any rows.

    Returns the number of facts newly set to 'expired'.
    """
    root = project_root or Path.cwd()
    today = _now_iso()

    # Collect content_item ids whose path is missing
    rows = conn.execute(
        "SELECT id, metadata_json FROM content_items WHERE source = 'self_ingest_md'"
    ).fetchall()

    missing_content_ids: list[int] = []
    for ci_id, meta_json in rows:
        try:
            meta = json.loads(meta_json or "{}")
        except Exception:
            continue
        path_str = meta.get("path", "")
        if not path_str:
            continue
        p = Path(path_str)
        if not p.is_absolute():
            p = root / p
        if not p.exists():
            missing_content_ids.append(ci_id)

    if not missing_content_ids:
        return 0

    # Find active facts sourced from those content_items
    placeholders = ",".join("?" * len(missing_content_ids))
    fact_rows = conn.execute(
        f"SELECT id FROM facts WHERE status = 'active' AND created_from IN ({placeholders})",
        missing_content_ids,
    ).fetchall()

    if not fact_rows:
        return 0

    if dry_run:
        return len(fact_rows)

    fact_ids = [r[0] for r in fact_rows]
    for fid in fact_ids:
        conn.execute(
            "UPDATE facts SET status = 'expired', valid_to = ? WHERE id = ?",
            (today, fid),
        )
    conn.commit()
    return len(fact_ids)


def recall_lessons(conn) -> list[dict]:
    """Return active facts with predicate='lesson' for lessons projection.

    Each dict has: slug, text.
    - slug: entity slug (e.g. 'lesson-design-first')
    - text: object_literal (the rule text)

    Only active facts are returned (status='active').
    """
    rows = conn.execute(
        """
        SELECT e.slug, f.object_literal
          FROM facts f
          JOIN entities e ON e.id = f.subject_entity_id
         WHERE f.predicate = 'lesson'
           AND f.status    = 'active'
         ORDER BY f.id
        """
    ).fetchall()
    return [{"slug": slug, "text": text} for slug, text in rows]
