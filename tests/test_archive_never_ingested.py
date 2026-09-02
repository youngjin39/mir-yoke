"""The archive tree is never ingested, whatever whitelist the caller passes.

``docs/_archive/`` holds retired records behind live pointers. Ingesting one puts
a superseded decision back into context as current authority, which is the reason
it was archived in the first place.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mir.core.engine.memory import distill, store


def _fresh_db(tmp_path: Path) -> store.Connection:
    c = store.connect(tmp_path / "memory.db", load_vec=False)
    store.apply_migrations(c.conn)
    return c


def test_matcher_refuses_the_archive_tree_under_any_whitelist() -> None:
    """The exclusion cannot live in DEFAULT_WHITELIST.

    ``mir memory ingest-md --whitelist …`` replaces the tuple wholesale, so a
    caller-supplied glob is the one reachable path into the archive. The refusal
    has to hold for globs this module never chose.
    """
    assert distill._matches_whitelist("docs/_archive/README.md", ("*",)) is False


def test_matcher_still_admits_live_docs() -> None:
    assert (
        distill._matches_whitelist(
            "docs/decisions/adr-01-external-store.md", distill.DEFAULT_WHITELIST
        )
        is True
    )
    assert (
        distill._matches_whitelist(
            "docs/harness-engineering/overview.md", distill.DEFAULT_WHITELIST
        )
        is True
    )


@pytest.mark.parametrize(
    "rel",
    [
        # The two files at the tree root are the fnmatch depth trap: an exclude
        # spelled ``docs/_archive/**/*.md`` requires a slash after _archive/ and
        # so misses exactly these.
        "docs/_archive/README.md",
        "docs/_archive/INDEX.md",
        "docs/_archive/decisions/adr-07-review-gate-2026-05-11-historical.md",
    ],
)
def test_archive_tree_is_never_ingested(tmp_path: Path, rel: str) -> None:
    c = _fresh_db(tmp_path)
    try:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "---\ntitle: archived record\nstatus: accepted\n---\nbody\n", encoding="utf-8"
        )
        result = distill.ingest_markdown_file(
            target, conn=c.conn, project_root=tmp_path, whitelist_globs=("*",)
        )
        assert result.no_op is True
        assert result.no_op_reason == "archive"
        assert result.facts_inserted == 0
        assert c.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
    finally:
        c.conn.close()
