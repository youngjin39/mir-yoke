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
import json
import re
import uuid
from pathlib import Path

from mir.core.config.loader import (
    ConfigLoadError,
    load_config,
    resolve_archive_root,
    resolve_memory_db,
)
from mir.core.engine.memory import distill, store
from mir.core.engine.memory.external_store import CURRENT_METADATA_VERSION

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
    ins.add_argument("--consent", default="ephemeral", choices=("ephemeral", "persistent"))
    ins.add_argument("--db", type=Path, default=None)

    q = sub.add_parser("query", help="FTS5 keyword search")
    q.add_argument("keyword")
    q.add_argument("--limit", type=int, default=10)
    q.add_argument(
        "--history",
        action="store_true",
        default=False,
        help="include expired and superseded facts",
    )
    q.add_argument("--db", type=Path, default=None)

    ig = sub.add_parser(
        "ingest-md",
        help="ADR-05 S1: ingest a whitelisted markdown file frontmatter",
    )
    ig.add_argument("path", type=Path, help="path to a whitelisted markdown file")
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

    rc = sub.add_parser(
        "reconcile-missing",
        help="B2-FOLLOWUP: expire active facts whose source doc no longer exists",
    )
    rc.add_argument(
        "--project-root",
        type=Path,
        default=None,
        dest="project_root",
        help="project root for relative path resolution (default: cwd)",
    )
    rc.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="report count without writing any rows",
    )
    rc.add_argument("--db", type=Path, default=None)

    doc = sub.add_parser("doctor", help="verify the required memory baseline")
    doc.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        dest="project_root",
        help="repository root containing harness_a.toml (default: cwd)",
    )
    doc.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json",
        help="emit machine-readable evidence",
    )

    gc = sub.add_parser("gc", help="expire facts whose valid_to date has passed")
    gc.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="apply expiry updates (default: dry-run)",
    )
    gc.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json",
        help="emit machine-readable counts",
    )
    gc.add_argument("--db", type=Path, default=None)

    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    if ns.action == "doctor":
        code, report = run_doctor(ns.project_root)
        if ns.json:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        else:
            print(f"memory doctor: {report['status']}")
            for error in report["errors"]:
                print(f"  [not-ready] {error}")
            if not report["errors"]:
                print(f"  db: {report['memory']['db_path']}")
                print(f"  schema: {report['memory']['schema_version']}")
                print(f"  archives: {report['memory']['archives_registered']}")
                print(f"  vector: {report['vector']['status']}")
        return code

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
            rows = distill.fts_search(
                conn.conn,
                ns.keyword,
                limit=ns.limit,
                include_history=ns.history,
            )
            if not rows:
                print(f"no matches for {ns.keyword!r}")
                return 0
            if ns.history:
                placeholders = ",".join("?" * len(rows))
                status_map = {
                    int(fid): status
                    for fid, status in conn.conn.execute(
                        f"SELECT id, status FROM facts WHERE id IN ({placeholders})",
                        [fid for fid, _, _ in rows],
                    ).fetchall()
                }
                for fid, predicate, body in rows:
                    status = status_map.get(fid) or "unknown"
                    print(f"  #{fid}  [{status}]  {predicate}  {body}")
            else:
                for fid, predicate, body in rows:
                    print(f"  #{fid}  {predicate}  {body}")
            return 0

        if ns.action == "gc":
            result = store.gc_scan(conn.conn, dry_run=not ns.apply)
            payload = {"applied": ns.apply, **result}
            if ns.json:
                print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            elif ns.apply:
                print(f"expired={result['expired']} kept_active={result['kept_active']}")
            else:
                print(
                    f"dry_run: would_expire={result['expired']} kept_active={result['kept_active']}"
                )
            return 0

        if ns.action == "ingest-md":
            globs = tuple(ns.whitelist) if ns.whitelist else distill.DEFAULT_WHITELIST
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
        if ns.action == "reconcile-missing":
            from mir.core.engine.memory.distill import reconcile_missing_source

            count = reconcile_missing_source(
                conn.conn,
                project_root=ns.project_root,
                dry_run=ns.dry_run,
            )
            if ns.dry_run:
                print(f"dry_run: would_expire={count}")
            else:
                print(f"expired={count}")
            return 0

    finally:
        conn.conn.close()
    return 2


_REQUIRED_MEMORY_OBJECTS = {
    "schema_migrations",
    "entities",
    "facts",
    "facts_fts",
    "external_archives",
    "external_documents",
    "external_chunks",
    "external_chunks_fts",
    "external_store_meta",
}


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def run_doctor(project_root: Path, *, db_override: Path | None = None) -> tuple[int, dict]:
    """Inspect memory readiness without creating a missing database.

    Exit classification mirrors the CLI: 0 ready, 1 operationally not ready,
    2 invalid configuration or project-root arguments.
    """
    root = project_root.expanduser().resolve(strict=False)
    report: dict = {
        "status": "not_ready",
        "errors": [],
        "memory": {
            "required": True,
            "backend": "unknown",
            "db_path": ".mir/memory.db",
            "integrity": "not_checked",
            "schema_version": None,
            "latest_schema_version": store.latest_schema_version(),
            "fts5": "not_checked",
            "round_trip": "not_checked",
            "archives_configured": 0,
            "archives_registered": 0,
            "archives_synced": 0,
        },
        "vector": {
            "mode": "off",
            "sqlite_vec": "not_checked",
            "embedding": "disabled",
            "status": "off",
        },
    }
    if not root.is_dir():
        report["errors"].append(f"project root is not a directory: {root}")
        return 2, report
    if not (root / "harness_a.toml").is_file():
        report["errors"].append("active harness_a.toml is missing")
        return 2, report
    try:
        cfg = load_config(root)
    except ConfigLoadError as exc:
        report["errors"].append(str(exc))
        return 2, report

    memory = report["memory"]
    vector = report["vector"]
    memory["required"] = cfg.memory.required
    memory["backend"] = cfg.memory.backend
    memory["archives_configured"] = len(cfg.memory.external_archives)
    vector["mode"] = cfg.memory.vector_mode

    if not cfg.memory.enabled or not cfg.memory.required:
        report["errors"].append("portable baseline requires memory enabled=true and required=true")
    if not cfg.memory.external_archives:
        report["errors"].append("at least one external archive must be configured")
    for archive in cfg.memory.external_archives:
        archive_root = resolve_archive_root(root, archive)
        if not archive_root.is_dir():
            report["errors"].append(
                f"configured archive root is missing: {archive.slug!r} ({archive_root})"
            )

    configured_db_path = resolve_memory_db(root, cfg)
    db_path = db_override or configured_db_path
    memory["db_path"] = _relative_or_absolute(configured_db_path, root)
    if not db_path.is_file():
        report["errors"].append(f"memory database is missing: {db_path}")
        return 1, report

    connection = None
    embedding_backend = None
    try:
        connection = store.connect(db_path)
        conn = connection.conn
        vector["sqlite_vec"] = "available" if connection.vec_available else "unavailable"

        integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
        integrity = ", ".join(str(row[0]) for row in integrity_rows)
        memory["integrity"] = integrity
        if integrity_rows != [("ok",)]:
            report["errors"].append(f"SQLite integrity_check failed: {integrity}")

        actual_version = store.schema_version(conn)
        latest_version = store.latest_schema_version()
        memory["schema_version"] = actual_version
        if actual_version != latest_version:
            report["errors"].append(
                f"schema version {actual_version!r} is not latest {latest_version!r}"
            )

        objects = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
        missing_objects = sorted(_REQUIRED_MEMORY_OBJECTS - objects)
        if missing_objects:
            report["errors"].append(
                "required memory tables are missing: " + ", ".join(missing_objects)
            )
        else:
            memory["fts5"] = "ok"

        if not missing_objects:
            probe_token = f"mirdoctor{uuid.uuid4().hex}"
            try:
                conn.execute("BEGIN")
                distill.insert_triple(
                    conn,
                    distill.Triple(
                        subject_slug="mir-memory-doctor",
                        predicate="doctor_probe",
                        object_literal=probe_token,
                    ),
                )
                matches = distill.fts_search(conn, probe_token, limit=1)
                if not matches:
                    raise RuntimeError("inserted fact was not returned by FTS5")
                memory["round_trip"] = "ok"
            except Exception as exc:
                memory["round_trip"] = "failed"
                report["errors"].append(f"rollback-only FTS5 probe failed: {exc}")
            finally:
                conn.rollback()

        archive_rows = conn.execute(
            "SELECT id, slug, root_path, last_scanned_at FROM external_archives"
        ).fetchall()
        memory["archives_registered"] = len(archive_rows)
        if not archive_rows:
            report["errors"].append("no external archives are registered")
        registered = {row[1]: row for row in archive_rows}
        synced = 0
        for archive in cfg.memory.external_archives:
            row = registered.get(archive.slug)
            if row is None:
                report["errors"].append(f"configured archive is not registered: {archive.slug!r}")
                continue
            expected_root = resolve_archive_root(root, archive)
            actual_root = Path(row[2]).resolve(strict=False)
            if actual_root != expected_root:
                report["errors"].append(
                    f"archive root drift for {archive.slug!r}: {actual_root} != {expected_root}"
                )
            metadata = conn.execute(
                "SELECT value FROM external_store_meta WHERE key = ?",
                (f"schema_metadata_version:archive:{row[0]}",),
            ).fetchone()
            if row[3] is None or metadata is None or metadata[0] != CURRENT_METADATA_VERSION:
                report["errors"].append(
                    f"archive has no successful current sync evidence: {archive.slug!r}"
                )
            else:
                synced += 1
        memory["archives_synced"] = synced

        document_count = conn.execute("SELECT COUNT(*) FROM external_documents").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM external_chunks").fetchone()[0]
        memory["documents_indexed"] = document_count
        memory["chunks_indexed"] = chunk_count
        memory["archive_fts_probe"] = "not_checked"
        if document_count < 1 or chunk_count < 1:
            report["errors"].append("archive sync produced no searchable documents/chunks")
        else:
            sample = conn.execute(
                "SELECT a.root_path, d.relative_path, c.byte_start, c.byte_end "
                "FROM external_chunks c "
                "JOIN external_documents d ON d.id = c.document_id "
                "JOIN external_archives a ON a.id = d.archive_id "
                "ORDER BY c.id LIMIT 1"
            ).fetchone()
            try:
                snippet = (
                    (Path(sample[0]) / sample[1])
                    .read_bytes()[sample[2] : sample[3]]
                    .decode("utf-8")
                )
                tokens = [
                    token
                    for token in re.findall(r"[A-Za-z0-9_\u00C0-\uFFFF]+", snippet)
                    if len(token) >= 6
                ]
                if not tokens:
                    raise RuntimeError("indexed sample contains no stable probe token")
                probe_query = distill.sanitize_fts_query(tokens[0])
                probe_row = conn.execute(
                    "SELECT c.id FROM external_chunks_fts f "
                    "JOIN external_chunks c ON c.id = f.rowid "
                    "WHERE external_chunks_fts MATCH ? LIMIT 1",
                    (probe_query,),
                ).fetchone()
                if probe_row is None:
                    raise RuntimeError("indexed archive token was not returned by FTS5")
                memory["archive_fts_probe"] = "ok"
            except Exception as exc:
                memory["archive_fts_probe"] = "failed"
                report["errors"].append(f"archive FTS5 probe failed: {exc}")

        if cfg.memory.embedding.enabled:
            try:
                from mir.core.engine.memory.backends.omlx_http import from_config

                embedding_backend = from_config(cfg.memory.embedding)
                embedding_backend.encode(["mir memory doctor"])
                vector["embedding"] = "ready"
            except Exception as exc:
                vector["embedding"] = "unavailable"
                vector["embedding_reason"] = str(exc)
                if cfg.memory.embedding.required or cfg.memory.vector_mode == "required":
                    report["errors"].append(f"required embedding backend is unavailable: {exc}")

        if cfg.memory.vector_mode == "required" and not connection.vec_available:
            report["errors"].append(
                f"required sqlite-vec is unavailable: {connection.vec_reason or 'unknown reason'}"
            )
        if cfg.memory.vector_mode == "required" and connection.vec_available:
            unindexed_documents = conn.execute(
                "SELECT COUNT(*) FROM external_documents WHERE vec_indexed_at IS NULL"
            ).fetchone()[0]
            vector_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'external_chunks_vec'"
            ).fetchone()
            vector["documents_missing_vectors"] = unindexed_documents
            if vector_table is None:
                vector["chunk_rows"] = 0
                report["errors"].append("required external_chunks_vec table is missing")
            else:
                vector_rows = conn.execute("SELECT COUNT(*) FROM external_chunks_vec").fetchone()[0]
                vector["chunk_rows"] = vector_rows
                if vector_rows != chunk_count:
                    report["errors"].append(
                        f"vector row count {vector_rows} does not match chunk count {chunk_count}"
                    )
            if unindexed_documents:
                report["errors"].append(
                    f"{unindexed_documents} external documents have no vector index evidence"
                )
        if cfg.memory.vector_mode == "off":
            vector["status"] = "off"
        elif connection.vec_available and vector["embedding"] == "ready":
            vector["status"] = "ready"
        else:
            vector["status"] = "unavailable"
    except Exception as exc:
        report["errors"].append(f"memory doctor operational failure: {exc}")
    finally:
        if embedding_backend is not None:
            embedding_backend.close()
        if connection is not None:
            connection.conn.close()

    if not report["errors"]:
        report["status"] = "ready"
        return 0, report
    return 1, report


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
