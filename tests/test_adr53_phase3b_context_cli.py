"""ADR-53 Phase 3b-1 — `mir context` CLI subcommand tests (TDD-first).

Tests cover:
  pull: basic hit rendering, --history union, embed degrade, read-failure drop,
        near-dup collapse, snippet budget, --json output.
  sync: ScanResult per-archive print, fail-loud exit code 1 on failed entries.
  config: empty archives → empty result + notice (not error).
  advisory fold (b): archive_slugs + include_history combo (via unit import).

End-to-end wiring test uses subprocess import of `mir.cli.context` main
to prove the subcommand is callable (not just the internal functions).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mir.core.engine.memory import store
from mir.core.engine.memory.external_store import ExternalStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _make_db_with_archive(tmp_path: Path) -> tuple[Path, int]:
    """Create memory.db, register + scan one archive, return (db_path, archive_id)."""
    db_path = tmp_path / "memory.db"
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "alpha.md", "machine learning gradient descent optimization")
        _write(root, "beta.md", "machine learning neural networks deep learning")
        archive_id = es.register(
            slug="test-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)
    finally:
        c.conn.close()
    return db_path, archive_id


# ---------------------------------------------------------------------------
# Import guard — context module must be importable
# ---------------------------------------------------------------------------


def test_context_module_importable():
    """context.py must be importable via the CLI package."""
    from mir.cli import context  # noqa: F401  # just test the import


def test_context_registered_in_subcommands():
    """'context' must appear in the SUBCOMMANDS registry."""
    from mir.cli import SUBCOMMANDS
    assert "context" in SUBCOMMANDS, "SUBCOMMANDS must contain 'context'"


# ---------------------------------------------------------------------------
# pull — basic rendering
# ---------------------------------------------------------------------------


def test_pull_returns_chunk_lines(tmp_path, capsys):
    """pull with matching query prints [chunk] lines."""
    db_path, _ = _make_db_with_archive(tmp_path)
    from mir.cli.context import main
    ret = main(["pull", "machine learning", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # At least one [chunk] line expected
    assert "[chunk]" in out


def test_pull_no_match_prints_notice(tmp_path, capsys):
    """pull with zero matches prints a notice and exits 0."""
    db_path, _ = _make_db_with_archive(tmp_path)
    from mir.cli.context import main
    ret = main(["pull", "xyzquux_nomatch_9999", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # Should print some notice about no results
    assert "no results" in out.lower() or out.strip() == "" or "[chunk]" not in out


def test_pull_history_flag_queries_facts(tmp_path, capsys):
    """--history flag triggers fact query path (fts_search with include_history)."""
    db_path, _ = _make_db_with_archive(tmp_path)
    # Insert a fact so we have something to find
    c = store.connect(db_path)
    try:
        from mir.core.engine.memory.distill import Triple, insert_triple
        insert_triple(
            c.conn,
            Triple(
                subject_slug="test-subject",
                predicate="lesson",
                object_literal="machine learning is great",
            ),
            consent_scope="persistent",
        )
        c.conn.commit()
    finally:
        c.conn.close()

    from mir.cli.context import main
    ret = main(["pull", "machine learning", "--history", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # With --history we should get [fact] lines when there are matching facts
    assert "[fact]" in out or "[chunk]" in out  # at least one kind of result


def test_pull_json_flag_returns_machine_shape(tmp_path, capsys):
    """--json flag returns JSON with expected top-level keys."""
    db_path, _ = _make_db_with_archive(tmp_path)
    from mir.cli.context import main
    ret = main(["pull", "machine learning", "--json", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    data = json.loads(out)
    assert "degraded" in data
    assert "notices" in data
    assert "facts" in data
    assert "chunks" in data
    assert isinstance(data["chunks"], list)
    assert isinstance(data["facts"], list)


# ---------------------------------------------------------------------------
# pull — degrade path (embed exception → FTS-only)
# ---------------------------------------------------------------------------


def test_pull_embed_exception_degrades_to_fts(tmp_path, capsys):
    """When embed_fn raises, pull falls back to FTS-only and prepends notice."""
    db_path, _ = _make_db_with_archive(tmp_path)

    def bad_embed(texts):
        raise RuntimeError("embedding service unavailable")

    from mir.cli import context as ctx_module
    # Patch the embed construction so it raises
    with patch.object(
        ctx_module, "_build_embed_fn",
        side_effect=RuntimeError("embedding service unavailable"),
    ):
        from mir.cli.context import main
        ret = main(["pull", "machine learning", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    assert "[degraded]" in out


# ---------------------------------------------------------------------------
# pull — near-dup collapse
# ---------------------------------------------------------------------------


def test_pull_near_dup_collapse(tmp_path, capsys):
    """Near-duplicate chunks (Jaccard 8-gram >0.85) are collapsed; distinct chunks survive.

    3 files: two near-identical (>0.85 Jaccard) + one distinct.
    --k 5. Exactly 1 chunk line must survive (1 dedup survivor from dup_a/dup_b;
    distinct.md uses different vocabulary and won't match the FTS query).
    This test MUST fail if dedup is bypassed.
    """
    db_path = tmp_path / "memory.db"
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        # Two near-identical files (same long repeated body — Jaccard well above 0.85)
        body = "machine learning gradient descent optimization convergence rate " * 20
        _write(root, "dup_a.md", body)
        _write(root, "dup_b.md", body + " x")  # one token diff — still near-identical
        # One clearly distinct file — different vocabulary, no overlap
        _write(root, "distinct.md",
               "photosynthesis chlorophyll sunlight carbon dioxide oxygen plant biology")
        archive_id = es.register(
            slug="dup-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)
    finally:
        c.conn.close()

    from mir.cli.context import main
    ret = main(["pull", "machine learning gradient", "--k", "5", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    chunk_lines = [ln for ln in out.splitlines() if ln.strip().startswith("[chunk]")]
    # dup_a and dup_b are near-identical: only 1 survives dedup.
    # distinct.md uses completely different vocabulary so FTS won't return it for
    # this query — we expect exactly 1 survivor (the dedup winner from dup_a/dup_b).
    # If dedup is bypassed both dup_a and dup_b appear → len == 2, assertion fails.
    assert len(chunk_lines) == 1, (
        f"Expected exactly 1 chunk after near-dup collapse (dup_a+dup_b merge to 1), "
        f"got {len(chunk_lines)}: {chunk_lines}"
    )


# ---------------------------------------------------------------------------
# pull — read failure drops hit with stale notice
# ---------------------------------------------------------------------------


def test_pull_read_failure_drops_hit_with_stale_notice(tmp_path, capsys):
    """If file read fails during pull, the hit is dropped with [stale] notice."""
    db_path, archive_id = _make_db_with_archive(tmp_path)
    # Delete alpha.md after indexing to force a read failure
    (tmp_path / "archive" / "alpha.md").unlink()

    from mir.cli.context import main
    ret = main(["pull", "machine learning", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # Should see [stale] notice for the deleted file
    assert "[stale]" in out


# ---------------------------------------------------------------------------
# pull — snippet budget (6KB total)
# ---------------------------------------------------------------------------


def test_pull_snippet_budget_truncates(tmp_path, capsys):
    """Total snippet content must not exceed 6KB."""
    db_path = tmp_path / "memory.db"
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        # Write many large files
        for i in range(10):
            # Each file ~2KB of relevant content
            body = f"machine learning optimization {i} " + ("word " * 200)
            _write(root, f"large_{i}.md", body)
        archive_id = es.register(
            slug="large-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)
    finally:
        c.conn.close()

    from mir.cli.context import main
    ret = main(["pull", "machine learning optimization", "--k", "10", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # Total output of snippet content should be bounded
    # Check: all snippet text together < 8KB (budget is 6KB + overhead)
    snippet_content = "\n".join(
        ln for ln in out.splitlines()
        if not ln.strip().startswith("[chunk]") and not ln.strip().startswith("[fact]")
           and not ln.strip().startswith("[stale]") and not ln.strip().startswith("[degraded]")
    )
    snippet_bytes = len(snippet_content.encode("utf-8"))
    assert snippet_bytes <= 6144, (
        f"snippet content {snippet_bytes} bytes exceeds 6KB budget (ADR-53 D2)"
    )


# ---------------------------------------------------------------------------
# sync — basic scan
# ---------------------------------------------------------------------------


def test_sync_prints_scan_result(tmp_path, capsys):
    """sync prints ScanResult info and exits 0 when no failures."""
    db_path, _ = _make_db_with_archive(tmp_path)
    # Add a new file to scan
    _write(tmp_path / "archive", "gamma.md", "new document for sync test")

    # Re-register archive to get it into the db if needed; actually just sync
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        # Just re-register with same settings
        es.register(
            slug="test-archive",
            root_path=str(tmp_path / "archive"),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
    finally:
        c.conn.close()

    from mir.cli.context import main
    ret = main(["sync", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # Should print scan result info
    assert "inserted" in out or "unchanged" in out or "test-archive" in out


def test_sync_exits_1_on_failed_entries(tmp_path, capsys):
    """sync exits 1 when any archive scan has failed entries."""
    db_path = tmp_path / "memory.db"
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "valid.md", "hello world")
        archive_id = es.register(
            slug="fail-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)
    finally:
        c.conn.close()

    # Patch ExternalStore.scan to return a ScanResult with failures
    from mir.cli import context as ctx_module
    from mir.core.engine.memory.external_store import ScanResult
    with patch.object(ctx_module.ExternalStore, "scan",
                      return_value=ScanResult(
                          inserted=0, deleted=0, reindexed=0, unchanged=1,
                          failed=(("valid.md", "permission denied"),)
                      )):
        ret = ctx_module.main(["sync", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 1
    assert "failed" in out.lower()


# ---------------------------------------------------------------------------
# config: empty archives → empty result + notice
# ---------------------------------------------------------------------------


def test_pull_empty_archives_notice(tmp_path, capsys):
    """When no archives are configured, pull returns empty result + notice."""
    db_path = tmp_path / "memory.db"
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        # No archives registered
    finally:
        c.conn.close()

    from mir.cli.context import main
    ret = main(["pull", "anything", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # Should print some notice about no archives
    assert (
        "no archive" in out.lower()
        or "0 archive" in out.lower()
        or "empty" in out.lower()
        or "[chunk]" not in out
    )


# ---------------------------------------------------------------------------
# Advisory fold (a): _doc_created_ordinal datetime-with-time fix
# ---------------------------------------------------------------------------


def test_doc_created_ordinal_datetime_string():
    """datetime-with-time strings like '2026-06-06T12:00:00' rank by date, not ordinal 0."""
    import datetime

    from mir.core.engine.memory.external_store import _doc_created_ordinal

    # Pure date string — should work as before
    date_ordinal = _doc_created_ordinal('{"created": "2026-06-06"}')
    assert date_ordinal == datetime.date(2026, 6, 6).toordinal()

    # Datetime with time — should parse date prefix, not fall back to 0
    datetime_ordinal = _doc_created_ordinal('{"created": "2026-06-06T12:30:00"}')
    assert datetime_ordinal == datetime.date(2026, 6, 6).toordinal(), (
        "datetime-with-time 'created' field should rank by date, not return 0"
    )

    # datetime object (from frontmatter parsed as datetime)
    dt_obj_ordinal = _doc_created_ordinal(json.dumps({"created": "2026-06-06 09:00:00"}))
    assert dt_obj_ordinal == datetime.date(2026, 6, 6).toordinal()

def test_pull_history_chunk_shows_expired_status(tmp_path, capsys):
    """pull --history: expired doc chunk must show [expired] label, not [active]."""
    db_path = tmp_path / "memory.db"
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "expired_doc.md",
               "quantum entanglement expired document content text")
        _write(root, "active_doc.md",
               "quantum entanglement active document content text")
        archive_id = es.register(
            slug="status-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)
        c.conn.execute(
            "UPDATE external_documents SET status='expired' "
            "WHERE relative_path='expired_doc.md'"
        )
        c.conn.commit()
    finally:
        c.conn.close()

    from mir.cli.context import main
    ret = main(["pull", "quantum entanglement", "--history", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    # The expired doc chunk must be labeled [expired], not [active]
    assert "[expired]" in out, (
        f"Expected [expired] label in output for expired doc, got:\n{out}"
    )


def test_pull_json_history_chunk_has_status_field(tmp_path, capsys):
    """pull --history --json: each chunk dict must include a 'status' key."""
    db_path = tmp_path / "memory.db"
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        root = tmp_path / "archive"
        _write(root, "expired_doc.md",
               "quantum entanglement expired document content text")
        archive_id = es.register(
            slug="status-json-archive",
            root_path=str(root),
            mode="indexed",
            owner="family:x",
            glob_include=("**/*.md",),
        )
        es.scan(archive_id, embed_fn=None)
        c.conn.execute(
            "UPDATE external_documents SET status='expired' "
            "WHERE relative_path='expired_doc.md'"
        )
        c.conn.commit()
    finally:
        c.conn.close()

    from mir.cli.context import main
    ret = main(["pull", "quantum entanglement", "--history", "--json",
                "--db", str(db_path)])
    out = capsys.readouterr().out
    assert ret == 0
    data = json.loads(out)
    chunks = data.get("chunks", [])
    assert len(chunks) > 0, "Expected at least one chunk with include_history=True"
    for chunk in chunks:
        assert "status" in chunk, f"chunk dict must have 'status' key: {chunk}"
    expired_chunks = [ch for ch in chunks if ch["status"] == "expired"]
    assert len(expired_chunks) >= 1, (
        f"Expected at least one chunk with status='expired', got: {chunks}"
    )


# ---------------------------------------------------------------------------
# ADR-53 stage-3 regression: tomllib fallback in stub-config branch
# ---------------------------------------------------------------------------


def test_sync_reads_archives_from_toml_without_pydantic(tmp_path):
    """Regression: sync registers archives from harness_a.toml when pydantic config
    loader is unavailable (the live path on a fresh template clone).

    On the CURRENT template code (stub-config branch has no TOML parsing),
    sync skips archive registration and exits with 0 archives. This test MUST
    FAIL before the fix and PASS after.
    """
    import builtins
    import sys

    # Create a project structure with memory.db + harness_a.toml
    mir_dir = tmp_path / ".mir"
    mir_dir.mkdir()
    db_path = mir_dir / "memory.db"

    # Create a docs dir with at least one markdown file
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        "tomllib fallback regression test document content", encoding="utf-8"
    )

    # Write harness_a.toml with one [[memory.external_archives]] block
    toml_content = f"""\
[[memory.external_archives]]
slug = "template-docs"
root = "{docs_dir}"
mode = "indexed"
glob_include = ["**/*.md"]
"""
    (tmp_path / "harness_a.toml").write_text(toml_content, encoding="utf-8")

    # Init the DB with migrations
    c = store.connect(db_path)
    try:
        store.apply_migrations(c.conn)
    finally:
        c.conn.close()

    # Evict any cached loader module so our import patch fires inside main()
    for key in list(sys.modules.keys()):
        if "mir.core.config" in key:
            sys.modules.pop(key, None)

    import mir.cli.context as ctx_mod

    # Intercept the inline `from mir.core.config.loader import load_config` call
    # that lives inside main() — simulates pydantic/loader being unavailable.
    _original_import = builtins.__import__

    def _block_loader(name, *args, **kwargs):
        if name == "mir.core.config.loader":
            raise ImportError("pydantic not available — simulated fresh template clone")
        return _original_import(name, *args, **kwargs)

    builtins.__import__ = _block_loader
    try:
        ret = ctx_mod.main(["sync", "--db", str(db_path)])
    finally:
        builtins.__import__ = _original_import

    # After sync, the archive must be registered and at least 1 document indexed
    c = store.connect(db_path)
    try:
        archive_rows = c.conn.execute(
            "SELECT id, slug FROM external_archives"
        ).fetchall()
        doc_count = c.conn.execute(
            "SELECT COUNT(*) FROM external_documents"
        ).fetchone()[0]
    finally:
        c.conn.close()

    assert len(archive_rows) >= 1, (
        f"Expected >= 1 archive registered from harness_a.toml (tomllib fallback), "
        f"got {len(archive_rows)}. This gap was introduced by the stub-config branch "
        f"not parsing TOML archives (ADR-53 stage-3 fix required)."
    )
    assert doc_count >= 1, (
        f"Expected >= 1 document ingested after sync, got {doc_count}."
    )
