"""ADR-53 Phase 3a — search() status filter + recency ranking tests (TDD-first)."""
from __future__ import annotations

from pathlib import Path

from mir.core.engine.memory import store
from mir.core.engine.memory.external_store import ExternalStore


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_search_default_excludes_expired_chunks(tmp_path):
    c = store.connect(tmp_path / "memory.db")
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "active.md", "quantum entanglement active document")
        _write(root, "expired.md", "quantum entanglement expired document")

        archive_id = es.register(
            slug="test-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)

        c.conn.execute(
            "UPDATE external_documents SET status='expired' WHERE relative_path='expired.md'"
        )
        c.conn.commit()

        hits = es.search("quantum entanglement", k=10, embed_fn=None)

        assert all(h.relative_path != "expired.md" for h in hits)
        assert any(h.relative_path == "active.md" for h in hits)
    finally:
        c.conn.close()


def test_search_include_history_returns_all(tmp_path):
    c = store.connect(tmp_path / "memory.db")
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "active.md", "quantum entanglement active document")
        _write(root, "expired.md", "quantum entanglement expired document")

        archive_id = es.register(
            slug="test-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)

        c.conn.execute(
            "UPDATE external_documents SET status='expired' WHERE relative_path='expired.md'"
        )
        c.conn.commit()

        hits = es.search(
            "quantum entanglement", k=10, embed_fn=None, include_history=True
        )
        paths = {h.relative_path for h in hits}

        assert "active.md" in paths
        assert "expired.md" in paths
    finally:
        c.conn.close()


def test_search_recency_tiebreak_more_recent_ranks_first(tmp_path):
    c = store.connect(tmp_path / "memory.db")
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(
            root,
            "older.md",
            "---\ncreated: 2023-01-01\n---\nneural network topology identical terms",
        )
        _write(
            root,
            "newer.md",
            "---\ncreated: 2025-06-01\n---\nneural network topology identical terms",
        )

        archive_id = es.register(
            slug="test-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)

        hits = es.search("neural network topology", k=10, embed_fn=None)

        assert len(hits) >= 2
        assert hits[0].relative_path == "newer.md"
    finally:
        c.conn.close()


def test_search_missing_created_no_crash(tmp_path):
    c = store.connect(tmp_path / "memory.db")
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "nodates.md", "stellar formation process")
        _write(
            root,
            "dated.md",
            "---\ncreated: 2024-03-15\n---\nstellar formation process",
        )

        archive_id = es.register(
            slug="test-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)

        hits = es.search("stellar formation", k=10, embed_fn=None)

        assert len(hits) >= 1
        assert "dated.md" in {h.relative_path for h in hits}
    finally:
        c.conn.close()


def test_search_fts_only_honors_status_filter(tmp_path):
    c = store.connect(tmp_path / "memory.db", load_vec=False)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "archived.md", "photosynthesis chlorophyll archived")
        _write(root, "current.md", "photosynthesis chlorophyll current")

        archive_id = es.register(
            slug="test-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)

        c.conn.execute(
            "UPDATE external_documents SET status='archived' WHERE relative_path='archived.md'"
        )
        c.conn.commit()

        hits = es.search("photosynthesis chlorophyll", k=10, embed_fn=None)

        assert all(h.relative_path != "archived.md" for h in hits)
        assert any(h.relative_path == "current.md" for h in hits)
    finally:
        c.conn.close()


def test_search_archive_slugs_with_include_history_combo(tmp_path):
    """archive_slugs scoping applies even when include_history=True.

    Advisory fold (b): history lifts the status gate only; archive_slugs
    scope still applies. A chunk from archive-B must not appear when
    archive_slugs=('archive-a',) even with include_history=True.
    """
    c = store.connect(tmp_path / "memory.db")
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root_a = tmp_path / "archive_a"
        root_b = tmp_path / "archive_b"
        _write(root_a, "doc_a.md", "supernova remnant stellar collapse active")
        _write(root_b, "doc_b.md", "supernova remnant stellar collapse other")

        id_a = es.register(
            slug="archive-a",
            root_path=str(root_a),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        id_b = es.register(
            slug="archive-b",
            root_path=str(root_b),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(id_a, embed_fn=None)
        es.scan(id_b, embed_fn=None)

        # Expire doc_b so it would only appear with include_history
        c.conn.execute(
            "UPDATE external_documents SET status='expired' WHERE relative_path='doc_b.md'"
        )
        c.conn.commit()

        # archive_slugs scoping must exclude archive-b even with include_history=True
        hits = es.search(
            "supernova remnant",
            k=10,
            embed_fn=None,
            archive_slugs=("archive-a",),
            include_history=True,
        )
        slugs = {h.archive_slug for h in hits}
        assert "archive-b" not in slugs, (
            "archive_slugs filter must scope out archive-b even with include_history=True"
        )
        # archive-a should still appear
        assert "archive-a" in slugs
    finally:
        c.conn.close()


def test_search_fts_only_result_order_is_deterministic(tmp_path):
    """Run the same FTS-only search 5 times in-process and assert identical result order.

    Catches dict-iteration nondeterminism inside search(). The docs share
    identical body text so BM25 scores tie, making ordering rely purely on
    the deterministic tiebreaker (chunk_id ASC).
    """
    c = store.connect(tmp_path / "memory.db")
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        for name in ("alpha.md", "beta.md", "gamma.md", "delta.md"):
            _write(root, name, "gravitational wave detector interferometer laser optics")

        archive_id = es.register(
            slug="det-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:det",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)

        results = [
            [h.relative_path for h in es.search("gravitational wave detector", k=10, embed_fn=None)]
            for _ in range(5)
        ]

        # All 5 runs must return exactly the same ordered list.
        for run in results[1:]:
            assert run == results[0], f"Non-deterministic order detected: {results[0]!r} vs {run!r}"
        # Must have found at least 3 docs.
        assert len(results[0]) >= 3
    finally:
        c.conn.close()

def test_search_include_history_hit_has_correct_status(tmp_path):
    """include_history=True: expired doc hit has status=='expired', active doc has status=='active'."""
    c = store.connect(tmp_path / 'memory.db')
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / 'archive'
        _write(root, 'active.md', 'quantum entanglement active document text here')
        _write(root, 'expired.md', 'quantum entanglement expired document text here')

        archive_id = es.register(
            slug='test-status-archive',
            root_path=str(root),
            mode='indexed',
            owner='family:x',
            glob_include=('**/*.md',),
        )
        es.scan(archive_id, embed_fn=None)

        c.conn.execute(
            "UPDATE external_documents SET status='expired' WHERE relative_path='expired.md'"
        )
        c.conn.commit()

        hits = es.search('quantum entanglement', k=10, embed_fn=None, include_history=True)
        by_path = {h.relative_path: h for h in hits}

        assert 'active.md' in by_path, 'active doc must appear'
        assert 'expired.md' in by_path, 'expired doc must appear with include_history=True'
        assert by_path['active.md'].status == 'active', 'active doc hit must have status=active'
        assert by_path['expired.md'].status == 'expired', 'expired doc hit must have status=expired'
    finally:
        c.conn.close()
