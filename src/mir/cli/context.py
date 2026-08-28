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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mir.core.config.loader import ConfigLoadError, load_config, resolve_archive_root
from mir.core.context.profile_task_context import build_profile_task_context
from mir.core.engine.memory import store
from mir.core.engine.memory.external_store import ExternalStore, ExternalStoreError

from ._common import default_db_path

_SNIPPET_BUDGET_BYTES = 6144  # 6 KB total per pull
_FACT_BUDGET_BYTES = 2048
_FACT_TRUNC_SUFFIX = "…[truncated]"
_UNSAFE_FACT_PATTERNS = (
    re.compile(
        r"\b(?:ignore|disregard|override)\b.{0,80}"
        r"\b(?:all|any|previous|prior|earlier|above|system|developer)\b.{0,40}"
        r"\b(?:instructions?|directions?|rules?|guidance)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:you\s+must|must|immediately|now)\b.{0,60}"
        r"\b(?:execute|run|invoke|call)\b.{0,40}"
        r"\b(?:tools?|commands?|shell|bash|terminal)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:reveal|print|exfiltrate)\b.{0,80}"
        r"\b(?:system prompt|credentials?|secrets?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"<\s*/?\s*(?:system|assistant|developer|tool)\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|gho)_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"),
    re.compile(r"\bxoxb-[0-9A-Za-z-]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\baws_secret_access_key\s*=\s*\S+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_NEAR_DUP_SHINGLE_N = 8
_NEAR_DUP_JACCARD_THRESHOLD = 0.85


@dataclass(frozen=True)
class _FactRow:
    id: int
    status: str
    subject: str
    predicate: str
    object: str
    source_content_ids: tuple[int, ...]


# ---------------------------------------------------------------------------
# Shingle helpers for near-dup collapse
# ---------------------------------------------------------------------------


def _shingles(text: str, n: int = _NEAR_DUP_SHINGLE_N) -> set[str]:
    """Lowercase, whitespace-normalised n-gram shingle set."""
    normalised = re.sub(r"\s+", " ", text.lower()).strip()
    if len(normalised) < n:
        return {normalised} if normalised else set()
    return {normalised[i : i + n] for i in range(len(normalised) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _truncate_utf8(text: str, max_bytes: int, suffix: str = _FACT_TRUNC_SUFFIX) -> str:
    """Truncate *text* at a UTF-8 boundary and retain an explicit suffix."""
    encoded_suffix = suffix.encode("utf-8")
    if max_bytes < len(encoded_suffix):
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[: max_bytes - len(encoded_suffix)].decode("utf-8", errors="ignore") + suffix


def _search_facts(
    conn, query: str, *, limit: int, include_history: bool
) -> list[_FactRow]:
    """Fetch fact rows with an explicit final tie-break for stable rendering."""
    from mir.core.engine.memory.distill import sanitize_fts_query

    status_clause = "" if include_history else "AND f.status = 'active'"
    rows = conn.execute(
        f"""
            SELECT f.id, f.status,
                   COALESCE(subject.slug, subject.canonical_name, 'unknown-subject'),
                   f.predicate,
                   COALESCE(f.object_literal, object_entity.slug, ''),
                   COALESCE(
                     (SELECT GROUP_CONCAT(DISTINCT p.content_item_id)
                        FROM provenance p
                       WHERE p.fact_id = f.id AND p.content_item_id IS NOT NULL),
                     CAST(f.created_from AS TEXT),
                     ''
                   )
              FROM facts_fts s JOIN facts f ON f.id = s.rowid
              LEFT JOIN entities subject ON subject.id = f.subject_entity_id
              LEFT JOIN entities object_entity ON object_entity.id = f.object_entity_id
             WHERE facts_fts MATCH ? {status_clause}
             ORDER BY bm25(facts_fts), f.id ASC
             LIMIT ?
        """,
        (sanitize_fts_query(query), limit),
    ).fetchall()
    return [
        _FactRow(
            id=row[0],
            status=row[1],
            subject=row[2],
            predicate=row[3],
            object=row[4],
            source_content_ids=tuple(
                int(value) for value in row[5].split(",") if value
            ),
        )
        for row in rows
    ]


def _quarantine_instruction_like_facts(
    facts: list[_FactRow],
) -> tuple[list[_FactRow], list[int]]:
    """Keep retrieved memory as data by omitting obvious instruction injection."""
    safe: list[_FactRow] = []
    blocked: list[int] = []
    for fact in facts:
        body = f"{fact.subject} {fact.predicate} {fact.object}"
        if any(pattern.search(body) for pattern in _UNSAFE_FACT_PATTERNS):
            blocked.append(fact.id)
        else:
            safe.append(fact)
    return safe, blocked


def _fact_prefix(fact: _FactRow) -> str:
    sources = ",".join(str(value) for value in fact.source_content_ids) or "unknown"
    return (
        f"[fact] #{fact.id} [{fact.status}] {fact.subject} {fact.predicate} "
        f"[sources:{sources}] "
    )


def _render_fact_rows(facts: list[_FactRow]) -> list[_FactRow]:
    """Bound human fact lines to the ADR-84 2 KiB output budget."""
    rendered: list[_FactRow] = []
    remaining = _FACT_BUDGET_BYTES
    for fact in facts:
        line = f"{_fact_prefix(fact)}{fact.object}"
        line_bytes = len(line.encode("utf-8"))
        separator = 1 if rendered else 0
        if line_bytes + separator <= remaining:
            rendered.append(fact)
            remaining -= line_bytes + separator
            continue
        if remaining <= separator:
            break
        prefix = _fact_prefix(fact)
        object_budget = remaining - separator - len(prefix.encode("utf-8"))
        if object_budget >= len(_FACT_TRUNC_SUFFIX.encode("utf-8")):
            rendered.append(
                _FactRow(
                    id=fact.id,
                    status=fact.status,
                    subject=fact.subject,
                    predicate=fact.predicate,
                    object=_truncate_utf8(fact.object, object_budget),
                    source_content_ids=fact.source_content_ids,
                )
            )
        break
    return rendered


def _json_fact_rows(facts: list[_FactRow]) -> list[dict[str, Any]]:
    """Bound the JSON ``facts`` value itself to 2 KiB without invalid UTF-8."""
    out: list[dict[str, Any]] = []
    for fact in facts:
        candidate = {
            "id": fact.id,
            "status": fact.status,
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object,
            "source_content_ids": list(fact.source_content_ids),
        }
        if (
            len(json.dumps([*out, candidate], ensure_ascii=False).encode("utf-8"))
            <= _FACT_BUDGET_BYTES
        ):
            out.append(candidate)
            continue
        # Keep one explicitly truncated final fact when its fixed fields fit.
        low, high = 0, len(fact.object.encode("utf-8"))
        best: dict[str, Any] | None = None
        while low <= high:
            mid = (low + high) // 2
            trial = dict(candidate)
            trial["object"] = _truncate_utf8(fact.object, mid)
            if (
                len(json.dumps([*out, trial], ensure_ascii=False).encode("utf-8"))
                <= _FACT_BUDGET_BYTES
            ):
                best = trial
                low = mid + 1
            else:
                high = mid - 1
        if best is not None and _FACT_TRUNC_SUFFIX in best["object"]:
            out.append(best)
        break
    return out


# ---------------------------------------------------------------------------
# Embed helper
# ---------------------------------------------------------------------------


def _build_embed_fn(cfg) -> Any | None:
    """Build embed callable from ResolvedConfig.memory.embedding, or None.

    Returns None if the embedding config is unavailable. Raises on
    construction errors (caller catches and degrades).
    """
    emb_cfg = cfg.memory.embedding
    if not emb_cfg.enabled:
        return None
    from mir.core.engine.memory.backends.omlx_http import from_config

    return from_config(emb_cfg).encode


# ---------------------------------------------------------------------------
# pull subcommand
# ---------------------------------------------------------------------------


def _profile_context_lines(context: dict[str, Any] | None) -> list[str]:
    if context is None:
        return []
    repo = context["repository"]
    purpose = " ".join(str(repo.get("purpose", "")).split())
    line = (
        f"[repository] {repo.get('slug', 'unknown')} type={repo.get('repository_type', 'unknown')}"
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
            rendered = (
                ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
            )
            lines.append(f"[safety] {section}.{key}={rendered}")
    enabled_gates = sorted(key for key, value in safety.get("gates", {}).items() if value is True)
    if enabled_gates:
        lines.append(f"[safety] enabled_gates={', '.join(enabled_gates)}")

    for item in context["selected_refs"]:
        lines.append(f"[context-ref] {item['kind']} {item['path']}")
    freshness = context["freshness"]
    freshness_line = (
        f"[profile-freshness] state={freshness['state']} base={freshness['base_commit']}"
    )
    changed = freshness.get("changed_selected", [])
    if changed:
        freshness_line += f" changed={','.join(changed)}"
    freshness_line += f" reason={freshness['reason']}"
    lines.append(freshness_line)
    if context["needs_investigation"]:
        lines.append(
            "[context-advisory] inspect only the selected or uncertain boundary before expanding"
        )
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

    safe_facts, quarantined_fact_ids = _quarantine_instruction_like_facts(
        _search_facts(conn.conn, query, limit=k, include_history=include_history)
    )
    if quarantined_fact_ids:
        rendered_ids = ",".join(str(fact_id) for fact_id in quarantined_fact_ids)
        notices.append(f"[unsafe-memory] unsafe fact(s) omitted: {rendered_ids}")
    fact_rows = _render_fact_rows(safe_facts)

    # Check archives exist. Facts are independent durable context, so this is
    # deliberately after fact retrieval rather than an early empty-result exit.
    archive_rows = conn.conn.execute(
        "SELECT id, slug FROM external_archives ORDER BY id"
    ).fetchall()
    if not archive_rows:
        msg = (
            "no archives configured — run 'mir context sync' after adding "
            "[[memory.external_archives]] to harness_a.toml"
        )
        notices.append(msg)
        if output_json:
            print(
                json.dumps(
                    {
                        "degraded": degraded,
                        "notices": notices,
                        "repository_context": profile_context,
                        "facts": _json_fact_rows(fact_rows),
                        "chunks": [],
                    },
                    ensure_ascii=False,
                )
            )
        else:
            for line in _profile_context_lines(profile_context):
                print(line)
            for fact in fact_rows:
                print(f"{_fact_prefix(fact)}{fact.object}")
            for notice in notices:
                print(notice)
        return 0

    # Try search; on embed exception retry FTS-only
    hits = []
    try:
        hits = es.search(
            query,
            k=k,
            path_scopes=path_scopes,
            embed_fn=embed_fn,
            encoder_fingerprint=(
                cfg.memory.embedding.fingerprint if embed_fn is not None else None
            ),
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
            snippet = data[hit.byte_start : hit.byte_end].decode("utf-8", errors="replace")
        except Exception:
            notices.append("[stale] index entry skipped — run 'mir context sync'")
            continue
        kept_snippets.append((hit, snippet))

    # Near-dup collapse: Jaccard 8-gram > 0.85 vs any higher-ranked KEPT snippet → drop
    collapsed: list[tuple[Any, str]] = []
    kept_shingles: list[set[str]] = []
    for hit, snippet in kept_snippets:
        shingles = _shingles(snippet)
        is_dup = any(_jaccard(shingles, ks) > _NEAR_DUP_JACCARD_THRESHOLD for ks in kept_shingles)
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

    if output_json:
        out = {
            "degraded": degraded,
            "notices": notices,
            "repository_context": profile_context,
            "facts": _json_fact_rows(fact_rows),
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
        print(json.dumps(out, ensure_ascii=False))
        return 0

    # Human output
    for line in _profile_context_lines(profile_context):
        print(line)
    for n in notices:
        print(n)

    # Facts first (--history)
    for fact in fact_rows:
        print(f"{_fact_prefix(fact)}{fact.object}")

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


def _do_sync(ns: argparse.Namespace, conn, cfg, project_root: Path) -> int:
    """Execute sync logic. Returns exit code (1 if any failures)."""
    es = ExternalStore(conn)
    # D8: register archives from harness_a.toml config if not yet in DB
    if hasattr(cfg, "memory") and hasattr(cfg.memory, "external_archives"):
        for arch in cfg.memory.external_archives:
            es.register(
                slug=arch.slug,
                root_path=str(resolve_archive_root(project_root, arch)),
                mode=arch.mode,
                glob_include=tuple(arch.glob_include) if arch.glob_include else ("**/*.md",),
                glob_exclude=tuple(arch.glob_exclude),
                historical_glob=tuple(arch.historical_glob),
                chunk_size=arch.chunk_size,
                chunk_overlap=arch.chunk_overlap,
                owner="family:your-harness",
            )
    archive_rows = conn.conn.execute(
        "SELECT id, slug FROM external_archives ORDER BY id"
    ).fetchall()
    if not archive_rows:
        print("no archives configured")
        return 0

    if ns.reindex_missing_vectors:
        if not cfg.memory.embedding.enabled:
            print("missing-vector reindex requires memory.embedding.enabled=true")
            return 2
        if not conn.vec_available:
            print("missing-vector reindex requires sqlite-vec")
            return 2
        try:
            embed_fn = _build_embed_fn(cfg)
        except Exception as exc:
            print(f"missing-vector reindex embedding backend unavailable: {exc}")
            return 1
        if embed_fn is None:
            print("missing-vector reindex requires an embedding backend")
            return 2
        any_failed = False
        for archive_id, slug in archive_rows:
            try:
                result = es.reindex_missing_vectors(
                    archive_id,
                    embed_fn=embed_fn,
                    encoder_fingerprint=cfg.memory.embedding.fingerprint,
                )
            except ExternalStoreError as exc:
                any_failed = True
                print(f"{slug}: vector reindex refused: {exc}")
                continue
            print(
                f"{slug}: vector_coverage={result.indexed}/{result.eligible} "
                f"reindexed={result.reindexed} unchanged={result.unchanged}"
            )
            if result.failed:
                any_failed = True
                for rel, reason in result.failed:
                    print(f"  [failed] {rel}: {reason}")
        return 1 if any_failed else 0

    embed_fn = None
    try:
        embed_fn = _build_embed_fn(cfg)
    except Exception as exc:
        if cfg.memory.embedding.required or cfg.memory.vector_mode == "required":
            print(f"required embedding backend unavailable: {exc}")
            return 1
        print(f"[degraded] embedding unavailable — FTS-only sync: {exc}")

    any_failed = False
    for archive_id, slug in archive_rows:
        try:
            result = es.scan(
                archive_id,
                embed_fn=embed_fn,
                encoder_fingerprint=(
                    cfg.memory.embedding.fingerprint if embed_fn is not None else None
                ),
            )
        except ExternalStoreError as exc:
            any_failed = True
            print(f"{slug}: vector indexing refused: {exc}")
            continue
        if result.failed and embed_fn is not None and cfg.memory.vector_mode == "optional":
            print(f"[degraded] {slug}: vector indexing failed — retrying FTS-only")
            result = es.scan(archive_id, embed_fn=None)
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
    pl.add_argument(
        "--history",
        action="store_true",
        default=False,
        help="include expired/archived docs and facts",
    )
    pl.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json",
        help="machine-readable JSON output",
    )
    pl.add_argument("--k", type=int, default=8, dest="k", help="number of results (default: 8)")
    pl.add_argument(
        "--path",
        action="append",
        default=[],
        dest="target_paths",
        help="repository-relative task target (repeatable)",
    )
    pl.add_argument(
        "--risk",
        choices=("low", "normal", "high"),
        default="normal",
        help="main-agent task risk classification (default: normal)",
    )
    pl.add_argument("--db", type=Path, default=None)
    pl.add_argument("--project-root", type=Path, default=None, dest="project_root")

    sy = sub.add_parser("sync", help="ADR-53 D2: scan all configured archives")
    sy.add_argument(
        "--reindex-missing-vectors",
        action="store_true",
        default=False,
        help="explicitly backfill missing vector rows; never falls back to FTS-only",
    )
    sy.add_argument("--db", type=Path, default=None)
    sy.add_argument("--project-root", type=Path, default=None, dest="project_root")

    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    db_path = ns.db or default_db_path()
    project_root = ns.project_root or (
        db_path.parent.parent
        if db_path.name == "memory.db" and db_path.parent.name == ".mir"
        else db_path.parent
    )
    project_root = project_root.resolve()
    if not db_path.is_file():
        print(f"no memory.db at {db_path} — run 'mir migrate up' first")
        return 2

    # Load config (harness_a.toml). Malformed authored intent fails loud.
    try:
        cfg = load_config(project_root)
    except ConfigLoadError as exc:
        print(f"invalid memory configuration: {exc}")
        return 2

    conn = store.connect(db_path)
    try:
        if ns.action == "pull":
            return _do_pull(ns, conn, cfg, project_root)
        if ns.action == "sync":
            return _do_sync(ns, conn, cfg, project_root)
    finally:
        conn.conn.close()
    return 2
