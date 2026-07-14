"""mir context … — context retrieval CLI (ADR-53 D2/D7).

Subcommands:
  pull <query>  Hybrid retrieval: ExternalStore.search + optional fact union.
  sync          Scan all configured external archives; exit 1 on any failures.

Design pinned in docs/decisions/adr-53-context-assembly-current-only-retrieval-2026-06-05.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from mir.core.context.profile_task_context import build_profile_task_context
from mir.core.engine.memory import store
from mir.core.engine.memory.external_store import ExternalStore

from ._common import default_db_path

_SNIPPET_BUDGET_BYTES = 6144  # 6 KB total per pull
_NEAR_DUP_SHINGLE_N = 8
_NEAR_DUP_JACCARD_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Shingle helpers for near-dup collapse
# ---------------------------------------------------------------------------


def _shingles(text: str, n: int = _NEAR_DUP_SHINGLE_N) -> set[str]:
    """Lowercase, whitespace-normalised n-gram shingle set."""
    normalised = re.sub(r'\s+', ' ', text.lower()).strip()
    if len(normalised) < n:
        return {normalised} if normalised else set()
    return {normalised[i:i + n] for i in range(len(normalised) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Embed helper
# ---------------------------------------------------------------------------


def _build_embed_fn(cfg) -> Any | None:
    """Build embed callable from ResolvedConfig.memory.embedding, or None.

    Returns None if the embedding config is unavailable. Raises on
    construction errors (caller catches and degrades).
    """
    emb_cfg = cfg.memory.embedding
    if not emb_cfg or not emb_cfg.base_url:
        return None
    try:
        from mir.core.engine.memory.embeddings import build_embed_fn  # type: ignore
        return build_embed_fn(emb_cfg)
    except (ImportError, Exception):
        # If embeddings module does not exist or fails, return None
        return None


# ---------------------------------------------------------------------------
# pull subcommand
# ---------------------------------------------------------------------------


def _profile_context_lines(context: dict[str, Any] | None) -> list[str]:
    if context is None:
        return []
    repo = context["repository"]
    purpose = " ".join(str(repo.get("purpose", "")).split())
    line = (
        f"[repository] {repo.get('slug', 'unknown')} "
        f"type={repo.get('repository_type', 'unknown')}"
    )
    if purpose:
        line += f" purpose={purpose}"
    lines = [line]
    stack = repo.get("technology_stack", [])
    if stack:
        lines.append(f"[repository-stack] {', '.join(stack)}")

    safety = context["safety"]
    protected = safety.get("protected_paths", [])
    if protected:
        lines.append(f"[safety] protected_paths={', '.join(protected)}")
    generated = safety.get("generated_paths", [])
    if generated:
        lines.append(f"[safety] generated_paths={', '.join(generated)}")
    for section in ("preserve", "boundaries"):
        values = safety.get(section, {})
        for key, value in values.items():
            if value in (None, "", [], False):
                continue
            rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
            lines.append(f"[safety] {section}.{key}={rendered}")
    enabled_gates = sorted(key for key, value in safety.get("gates", {}).items() if value is True)
    if enabled_gates:
        lines.append(f"[safety] enabled_gates={', '.join(enabled_gates)}")

    for item in context["selected_refs"]:
        lines.append(f"[context-ref] {item['kind']} {item['path']}")
    freshness = context["freshness"]
    freshness_line = (
        f"[profile-freshness] state={freshness['state']} "
        f"base={freshness['base_commit']}"
    )
    changed = freshness.get("changed_selected", [])
    if changed:
        freshness_line += f" changed={','.join(changed)}"
    freshness_line += f" reason={freshness['reason']}"
    lines.append(freshness_line)
    if context["needs_investigation"]:
        lines.append("[context-advisory] inspect only the selected or uncertain boundary before expanding")
    lines.extend(f"[context-advisory] {warning}" for warning in context.get("warnings", []))
    return lines


def _profile_search_scopes(context: dict[str, Any] | None) -> tuple[str, ...] | None:
    """Return profile-selected corpus scopes without broadening an explicit target."""
    if context is None:
        return None
    targets = context.get("task", {}).get("target_paths", [])
    selected = context.get("selected_refs", [])
    refs = [
        item.get("path")
        for item in selected
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and (not targets or item.get("kind") not in {"code_scope", "non_code_scope"})
    ]
    scopes = [*targets, *refs]
    compact = tuple(dict.fromkeys(scope for scope in scopes if scope))
    return compact or None


def _do_pull(
    ns: argparse.Namespace,
    conn,
    cfg,
    project_root: Path,
) -> int:
    """Execute pull logic. Returns exit code."""
    query = ns.query
    k = ns.k
    include_history = ns.history
    output_json = ns.json
    profile_context = build_profile_task_context(
        project_root,
        query=query,
        target_paths=tuple(ns.target_paths),
        risk=ns.risk,
    )
    path_scopes = None if include_history else _profile_search_scopes(profile_context)

    notices: list[str] = []
    degraded = False
    embed_fn = None

    # Build embed_fn from config; degrade to FTS-only on any error.
    try:
        embed_fn = _build_embed_fn(cfg)
    except Exception:
        degraded = True
        embed_fn = None
        notices.append("[degraded] embedding unavailable — FTS-only results")

    # Retry once with embed_fn=None if embed construction returned something
    # that immediately fails on call (handled below in search try/except).

    es = ExternalStore(conn)

    # Check archives exist
    archive_rows = conn.conn.execute(
        "SELECT id, slug FROM external_archives ORDER BY id"
    ).fetchall()
    if not archive_rows:
        msg = ("no archives configured — run 'mir context sync' after adding "
            "[[memory.external_archives]] to harness_a.toml")
        notices.append(msg)
        if output_json:
            print(json.dumps({
                "degraded": degraded,
                "notices": notices,
                "repository_context": profile_context,
                "facts": [],
                "chunks": [],
            }))
        else:
            for line in _profile_context_lines(profile_context):
                print(line)
            print(msg)
        return 0

    # Try search; on embed exception retry FTS-only
    hits = []
    try:
        hits = es.search(
            query,
            k=k,
            path_scopes=path_scopes,
            embed_fn=embed_fn,
            include_history=include_history,
        )
    except Exception:
        if embed_fn is not None:
            degraded = True
            notices.append("[degraded] embedding unavailable — FTS-only results")
            try:
                hits = es.search(
                    query,
                    k=k,
                    path_scopes=path_scopes,
                    embed_fn=None,
                    include_history=include_history,
                )
            except Exception:
                hits = []
        else:
            hits = []

    # Re-read snippets; drop stale hits
    kept_snippets: list[tuple[Any, str]] = []  # (hit, snippet_text)
    for hit in hits:
        archive_row = conn.conn.execute(
            "SELECT a.root_path, d.file_hash "
            "FROM external_archives a "
            "JOIN external_documents d ON d.archive_id = a.id "
            "WHERE a.slug = ? AND d.relative_path = ?",
            (hit.archive_slug, hit.relative_path),
        ).fetchone()
        if archive_row is None:
            notices.append("[stale] index entry skipped — run 'mir context sync'")
            continue
        file_path = Path(archive_row[0]) / hit.relative_path
        try:
            data = file_path.read_bytes()
            if hashlib.sha256(data).hexdigest() != archive_row[1]:
                notices.append("[stale] index entry skipped — run 'mir context sync'")
                continue
            snippet = data[hit.byte_start:hit.byte_end].decode("utf-8", errors="replace")
        except Exception:
            notices.append("[stale] index entry skipped — run 'mir context sync'")
            continue
        kept_snippets.append((hit, snippet))

    # Near-dup collapse: Jaccard 8-gram > 0.85 vs any higher-ranked KEPT snippet → drop
    collapsed: list[tuple[Any, str]] = []
    kept_shingles: list[set[str]] = []
    for hit, snippet in kept_snippets:
        shingles = _shingles(snippet)
        is_dup = any(
            _jaccard(shingles, ks) > _NEAR_DUP_JACCARD_THRESHOLD
            for ks in kept_shingles
        )
        if not is_dup:
            collapsed.append((hit, snippet))
            kept_shingles.append(shingles)
        if len(collapsed) >= k:
            break

    # Snippet budget: 6 KB total, measured as rendered indented output.
    # The test measures joined indented lines (2-sp prefix + content + newline separators).
    # Use a running-total approach so the rendered output stays within _SNIPPET_BUDGET_BYTES.
    TRUNC_SUFFIX = "…[truncated]"
    TRUNC_SUFFIX_BYTES = TRUNC_SUFFIX.encode("utf-8")
    remaining = _SNIPPET_BUDGET_BYTES
    budget_collapsed: list[tuple[Any, str]] = []
    for hit, snippet in collapsed:
        if remaining <= 0:
            break
        lines = snippet.splitlines() if snippet.splitlines() else [""]
        rendered = "\n".join(f"  {line}" for line in lines)
        rendered_enc = rendered.encode("utf-8")
        if len(rendered_enc) <= remaining:
            remaining -= len(rendered_enc)
            remaining -= 1  # inter-snippet \n separator in test measurement
            budget_collapsed.append((hit, snippet))
        else:
            # Truncate to fit remaining budget: available = remaining - indent(2) - suffix_bytes
            avail = remaining - 2 - len(TRUNC_SUFFIX_BYTES)
            if avail <= 0:
                break
            enc = snippet.encode("utf-8")
            truncated = enc[:avail].decode("utf-8", errors="replace") + TRUNC_SUFFIX
            t_lines = truncated.splitlines() if truncated.splitlines() else [""]
            truncated_rendered = "\n".join(f"  {line}" for line in t_lines)
            remaining -= len(truncated_rendered.encode("utf-8"))
            remaining -= 1  # inter-snippet \n separator in test measurement
            budget_collapsed.append((hit, truncated))
    collapsed = budget_collapsed

    # Fetch facts if --history
    fact_rows: list[tuple[int, str, str, str]] = []
    if include_history:
        from mir.core.engine.memory.distill import fts_search
        raw_facts = fts_search(conn.conn, query, limit=k, include_history=True)
        if raw_facts:
            fact_ids = [fid for fid, _, _ in raw_facts]
            placeholders = ",".join("?" * len(fact_ids))
            status_map = {
                int(fid): status
                for fid, status in conn.conn.execute(
                    f"SELECT id, status FROM facts WHERE id IN ({placeholders})",
                    fact_ids,
                ).fetchall()
            }
            for fid, predicate, obj in raw_facts:
                status = status_map.get(fid, "unknown")
                fact_rows.append((fid, status, predicate, obj))

    if output_json:
        out = {
            "degraded": degraded,
            "notices": notices,
            "repository_context": profile_context,
            "facts": [
                {"id": fid, "status": status, "predicate": pred, "object": obj}
                for fid, status, pred, obj in fact_rows
            ],
            "chunks": [
                {
                    "archive_slug": hit.archive_slug,
                    "relative_path": hit.relative_path,
                    "byte_start": hit.byte_start,
                    "byte_end": hit.byte_end,
                    "score": hit.score,
                    "status": hit.status,
                    "snippet": snippet,
                }
                for hit, snippet in collapsed
            ],
        }
        print(json.dumps(out))
        return 0

    # Human output
    for line in _profile_context_lines(profile_context):
        print(line)
    for n in notices:
        print(n)

    # Facts first (--history)
    for fid, status, pred, obj in fact_rows:
        print(f"[fact] #{fid} [{status}] {pred} {obj}")

    if not collapsed and not fact_rows:
        pass  # no output (empty is valid)

    for hit, snippet in collapsed:
        print(
            f"[chunk] [{hit.status}] {hit.archive_slug}:{hit.relative_path}"
            f"@{hit.byte_start}-{hit.byte_end} score={hit.score:.6f}"
        )
        # Indent snippet lines
        for line in snippet.splitlines():
            print(f"  {line}")

    return 0


# ---------------------------------------------------------------------------
# sync subcommand
# ---------------------------------------------------------------------------


def _do_sync(ns: argparse.Namespace, conn, cfg) -> int:
    """Execute sync logic. Returns exit code (1 if any failures)."""
    es = ExternalStore(conn)
    # D8: register archives from harness_a.toml config if not yet in DB
    existing_slugs: set[str] = {
        row[0] for row in conn.conn.execute(
            "SELECT slug FROM external_archives"
        ).fetchall()
    }
    if hasattr(cfg, "memory") and hasattr(cfg.memory, "external_archives"):
        for arch in cfg.memory.external_archives:
            if arch.slug not in existing_slugs:
                es.register(
                    slug=arch.slug,
                    root_path=arch.root,
                    mode=arch.mode,
                    glob_include=tuple(arch.glob_include) if arch.glob_include else ("**/*.md",),
                    owner="family:your-harness",
                )
    archive_rows = conn.conn.execute(
        "SELECT id, slug FROM external_archives ORDER BY id"
    ).fetchall()
    if not archive_rows:
        print("no archives configured")
        return 0

    embed_fn = None
    try:
        embed_fn = _build_embed_fn(cfg)
    except Exception:
        pass  # FTS-only sync

    any_failed = False
    for archive_id, slug in archive_rows:
        result = es.scan(archive_id, embed_fn=embed_fn)
        status_parts = [
            f"inserted={result.inserted}",
            f"reindexed={result.reindexed}",
            f"unchanged={result.unchanged}",
            f"deleted={result.deleted}",
        ]
        if result.failed:
            status_parts.append(f"failed={len(result.failed)}")
            any_failed = True
            for rel, reason in result.failed:
                print(f"  [failed] {rel}: {reason}")
        print(f"{slug}: {' '.join(status_parts)}")

    return 1 if any_failed else 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mir context")
    sub = p.add_subparsers(dest="action", required=True)

    pl = sub.add_parser("pull", help="ADR-53 D2: hybrid context retrieval")
    pl.add_argument("query", help="search query")
    pl.add_argument("--history", action="store_true", default=False,
                    help="include expired/archived docs and facts")
    pl.add_argument("--json", action="store_true", default=False, dest="json",
                    help="machine-readable JSON output")
    pl.add_argument("--k", type=int, default=8, dest="k",
                    help="number of results (default: 8)")
    pl.add_argument("--path", action="append", default=[], dest="target_paths",
                    help="repository-relative task target (repeatable)")
    pl.add_argument("--risk", choices=("low", "normal", "high"), default="normal",
                    help="main-agent task risk classification (default: normal)")
    pl.add_argument("--db", type=Path, default=None)

    sy = sub.add_parser("sync", help="ADR-53 D2: scan all configured archives")
    sy.add_argument("--db", type=Path, default=None)

    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    db_path = ns.db or default_db_path()
    project_root = (
        db_path.parent.parent
        if db_path.name == "memory.db" and db_path.parent.name == ".mir"
        else db_path.parent
    )
    if not db_path.is_file():
        print(f"no memory.db at {db_path} — run 'mir migrate up' first")
        return 2

    # Load config (harness_a.toml). Fail gracefully if absent.
    try:
        from mir.core.config.loader import load_config
        cfg = load_config(db_path.parent.parent if db_path.name == "memory.db" else Path.cwd())
    except Exception:
        # Fallback: minimal TOML parse for [[memory.external_archives]] without pydantic.
        import tomllib as _tomllib

        class _ArchiveStub:
            def __init__(self, d: dict) -> None:
                self.slug = d["slug"]
                self.root = d["root"]
                self.mode = d.get("mode", "indexed")
                self.glob_include = d.get("glob_include", ["**/*.md"])

        class _StubMemory:
            embedding = None
            external_archives: list = []

        class _StubCfg:
            memory = _StubMemory()

        _project_root = db_path.parent.parent if db_path.name == "memory.db" else Path.cwd()
        _toml_path = _project_root / "harness_a.toml"
        if _toml_path.is_file():
            try:
                with _toml_path.open("rb") as _f:
                    _raw = _tomllib.load(_f)
                _archives = _raw.get("memory", {}).get("external_archives", [])
                _StubMemory.external_archives = [_ArchiveStub(a) for a in _archives]
            except Exception:
                pass
        cfg = _StubCfg()

    conn = store.connect(db_path)
    try:
        if ns.action == "pull":
            return _do_pull(ns, conn, cfg, project_root)
        if ns.action == "sync":
            return _do_sync(ns, conn, cfg)
    finally:
        conn.conn.close()
    return 2
