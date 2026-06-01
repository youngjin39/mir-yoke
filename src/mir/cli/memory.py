"""``mir memory …`` — distill + query + (ADR-05 S1) self-ingest + (P50-B) render.

Phase 1 scope: insert a triple + keyword search via FTS5. Vector search
wiring happens in Step 3 once the MCP gateway lands.

ADR-05 S1 (2026-05-10) adds the ``ingest-md`` subcommand that pipes a
markdown file through ``distill.ingest_markdown_file``. The whitelist is
hard-coded to ``docs/decisions/adr-*.md`` for the spike; S5 will move the
list into config.

P50-B (2026-05-31) adds the ``render`` subcommand that projects DB contents
(ingested docs index + lesson facts) into markdown files inside
``<!-- mir:generated:start -->`` / ``<!-- mir:generated:end -->`` marker blocks.
Default is dry-run (stdout only). ``--apply`` writes the file.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from mir.core.engine.memory import distill, store

from ._common import default_db_path


# ---------------------------------------------------------------------------
# Marker constants
# ---------------------------------------------------------------------------

_MARKER_START = "<!-- mir:generated:start -->"
_MARKER_END = "<!-- mir:generated:end -->"


# ---------------------------------------------------------------------------
# Projection renderers
# ---------------------------------------------------------------------------


def _render_memory_map_section(conn) -> str:
    """Build the keyword→file index table from DB."""
    rows = distill.recall_ingested_index(conn)
    lines: list[str] = ["## Keyword → File Index (DB projection)", ""]
    lines.append("| Keyword | File | Title |")
    lines.append("|---|---|---|")
    if not rows:
        lines.append("| (no ingested documents) | — | — |")
    else:
        for row in rows:
            kws = ", ".join(row["keywords"]) if row["keywords"] else "—"
            path = row["path"] or row["slug"]
            title = row["title"] or row["slug"]
            lines.append(f"| {kws} | {path} | {title} |")
    return "\n".join(lines)


def _render_lessons_section(conn) -> str:
    """Build the Active Lessons list from DB lesson facts."""
    lessons = distill.recall_lessons(conn)
    lines: list[str] = ["## Active Lessons (DB projection)", ""]
    if not lessons:
        lines.append("- None recorded yet.")
    else:
        for lesson in lessons:
            text = lesson["text"].strip()
            slug_label = lesson["slug"]
            lines.append(f"- **{slug_label}**: {text}")
    return "\n".join(lines)


def _inject_markers(existing: str, generated_body: str) -> str:
    """Replace content inside marker block, or append a new marker block.

    Content outside the markers is preserved verbatim.
    If no markers exist, a fresh marker block is appended.
    """
    block = f"{_MARKER_START}\n{generated_body}\n{_MARKER_END}"
    if _MARKER_START in existing and _MARKER_END in existing:
        # Replace only the inner block
        before = existing[: existing.index(_MARKER_START)]
        after_marker_end = existing.index(_MARKER_END) + len(_MARKER_END)
        after = existing[after_marker_end:]
        return before + block + after
    else:
        # Append fresh marker block
        sep = "\n\n" if existing and not existing.endswith("\n\n") else "\n"
        if not existing.endswith("\n"):
            sep = "\n" + sep
        return existing + sep + block + "\n"


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mir memory")
    sub = p.add_subparsers(dest="action", required=True)

    ins = sub.add_parser("insert", help="insert a minimal triple")
    ins.add_argument("--subject", required=True)
    ins.add_argument("--predicate", required=True)
    ins.add_argument("--object", required=True, dest="obj")
    ins.add_argument("--consent", default="ephemeral",
                     choices=("ephemeral", "persistent"))
    ins.add_argument("--db", type=Path, default=None)

    q = sub.add_parser("query", help="FTS5 keyword search")
    q.add_argument("keyword")
    q.add_argument("--limit", type=int, default=10)
    q.add_argument("--db", type=Path, default=None)

    ig = sub.add_parser(
        "ingest-md",
        help="ADR-05 S1: ingest a whitelisted markdown file frontmatter",
    )
    ig.add_argument("path", type=Path,
                    help="path to a whitelisted markdown file")
    ig.add_argument("--db", type=Path, default=None)
    ig.add_argument(
        "--whitelist",
        action="append",
        default=None,
        help="override default fnmatch glob (default: docs/decisions/adr-*.md)",
    )

    rn = sub.add_parser(
        "render",
        help="P50-B: project DB contents into markdown (dry-run by default)",
    )
    rn.add_argument(
        "--target",
        choices=("memory-map", "lessons", "all"),
        default="all",
        help="which projection to render (default: all)",
    )
    rn.add_argument(
        "--output-path",
        type=Path,
        default=None,
        dest="output_path",
        help="target file path for --apply (default: none = stdout only)",
    )
    rn.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="write projection into the output file (default: dry-run stdout)",
    )
    rn.add_argument("--db", type=Path, default=None)

    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    db_path = ns.db or default_db_path()
    if not db_path.is_file():
        print(f"no memory.db at {db_path} — run `mir migrate up` first")
        return 2

    conn = store.connect(db_path)
    try:
        if ns.action == "insert":
            fid = distill.insert_triple(
                conn.conn,
                distill.Triple(
                    subject_slug=ns.subject,
                    predicate=ns.predicate,
                    object_literal=ns.obj,
                ),
                consent_scope=ns.consent,
            )
            conn.conn.commit()
            print(f"fact id={fid}")
            return 0

        if ns.action == "query":
            rows = distill.fts_search(conn.conn, ns.keyword, limit=ns.limit)
            if not rows:
                print(f"no matches for {ns.keyword!r}")
                return 0
            for fid, predicate, body in rows:
                print(f"  #{fid}  {predicate}  {body}")
            return 0

        if ns.action == "ingest-md":
            globs = (
                tuple(ns.whitelist)
                if ns.whitelist
                else distill.DEFAULT_WHITELIST
            )
            result = distill.ingest_markdown_file(
                ns.path,
                conn=conn.conn,
                whitelist_globs=globs,
            )
            if result.no_op:
                reason = result.no_op_reason or "unspecified"
                print(f"no_op[{reason}]: hash={result.file_hash[:12] or 'n/a'}…")
            else:
                print(
                    f"ingested: facts+={result.facts_inserted} "
                    f"superseded={result.facts_superseded} "
                    f"links+={result.fact_links_added} "
                    f"hash={result.file_hash[:12]}…"
                )
            return 0

        if ns.action == "render":
            return _do_render(ns, conn.conn)

    finally:
        conn.conn.close()
    return 2


def _do_render(ns: argparse.Namespace, conn) -> int:
    """Execute the render subcommand logic."""
    target = ns.target  # "memory-map", "lessons", or "all"
    apply_mode = ns.apply
    output_path: Path | None = ns.output_path

    sections: list[str] = []

    if target in ("memory-map", "all"):
        sections.append(_render_memory_map_section(conn))

    if target in ("lessons", "all"):
        sections.append(_render_lessons_section(conn))

    generated_body = "\n\n".join(sections)

    if not apply_mode:
        # Dry-run: print to stdout wrapped in markers so callers can verify
        print(f"{_MARKER_START}")
        print(generated_body)
        print(f"{_MARKER_END}")
        return 0

    # Apply mode: write to file
    if output_path is None:
        # No output path → print to stdout (same as dry-run)
        print(f"{_MARKER_START}")
        print(generated_body)
        print(f"{_MARKER_END}")
        return 0

    # Read existing content (create empty if file does not exist)
    if output_path.is_file():
        existing = output_path.read_text(encoding="utf-8")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""

    updated = _inject_markers(existing, generated_body)
    output_path.write_text(updated, encoding="utf-8")
    print(f"render applied → {output_path}")
    return 0
