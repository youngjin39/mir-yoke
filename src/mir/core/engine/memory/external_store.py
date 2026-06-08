"""External archive indexer — path-only + embedding + FTS5 (ADR 1).

design v0.6 §5 · decisions/adr-01-external-store.md.

Mir memory.db keeps only ``(archive, document, chunk)`` rows plus
``external_chunks_vec`` (sqlite-vec) and ``external_chunks_fts`` (FTS5
contentless). File bodies stay in the file system — Mir never writes into
the archive. ``mode='immutable'`` archives are additionally wired into
``PolicyStore.denied_paths`` by the config loader (ADR 1 §2.8).

Key invariants:
  * ``external_chunks.id == external_chunks_vec.rowid == external_chunks_fts.rowid``
    — all three populated inside one sqlite transaction per chunk.
  * Chunking is char-oriented (800 + 100 overlap default). ``byte_start``
    and ``byte_end`` record the UTF-8 byte offsets of those char slices
    so ``file.read()[byte_start:byte_end].decode("utf-8")`` round-trips.
  * vec0 creation is runtime-only via ``ensure_external_vec_table`` —
    migration 015 does not touch sqlite-vec (Third Review TB1).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mir.core.engine.memory.distill import _parse_frontmatter, sanitize_fts_query
from mir.core.engine.memory.store import Connection
from mir.core.engine.memory.vector_index import (
    _pack_vector,
    validate_embedding,
)

DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_EMBED_DIM = 1024
CURRENT_METADATA_VERSION = '3'  # v3: archive-path status derivation backfill (ADR-53 D5)


# --- Errors ------------------------------------------------------------

class ExternalStoreError(RuntimeError):
    """Base error for external_store operations."""


class ExternalArchiveOverlapError(ExternalStoreError):
    """Two archives cover the same absolute path (self-review M7)."""


# --- Data classes -------------------------------------------------------

@dataclass(frozen=True)
class Chunk:
    """A char-bounded slice of file text with its UTF-8 byte range."""

    chunk_index: int
    text: str
    byte_start: int
    byte_end: int
    text_hash: str


@dataclass(frozen=True)
class ScanResult:
    inserted: int
    deleted: int
    reindexed: int
    unchanged: int
    failed: tuple[tuple[str, str], ...] = ()    # (relpath, reason) per file


@dataclass(frozen=True)
class ExternalHit:
    """One hybrid-search result."""

    archive_slug: str
    relative_path: str
    byte_start: int
    byte_end: int
    score: float
    status: str = 'active'


# --- vec0 runtime helper (Third Review TB1) ----------------------------

def ensure_external_vec_table(
    conn, *, dim: int = DEFAULT_EMBED_DIM
) -> None:
    """Create ``external_chunks_vec`` if sqlite-vec is loaded.

    Caller must verify ``Connection.vec_available`` first — calling this
    against a connection without the extension will raise ``sqlite3``
    errors. Uses the same lowercase ``float[NNN]`` contract as
    ``facts_vec`` (v0.5.3 V8).
    """
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS external_chunks_vec "
        f"USING vec0(embedding float[{dim}])"
    )


# --- Chunker (self-review H2) -------------------------------------------

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。!?])\s+")
_PARAGRAPH_BOUNDARY = "\n\n"


def _chunk_text(
    raw: str,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split *raw* into character-bounded chunks.

    Paragraph boundary first, sentence next, char last. ``byte_start`` /
    ``byte_end`` record the UTF-8 byte range of the char slice so callers
    can re-read the original bytes without a round-trip through str.
    """
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError(
            f"invalid chunk params size={size!r} overlap={overlap!r}"
        )
    if not raw:
        return []

    # Precompute char_index → byte_offset table once (UTF-8 widths vary).
    byte_offsets: list[int] = [0]
    running = 0
    for ch in raw:
        running += len(ch.encode("utf-8"))
        byte_offsets.append(running)
    total_chars = len(raw)
    assert byte_offsets[-1] == len(raw.encode("utf-8"))

    chunks: list[Chunk] = []
    start = 0
    idx = 0
    while start < total_chars:
        end = min(start + size, total_chars)
        # Prefer paragraph break within [start, end]
        if end < total_chars:
            window = raw[start:end]
            pbreak = window.rfind(_PARAGRAPH_BOUNDARY)
            if pbreak > overlap:                # don't collapse to tiny chunk
                end = start + pbreak + len(_PARAGRAPH_BOUNDARY)
            else:
                # Fall back to sentence boundary
                match = None
                for m in _SENTENCE_BOUNDARY.finditer(window):
                    match = m
                if match is not None and match.end() > overlap:
                    end = start + match.end()
                # else: hard char boundary (end stays at start + size)

        piece = raw[start:end]
        chunks.append(
            Chunk(
                chunk_index=idx,
                text=piece,
                byte_start=byte_offsets[start],
                byte_end=byte_offsets[end],
                text_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
            )
        )
        idx += 1
        if end >= total_chars:
            break
        start = max(0, end - overlap)
    return chunks


# --- Glob matcher -------------------------------------------------------

def _compile_globs(spec: str | None) -> tuple[str, ...]:
    if not spec:
        return ()
    return tuple(g.strip() for g in spec.split(",") if g.strip())


def _matches_any(rel: str, patterns: Iterable[str]) -> bool:
    for p in patterns:
        if fnmatch.fnmatch(rel, p):
            return True
    return False



def _derive_doc_category(rel: str) -> str | None:
    # archive check precedes decisions: archive paths may contain /decisions/
    if '/_archive/' in rel or rel.startswith('docs/_archive/') or rel.startswith('_archive/'):
        return 'archive'
    if rel.startswith('docs/decisions/'):
        return 'decision'
    if rel.startswith('.ai-harness/'):
        return 'harness-rule'
    if rel.startswith('tasks/'):
        return 'task'
    if rel.startswith('docs/'):
        return 'doc'
    return None


def _derive_layer(rel: str) -> str | None:
    if (
        '/_archive/' in rel
        or rel.startswith('docs/_archive/')
        or rel.startswith('_archive/')
        or rel.startswith('tasks/handoffs/')
        or rel.startswith('tasks/sessions/')
    ):
        return 'episodic'
    if rel.startswith('docs/'):
        return 'semantic'
    if rel.startswith('.ai-harness/'):
        return 'procedural'
    if rel.startswith('tasks/'):
        return 'working'
    return None


def _glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a ``**``-aware glob to a regex (fnmatch lacks ``**``)."""
    # Normalise and split segments.
    buf: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern[i:i + 3] == "**/":
            buf.append(r"(?:.*/)?")
            i += 3
        elif pattern[i:i + 2] == "**":
            buf.append(r".*")
            i += 2
        elif ch == "*":
            buf.append(r"[^/]*")
            i += 1
        elif ch == "?":
            buf.append(r"[^/]")
            i += 1
        elif ch in ".+^$(){}|\\":
            buf.append(re.escape(ch))
            i += 1
        else:
            buf.append(ch)
            i += 1
    buf.append("$")
    return re.compile("".join(buf))


def _compile_pattern_set(patterns: tuple[str, ...]) -> tuple[re.Pattern, ...]:
    return tuple(_glob_to_regex(p) for p in patterns)


def _matches_regex_any(rel: str, compiled: tuple[re.Pattern, ...]) -> bool:
    return any(c.match(rel) for c in compiled)


def _walk_archive(
    root: Path,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
) -> Iterator[str]:
    """Yield archive-relative paths matching *include* and not *exclude*.

    ``**`` is honoured: ``**/*.md`` matches any-depth .md files (fnmatch
    treats ``**`` as ``*`` so we pre-compile to regex instead).
    """
    root = root.resolve()
    if not root.is_dir():
        return
    inc_regex = _compile_pattern_set(include) if include else ()
    exc_regex = _compile_pattern_set(exclude) if exclude else ()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if inc_regex and not _matches_regex_any(rel, inc_regex):
            continue
        if exc_regex and _matches_regex_any(rel, exc_regex):
            continue
        yield rel


# --- Core store ---------------------------------------------------------

@dataclass(frozen=True)
class _ArchiveRow:
    id: int
    slug: str
    root_path: str
    mode: str
    glob_include: tuple[str, ...]
    glob_exclude: tuple[str, ...]
    chunk_size: int
    chunk_overlap: int


def _int_ver(v: str) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return -1


_FIRST_HEADING_RE = re.compile(r'^\#\s+(.+)', re.MULTILINE)


def _extract_title_and_frontmatter(text: str) -> tuple[str | None, str | None]:
    try:
        fm = _parse_frontmatter(text)
    except Exception:
        return None, None
    frontmatter_json: str | None = None
    if fm:
        try:
            frontmatter_json = json.dumps(fm, ensure_ascii=False)
        except Exception:
            frontmatter_json = None
    title: str | None = None
    fm_title = fm.get('title') if fm else None
    if isinstance(fm_title, str) and fm_title.strip():
        title = fm_title.strip()
    else:
        m = _FIRST_HEADING_RE.search(text)
        if m:
            title = m.group(1).strip() or None
    return title, frontmatter_json


def _doc_created_ordinal(frontmatter_json_str: str | None) -> int:
    """Parse frontmatter_json 'created' field to ordinal for recency sort.

    Advisory fold (a): parse str(created)[:10] so datetime strings like
    '2026-06-06T12:00:00' rank by date rather than falling back to ordinal 0.

    Returns 0 for missing/unparseable values (ADR-53 D6 — ranking-only nondeterminism boundary).
    """
    if not frontmatter_json_str:
        return 0
    try:
        fm = json.loads(frontmatter_json_str)
        created = fm.get('created')
        if not created:
            return 0
        from datetime import date
        # Take first 10 chars to handle both date strings and datetime strings
        date_str = str(created)[:10]
        return date.fromisoformat(date_str).toordinal()
    except Exception:
        return 0


class ExternalStore:
    """Indexer for external file archives.

    The store takes a pre-built :class:`Connection` (so sqlite-vec is
    loaded exactly once — Third Review TM3) and never opens its own.
    Constructors should run ``ensure_external_vec_table`` if the caller
    wants vector search; FTS5-only mode is valid when
    ``conn.vec_available`` is False (TB1 fallback).
    """

    def __init__(self, conn: Connection):
        self._conn = conn
        if conn.vec_available:
            ensure_external_vec_table(conn.conn)

    # ---- registration ----

    def register(
        self,
        *,
        slug: str,
        root_path: str,
        mode: str,
        glob_include: tuple[str, ...] = (),
        glob_exclude: tuple[str, ...] = (),
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        owner: str,
    ) -> int:
        """Insert or update an archive row. Returns archive_id."""
        if mode not in ("indexed", "immutable"):
            raise ValueError(f"invalid mode {mode!r}")
        now = datetime.now(UTC).isoformat()
        cur = self._conn.conn.execute(
            """
            INSERT INTO external_archives
              (slug, root_path, mode, glob_include, glob_exclude,
               chunk_size, chunk_overlap, owner, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
              root_path = excluded.root_path,
              mode = excluded.mode,
              glob_include = excluded.glob_include,
              glob_exclude = excluded.glob_exclude,
              chunk_size = excluded.chunk_size,
              chunk_overlap = excluded.chunk_overlap,
              owner = excluded.owner
            RETURNING id
            """,
            (
                slug, root_path, mode,
                ",".join(glob_include) if glob_include else None,
                ",".join(glob_exclude) if glob_exclude else None,
                chunk_size, chunk_overlap, owner, now,
            ),
        )
        row = cur.fetchone()
        self._conn.conn.commit()
        return row[0]

    def _fetch_archive(self, archive_id: int) -> _ArchiveRow:
        row = self._conn.conn.execute(
            "SELECT id, slug, root_path, mode, glob_include, glob_exclude, "
            "chunk_size, chunk_overlap "
            "FROM external_archives WHERE id = ?",
            (archive_id,),
        ).fetchone()
        if row is None:
            raise ExternalStoreError(f"archive_id {archive_id} not found")
        return _ArchiveRow(
            id=row[0], slug=row[1], root_path=row[2], mode=row[3],
            glob_include=_compile_globs(row[4]),
            glob_exclude=_compile_globs(row[5]),
            chunk_size=row[6], chunk_overlap=row[7],
        )

    # ---- scan ----

    def scan(
        self,
        archive_id: int,
        *,
        embed_fn=None,
        embed_batch_size: int | None = None,
    ) -> ScanResult:
        """Sync ``external_documents/chunks/fts/vec`` with the filesystem.

        ``embed_fn(list[str]) -> list[list[float]]`` is called per file
        (batched per its chunks). If ``None``, vector index is skipped
        (FTS5-only mode). If the connection lacks vec_available, vector
        writes are silently skipped per TB1 graceful-degradation rule.
        """
        archive = self._fetch_archive(archive_id)
        root = Path(archive.root_path)
        current_fs = set(_walk_archive(root, archive.glob_include, archive.glob_exclude))

        db_rows = self._conn.conn.execute(
            "SELECT relative_path FROM external_documents WHERE archive_id = ?",
            (archive_id,),
        ).fetchall()
        db_set = {r[0] for r in db_rows}

        forced_rescan = False
        _stored_ver = self._conn.conn.execute(
            "SELECT value FROM external_store_meta WHERE key='schema_metadata_version'"
        ).fetchone()
        if (
            _stored_ver is not None
            and _int_ver(_stored_ver[0]) < _int_ver(CURRENT_METADATA_VERSION)
        ):
            forced_rescan = True

        to_delete = db_set - current_fs
        to_insert = current_fs - db_set
        to_check  = current_fs & db_set

        inserted = deleted = reindexed = unchanged = 0
        failed: list[tuple[str, str]] = []

        for rel in to_delete:
            try:
                self._cascade_delete_document(archive_id, rel)
                deleted += 1
            except Exception as e:                          # pragma: no cover
                failed.append((rel, f"delete: {e}"))

        for rel in to_insert:
            try:
                self._index_file(
                    archive, rel,
                    embed_fn=embed_fn, embed_batch_size=embed_batch_size,
                )
                inserted += 1
            except Exception as e:
                failed.append((rel, f"insert: {e}"))

        for rel in to_check:
            try:
                changed = self._reindex_if_changed(
                    archive, rel,
                    embed_fn=embed_fn, embed_batch_size=embed_batch_size,
                    forced=forced_rescan,
                )
                if changed:
                    reindexed += 1
                else:
                    unchanged += 1
            except Exception as e:
                failed.append((rel, f"reindex: {e}"))

        if forced_rescan and not failed:
            self._conn.conn.execute(
                "INSERT OR REPLACE INTO external_store_meta(key, value) "
                "VALUES ('schema_metadata_version', ?)",
                (CURRENT_METADATA_VERSION,),
            )
        elif _stored_ver is None:
            self._conn.conn.execute(
                "INSERT OR IGNORE INTO external_store_meta(key, value) "
                "VALUES ('schema_metadata_version', ?)",
                (CURRENT_METADATA_VERSION,),
            )

        self._conn.conn.execute(
            "UPDATE external_archives SET last_scanned_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), archive_id),
        )
        self._conn.conn.commit()

        return ScanResult(
            inserted=inserted, deleted=deleted, reindexed=reindexed,
            unchanged=unchanged, failed=tuple(failed),
        )

    # ---- internals ----

    def _read_file(self, archive: _ArchiveRow, rel: str) -> tuple[str, str, int]:
        p = Path(archive.root_path) / rel
        data = p.read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ExternalStoreError(f"{rel}: not utf-8 ({e})") from e
        return text, file_hash, len(data)

    def _cascade_delete_document(self, archive_id: int, rel: str) -> None:
        conn = self._conn.conn
        with conn:
            # Locate doc + chunks up front so we can clear _fts / _vec explicitly.
            doc_row = conn.execute(
                "SELECT id FROM external_documents "
                "WHERE archive_id = ? AND relative_path = ?",
                (archive_id, rel),
            ).fetchone()
            if doc_row is None:
                return
            doc_id = doc_row[0]
            chunk_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM external_chunks WHERE document_id = ?",
                    (doc_id,),
                ).fetchall()
            ]
            for cid in chunk_ids:
                self._delete_chunk_rowid(cid)
            conn.execute("DELETE FROM external_documents WHERE id = ?", (doc_id,))
            # external_chunks rows cascade via FK.

    def _delete_chunk_rowid(self, chunk_id: int) -> None:
        conn = self._conn.conn
        conn.execute("DELETE FROM external_chunks_fts WHERE rowid = ?", (chunk_id,))
        if self._conn.vec_available:
            conn.execute("DELETE FROM external_chunks_vec WHERE rowid = ?", (chunk_id,))

    def _index_file(
        self,
        archive: _ArchiveRow,
        rel: str,
        *,
        embed_fn,
        embed_batch_size: int | None = None,
    ) -> int:
        """Insert a new document + its chunks. Returns document_id."""
        text, file_hash, byte_len = self._read_file(archive, rel)
        chunks = _chunk_text(
            text, size=archive.chunk_size, overlap=archive.chunk_overlap,
        )

        conn = self._conn.conn
        with conn:
            source_slug = 'your-harness'
            doc_category = _derive_doc_category(rel)
            layer = _derive_layer(rel)
            title, frontmatter_json = _extract_title_and_frontmatter(text)
            # ADR-53 D4: path-derived status — archive paths are 'expired' so default
            # retrieval excludes them; include_history=True still reaches them.
            doc_status = 'expired' if doc_category == 'archive' else 'active'
            cur = conn.execute(
                "INSERT INTO external_documents "
                "(archive_id, relative_path, file_hash, byte_len, vec_indexed_at, "
                "source_slug, doc_category, layer, status, title, frontmatter_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (archive.id, rel, file_hash, byte_len,
                 datetime.now(UTC).isoformat() if embed_fn and self._conn.vec_available else None,
                 source_slug, doc_category, layer, doc_status, title, frontmatter_json),
            )
            doc_id = cur.lastrowid
            assert doc_id is not None, "INSERT must return a rowid"
            self._insert_chunks(
                doc_id, chunks,
                embed_fn=embed_fn, embed_batch_size=embed_batch_size,
            )
        return doc_id

    def _reindex_if_changed(
        self,
        archive: _ArchiveRow,
        rel: str,
        *,
        embed_fn,
        embed_batch_size: int | None = None,
        forced: bool = False,
    ) -> bool:
        text, file_hash, byte_len = self._read_file(archive, rel)
        conn = self._conn.conn
        row = conn.execute(
            "SELECT id, file_hash FROM external_documents "
            "WHERE archive_id = ? AND relative_path = ?",
            (archive.id, rel),
        ).fetchone()
        if row is None:
            # race: vanished between diff and now — treat as insert.
            self._index_file(archive, rel, embed_fn=embed_fn)
            return True
        doc_id, old_hash = row
        if old_hash == file_hash and not forced:
            return False

        chunks = _chunk_text(
            text, size=archive.chunk_size, overlap=archive.chunk_overlap,
        )
        with conn:
            # Drop old chunks (cascades rowids in _fts / _vec too).
            old_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM external_chunks WHERE document_id = ?",
                    (doc_id,),
                ).fetchall()
            ]
            for cid in old_ids:
                self._delete_chunk_rowid(cid)
            conn.execute("DELETE FROM external_chunks WHERE document_id = ?", (doc_id,))
            source_slug = 'your-harness'
            doc_category = _derive_doc_category(rel)
            layer = _derive_layer(rel)
            title, frontmatter_json = _extract_title_and_frontmatter(text)
            # ADR-53 D4: path-derived status — archive paths are 'expired'.
            doc_status = 'expired' if doc_category == 'archive' else 'active'
            conn.execute(
                "UPDATE external_documents "
                "SET file_hash = ?, byte_len = ?, vec_indexed_at = ?, "
                "source_slug = ?, doc_category = ?, layer = ?, status = ?, "
                "title = ?, frontmatter_json = ? "
                "WHERE id = ?",
                (file_hash, byte_len,
                 datetime.now(UTC).isoformat() if embed_fn and self._conn.vec_available else None,
                 source_slug, doc_category, layer, doc_status, title, frontmatter_json, doc_id),
            )
            self._insert_chunks(
                doc_id, chunks,
                embed_fn=embed_fn, embed_batch_size=embed_batch_size,
            )
        return True

    def _insert_chunks(
        self,
        doc_id: int,
        chunks: list[Chunk],
        *,
        embed_fn,
        embed_batch_size: int | None = None,
    ) -> None:
        if not chunks:
            return
        conn = self._conn.conn
        # wave 2 RM1 — batching. Large files could submit 1000+ strings in
        # one embed_fn call, risking upstream timeout. batch_size=None → one
        # shot (previous behaviour). batch_size>0 → split.
        embeddings: list[list[float]] | None = None
        if embed_fn is not None and self._conn.vec_available:
            chunk_texts = [c.text for c in chunks]
            if embed_batch_size and embed_batch_size > 0:
                embeddings = []
                for i in range(0, len(chunk_texts), embed_batch_size):
                    batch = chunk_texts[i : i + embed_batch_size]
                    embeddings.extend(embed_fn(batch))
            else:
                embeddings = embed_fn(chunk_texts)
            if len(embeddings) != len(chunks):
                raise ExternalStoreError(
                    f"embed_fn returned {len(embeddings)} vectors for "
                    f"{len(chunks)} chunks"
                )

        for i, ch in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO external_chunks "
                "(document_id, chunk_index, byte_start, byte_end, text_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_id, ch.chunk_index, ch.byte_start, ch.byte_end, ch.text_hash),
            )
            chunk_id = cur.lastrowid
            conn.execute(
                "INSERT INTO external_chunks_fts(rowid, content) VALUES (?, ?)",
                (chunk_id, ch.text),
            )
            if embeddings is not None:
                vec = embeddings[i]
                validate_embedding(vec, expected_dim=DEFAULT_EMBED_DIM)
                conn.execute(
                    "INSERT INTO external_chunks_vec(rowid, embedding) VALUES (?, ?)",
                    (chunk_id, _pack_vector(vec)),
                )

    # ---- search ----

    def search(
        self,
        query: str,
        *,
        k: int = 10,
        archive_slugs: tuple[str, ...] | None = None,
        embed_fn=None,
        include_history: bool = False,
    ) -> list[ExternalHit]:
        """Hybrid search across registered archives.

        When ``embed_fn`` is provided and ``conn.vec_available`` is True,
        this performs a vec0 kNN + FTS5 MATCH + Reciprocal Rank Fusion.
        Otherwise it falls back to FTS5-only ranking (TB1).

        Only chunk metadata (path + byte range + score) is returned —
        the caller re-reads the file to get body text (ADR 1 §2.2).
        """
        # wave 2 SM6 — move the archive_slugs filter forward to the RRF input stage.
        # Previously this collected all vec_hits + fts_rows, ran RRF, and applied a
        # trailing slug filter after SELECT; rowids that should be excluded could
        # occupy RRF topk slots, so actual returned results could be fewer than k.
        # Query the chunk_id → slug mapping once up front and mask before RRF.
        allowed_chunk_ids: set[int] | None = None
        if archive_slugs:
            slug_filter_set = set(archive_slugs)
            allowed_chunk_ids = {
                row[0] for row in self._conn.conn.execute(
                    "SELECT c.id FROM external_chunks c "
                    "JOIN external_documents d ON d.id = c.document_id "
                    "JOIN external_archives a ON a.id = d.archive_id "
                    f"WHERE a.slug IN ({','.join('?' * len(slug_filter_set))})",
                    tuple(slug_filter_set),
                ).fetchall()
            }
            if not allowed_chunk_ids:
                return []

        # ADR-53 D4: default current-only filter (status='active'). include_history=True skips.
        if not include_history:
            status_chunk_ids: set[int] = {
                row[0] for row in self._conn.conn.execute(
                    'SELECT c.id FROM external_chunks c '
                    'JOIN external_documents d ON d.id = c.document_id '
                    "WHERE d.status = 'active'",
                ).fetchall()
            }
            if allowed_chunk_ids is not None:
                allowed_chunk_ids = allowed_chunk_ids & status_chunk_ids
            else:
                allowed_chunk_ids = status_chunk_ids
            if not allowed_chunk_ids:
                return []

        vec_hits: list[tuple[int, float]] = []
        if embed_fn is not None and self._conn.vec_available:
            try:
                [query_vec] = embed_fn([query])
            except ValueError:
                raise
            validate_embedding(query_vec, expected_dim=DEFAULT_EMBED_DIM)
            # wave 3 TN3 — sqlite-vec vec0 `distance` defaults to **L2 (Euclidean)**.
            # bge-m3 embeddings are normalized, so this works as a cosine substitute.
            # To switch to another metric, specify distance_metric at vec0 CREATE.
            # For now, keep the default L2.
            vec_hits = list(self._conn.conn.execute(
                "SELECT rowid, distance FROM external_chunks_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (_pack_vector(query_vec), k * 3),
            ).fetchall())
            if allowed_chunk_ids is not None:
                vec_hits = [h for h in vec_hits if h[0] in allowed_chunk_ids]

        safe_query = sanitize_fts_query(query)
        fts_rows = list(self._conn.conn.execute(
            "SELECT rowid, rank FROM external_chunks_fts "
            "WHERE external_chunks_fts MATCH ? ORDER BY rank, rowid ASC LIMIT ?",
            (safe_query, k * 3),
        ).fetchall())
        if allowed_chunk_ids is not None:
            fts_rows = [r for r in fts_rows if r[0] in allowed_chunk_ids]

        # RRF fusion (k_rrf = 60 as in the literature standard).
        k_rrf = 60.0
        scores: dict[int, float] = {}
        # Tied-rank RRF for vec: docs with identical distance receive the same RRF
        # contribution, preventing arbitrary row-order-dependent score differences.
        _vec_pos = 0
        _prev_vec_dist: float | None = None
        _vec_tie_start: int = 0
        for rowid, vec_dist in sorted(vec_hits, key=lambda h: (h[1], h[0])):
            if vec_dist != _prev_vec_dist:
                _vec_tie_start = _vec_pos
                _prev_vec_dist = vec_dist
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (k_rrf + _vec_tie_start)
            _vec_pos += 1
        # Tied-rank RRF for FTS: docs with identical BM25 rank receive the same
        # RRF contribution (position of the first doc in that tie group), so that
        # equal-relevance docs are not artificially separated by rowid order.
        _fts_pos = 0
        _prev_fts_rank: float | None = None
        _tie_start_pos: int = 0
        for rowid, fts_rank in fts_rows:
            if fts_rank != _prev_fts_rank:
                _tie_start_pos = _fts_pos
                _prev_fts_rank = fts_rank
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (k_rrf + _tie_start_pos)
            _fts_pos += 1

        if not scores:
            return []

        # ADR-53 D6: recency tie-break (-rrf_score, -created_ts).
        # Final key: (-rrf_score, -created_ordinal, chunk_id ASC) — chunk_id is
        # the ultimate stable tiebreaker making FTS-only results fully deterministic.
        candidate_ids = sorted(scores.keys())
        if candidate_ids:
            ph = ','.join('?' * len(candidate_ids))
            chunk_doc_rows = self._conn.conn.execute(
                f'SELECT c.id, c.document_id, d.frontmatter_json '
                f'FROM external_chunks c JOIN external_documents d ON d.id = c.document_id '
                f'WHERE c.id IN ({ph})',
                candidate_ids,
            ).fetchall()
            chunk_to_created: dict[int, int] = {
                r[0]: _doc_created_ordinal(r[2]) for r in chunk_doc_rows
            }
            rowids = sorted(
                candidate_ids,
                key=lambda rid: (-scores[rid], -chunk_to_created.get(rid, 0), rid),
            )[:k]
        else:
            rowids = []
        placeholders = ",".join("?" * len(rowids))
        rows = self._conn.conn.execute(
            f"""
            SELECT c.id, a.slug, d.relative_path, c.byte_start, c.byte_end, d.status
            FROM external_chunks c
            JOIN external_documents d ON d.id = c.document_id
            JOIN external_archives  a ON a.id = d.archive_id
            WHERE c.id IN ({placeholders})
            """,
            rowids,
        ).fetchall()
        row_by_id = {r[0]: r for r in rows}

        hits: list[ExternalHit] = []
        for rid in rowids:
            row = row_by_id.get(rid)
            if row is None:
                continue
            _, slug, relpath, bs, be, doc_status = row
            hits.append(ExternalHit(
                archive_slug=slug, relative_path=relpath,
                byte_start=bs, byte_end=be, score=scores[rid],
                status=doc_status if doc_status else 'active',
            ))
        return hits


__all__ = (
    "Chunk",
    "CURRENT_METADATA_VERSION",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_EMBED_DIM",
    "ExternalArchiveOverlapError",
    "ExternalHit",
    "ExternalStore",
    "ExternalStoreError",
    "ScanResult",
    "ensure_external_vec_table",
)
