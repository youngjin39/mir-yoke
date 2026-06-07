from __future__ import annotations

"""ADR-54 D1+D2+D3 — parity manifest generator and checker.

Generator (generate-parity subcommand):
  - Walks template repo file inventory from config/parity-classes.json.
  - Computes sha256 of normalized content per ownership class.
  - Walks git history (--follow, bounded) for previous_hashes[].
  - Embeds template_version, template_commit, generated_at, normalization rules.
  - D1 invariant: exits non-zero if any non-family-owned seeded path is absent.

Checker (R16 template_parity rule):
  - Reads parity manifest (manifest_path).
  - Compares live file hashes against manifest: IN_SYNC / BEHIND / LOCAL_DIVERGED.
  - Staleness guard (v5.2): compares live .git/HEAD against release ref
    refs/mir/parity-base (file-parse; absent -> skip silently).
    manifest.template_commit is provenance only.
  - Degradation: single WARN for template unreachable / manifest absent.
  - Probes v1: migration_head (sqlite3 mode=ro) + venv_mir_resolution.
  - Hard read-only: Path reads, sqlite3 mode=ro, ONE venv python subprocess.
  - NO uv run, NO git subprocess, NO writes.
"""

import datetime  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import subprocess  # noqa: E402
from collections.abc import Callable  # noqa: E402
from pathlib import Path  # noqa: E402

from tools.harness_consistency.models import Finding  # noqa: E402

# Marker constants for mir:adr53:context-core block
_MARKER_BEGIN = "# mir:adr53:context-core:begin"
_MARKER_END = "# mir:adr53:context-core:end"

# Slug placeholder used in normalized hashes for parameterized files
_SLUG_PLACEHOLDER = "{{SLUG}}"

# Template placeholder slug (generator side)
_TEMPLATE_SLUG = "your-harness"

# Minimum DB migration head for migration_head probe
_MIN_MIGRATION_HEAD = "017"

_KNOWN_OWNERSHIP_CLASSES = {
    "verbatim",
    "parameterized",
    "marker-block",
    "family-owned",
    "managed-keys",
}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _project_rule_catalog_v1(parsed: dict) -> dict:
    return {
        "version": int(parsed["version"]),
        "rules": sorted(
            [
                {
                    "id": rule["id"],
                    "name": rule["name"],
                    "severity": rule["severity"],
                    "drift_class": rule["drift_class"],
                }
                for rule in parsed["rules"]
            ],
            key=lambda item: item["name"],
        ),
    }


_MANAGED_KEY_PROJECTIONS: dict[str, Callable[[dict], dict]] = {
    "rule-catalog-v1": _project_rule_catalog_v1,
}

_MANAGED_KEY_EXCEPTIONS = (json.JSONDecodeError, KeyError, TypeError, ValueError)


def _lf_normalize(text: str) -> str:
    """Normalize line endings to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _marked_block(text: str, marker_begin: str, marker_end: str) -> str:
    """Extract content between begin/end markers (exclusive of markers)."""
    begin_index = text.find(marker_begin)
    if begin_index == -1:
        return ""
    content_start = begin_index + len(marker_begin)
    end_index = text.find(marker_end, content_start)
    if end_index == -1:
        return ""
    return text[content_start:end_index]


def _normalized_block(text: str) -> str:
    """Rstrip lines, strip blank edges, LF join — matches rules.py _normalized_generated_block."""
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _normalize_content(
    raw: str,
    ownership_class: str,
    params: dict,
    *,
    slug: str,
) -> str:
    """Return normalized content for hashing based on ownership_class.

    - verbatim: LF-normalized raw content.
    - parameterized: LF-normalized, then slug → {{SLUG}} replacement.
    - marker-block: extract the marker block content, normalize it.
    - managed-keys: hash an in-code named projection of structured JSON.
    - family-owned: not hashed; returns empty string.
    """
    normalized = _lf_normalize(raw)
    if ownership_class == "verbatim":
        return normalized
    if ownership_class == "parameterized":
        return normalized.replace(slug, _SLUG_PLACEHOLDER)
    if ownership_class == "marker-block":
        marker_begin = params.get("marker_begin", _MARKER_BEGIN)
        marker_end = params.get("marker_end", _MARKER_END)
        block = _marked_block(normalized, marker_begin, marker_end)
        return _normalized_block(block)
    if ownership_class == "managed-keys":
        projection_name = params["projection"]
        try:
            projector = _MANAGED_KEY_PROJECTIONS[projection_name]
        except KeyError as exc:
            raise ValueError(f"unknown projection {projection_name}") from exc
        projected = projector(json.loads(normalized))
        return json.dumps(
            projected,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    # family-owned: excluded
    return ""


# ---------------------------------------------------------------------------
# Git HEAD parsing (read-only file parse — no git subprocess)
# ---------------------------------------------------------------------------


def _resolve_git_head(template_repo: Path) -> str | None:
    """Parse <template>/.git/HEAD to resolve the current commit SHA.

    Returns:
        40-char hex SHA or None if unparseable (worktree gitdir: pointer, etc.).
    """
    head_file = template_repo / ".git" / "HEAD"
    if not head_file.exists():
        return None
    try:
        content = head_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    # Detached HEAD: bare 40-hex SHA
    if re.fullmatch(r"[0-9a-f]{40}", content):
        return content

    # Symbolic ref: "ref: refs/heads/main"
    if content.startswith("ref: "):
        ref = content[5:].strip()
        # Try loose ref file
        loose = template_repo / ".git" / ref
        if loose.exists():
            try:
                sha = loose.read_text(encoding="utf-8").strip()
                if re.fullmatch(r"[0-9a-f]{40}", sha):
                    return sha
            except OSError:
                pass
        # Try packed-refs
        packed = template_repo / ".git" / "packed-refs"
        if packed.exists():
            try:
                for line in packed.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("#"):
                        continue
                    parts = line.split(" ", 1)
                    if len(parts) == 2 and parts[1] == ref:
                        sha = parts[0]
                        if re.fullmatch(r"[0-9a-f]{40}", sha):
                            return sha
            except OSError:
                pass
        return None

    # worktree "gitdir:" pointer or other format — skip silently
    return None


def _resolve_parity_base_ref(template_repo: Path) -> str | None:
    ref = "refs/mir/parity-base"

    loose = template_repo / ".git" / ref
    if loose.exists():
        try:
            sha = loose.read_text(encoding="utf-8").strip()
            if re.fullmatch(r"[0-9a-f]{40}", sha):
                return sha
        except OSError:
            pass

    packed = template_repo / ".git" / "packed-refs"
    if packed.exists():
        try:
            for line in packed.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#"):
                    continue
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[1] == ref:
                    sha = parts[0]
                    if re.fullmatch(r"[0-9a-f]{40}", sha):
                        return sha
        except OSError:
            pass

    return None


# ---------------------------------------------------------------------------
# Generator side
# ---------------------------------------------------------------------------


def _git_history_hashes(
    template_repo: Path,
    path: str,
    ownership_class: str,
    params: dict,
    history_depth: int = 20,
) -> list[str]:
    """Walk git history for a file and return previous normalized hashes.

    Uses git log --follow to handle renames.
    Skips silently on git errors.
    """
    try:
        result = subprocess.run(
            [
                "git", "log", "--follow",
                f"--max-count={history_depth}",
                "--format=%H",
                "--", path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(template_repo),
        )
        if result.returncode != 0:
            return []
        commits = [c.strip() for c in result.stdout.strip().splitlines() if c.strip()]
    except (subprocess.TimeoutExpired, OSError):
        return []

    if not commits:
        return []

    # First commit is HEAD — that is the current hash (already in manifest.hash)
    # We want the REMAINING commits for previous_hashes
    prev_commits = commits[1:]
    if not prev_commits:
        return []

    hashes = []
    for commit in prev_commits:
        try:
            show = subprocess.run(
                ["git", "show", f"{commit}:{path}"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(template_repo),
            )
            if show.returncode != 0:
                continue
            normalized = _normalize_content(
                show.stdout,
                ownership_class,
                params,
                slug=_TEMPLATE_SLUG,
            )
            if not normalized:
                continue
            h = _sha256(normalized)
            if h not in hashes:
                hashes.append(h)
        except (
            subprocess.TimeoutExpired,
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ):
            continue

    return hashes


def generate_parity_manifest(
    template_repo: Path,
    parity_classes_path: Path,
    output_path: Path | None = None,
    history_depth: int = 20,
) -> dict:
    """Generate parity manifest from template repo + parity-classes.json.

    Raises SystemExit(1) if any non-family-owned seeded path is absent (D1 invariant).
    """
    classes_data = json.loads(parity_classes_path.read_text(encoding="utf-8"))
    files_spec = classes_data["files"]

    # Resolve template version and commit
    version_file = template_repo / "VERSION"
    template_version = (
        version_file.read_text(encoding="utf-8").strip()
        if version_file.exists()
        else "unknown"
    )
    template_commit = _resolve_git_head(template_repo) or "unknown"

    # D1 invariant: every non-family-owned seeded path MUST exist in template
    missing = []
    for entry in files_spec:
        if entry["ownership_class"] == "family-owned":
            continue
        fpath = template_repo / entry["path"]
        if not fpath.exists():
            missing.append(entry["path"])

    if missing:
        import sys
        print(
            "[generate-parity] D1 invariant violated: "
            f"{len(missing)} seeded path(s) absent in template:",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  missing: {m}", file=sys.stderr)
        sys.exit(1)

    # Build per-file entries
    file_entries = []
    for entry in files_spec:
        path_str = entry["path"]
        ownership_class = entry["ownership_class"]
        params = entry.get("params", {})

        file_entry: dict = {
            "path": path_str,
            "ownership_class": ownership_class,
        }

        if ownership_class != "family-owned":
            fpath = template_repo / path_str
            raw = fpath.read_text(encoding="utf-8")
            try:
                normalized = _normalize_content(
                    raw,
                    ownership_class,
                    params,
                    slug=_TEMPLATE_SLUG,
                )
            except _MANAGED_KEY_EXCEPTIONS as exc:
                import sys
                print(
                    f"[generate-parity] managed-keys projection failed: "
                    f"{path_str} ({exc})",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not normalized:
                import sys
                print(
                    f"[generate-parity] D1 invariant violated: empty normalized content "
                    f"in {path_str} (marker-block absent or file empty)",
                    file=sys.stderr,
                )
                sys.exit(1)
            current_hash = _sha256(normalized)
            entry_history_depth = int(params.get("history_depth", history_depth))
            previous_hashes = _git_history_hashes(
                template_repo, path_str, ownership_class, params, entry_history_depth
            )
            file_entry["hash"] = current_hash
            file_entry["previous_hashes"] = previous_hashes
        else:
            file_entry["hash"] = None
            file_entry["previous_hashes"] = []

        if params:
            file_entry["params"] = params

        file_entries.append(file_entry)

    manifest = {
        "template_version": template_version,
        "template_commit": template_commit,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "normalization": {
            "verbatim": "sha256 of LF-normalized raw bytes",
            "parameterized": (
                "sha256 after slug normalization "
                "(your-harness / repo.slug → {{SLUG}})"
            ),
            "marker-block": (
                "sha256 of content between mir:adr53:context-core "
                "markers, rstripped+edge-stripped"
            ),
            "managed-keys": "sha256 of named structured JSON projection",
            "family-owned": "excluded from hashing",
            "slug_placeholder": _SLUG_PLACEHOLDER,
            "template_slug": _TEMPLATE_SLUG,
        },
        "files": file_entries,
    }

    if output_path is not None:
        output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return manifest


# ---------------------------------------------------------------------------
# Checker side (R16 rule) — read-only: Path.read_text, sqlite3 mode=ro, ONE venv subprocess
# ---------------------------------------------------------------------------


def _check_staleness(template_repo: Path, manifest: dict) -> Finding | None:
    """Compare parity-base release ref against live HEAD; emit WARN on mismatch."""
    parity_base = _resolve_parity_base_ref(template_repo)
    if parity_base is None:
        return None  # Ref absent — skip silently

    live_commit = _resolve_git_head(template_repo)
    if live_commit is None:
        return None  # Unparseable HEAD — skip silently

    if live_commit != parity_base:
        return Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message=(
                f"parity manifest stale — template HEAD {live_commit[:8]} != "
                f"parity-base {parity_base[:8]}; verdicts may be outdated"
            ),
            location="config/parity-manifest.json",
            drift_class=8,
        )
    return None


def _probe_migration_head(
    project_root: Path, min_head: str = _MIN_MIGRATION_HEAD
) -> Finding | None:
    """Check .mir/memory.db schema_migrations HEAD >= min_head (sqlite3 mode=ro)."""
    db_path = project_root / ".mir" / "memory.db"
    if not db_path.exists():
        return Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message="probe: memory.db absent — migration_head unverified",
            location=".mir/memory.db",
            drift_class=8,
        )
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            cur = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            )
            row = cur.fetchone()
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        return Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message=f"probe: migration_head query failed: {exc}",
            location=".mir/memory.db",
            drift_class=8,
        )
    if row is None:
        return Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message="probe: schema_migrations table empty — migration_head unverified",
            location=".mir/memory.db",
            drift_class=8,
        )
    live_head = str(row[0])
    # NB5: compare as integers when both are all-digit strings to avoid
    # lexicographic traps like "1000" < "017".
    def _int_ver(v: str) -> int | None:
        return int(v) if v.isdigit() else None

    _lv = _int_ver(live_head)
    _mv = _int_ver(min_head)
    if _lv is not None and _mv is not None:
        _behind = _lv < _mv
    else:
        _behind = live_head < min_head
    if _behind:
        return Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message=f"probe: migration_head {live_head!r} < required {min_head!r}",
            location=".mir/memory.db",
            drift_class=8,
        )
    return None


def _probe_venv_mir_resolution(project_root: Path) -> Finding | None:
    """Check that .venv/bin/python resolves mir inside the repo root.

    Documented exception to uv-run-mir-resolution: this is a resolution
    DIAGNOSTIC, not a mir CLI invocation. We use venv python directly to
    avoid uv's sync side effects.
    """
    venv_python = project_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message="probe: venv missing — resolution unverified",
            location=".venv/bin/python",
            drift_class=8,
        )
    try:
        result = subprocess.run(
            [str(venv_python), "-c", "import mir; print(mir.__file__)"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(project_root),
        )
        if result.returncode != 0:
            return Finding(
                rule_id="R16",
                rule_name="template_parity",
                severity="WARN",
                message=f"probe: venv mir import failed: {result.stderr.strip()[:100]}",
                location=".venv/bin/python",
                drift_class=8,
            )
        mir_file = Path(result.stdout.strip()).resolve()
        # NB6: resolve both paths before relative_to to handle symlinked project_root
        _resolved_root = project_root.resolve()
        try:
            mir_file.relative_to(_resolved_root)
        except ValueError:
            return Finding(
                rule_id="R16",
                rule_name="template_parity",
                severity="WARN",
                message=f"probe: mir resolves outside repo root: {mir_file}",
                location=".venv/bin/python",
                drift_class=8,
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message=f"probe: venv python subprocess error: {exc}",
            location=".venv/bin/python",
            drift_class=8,
        )
    return None


def _probe_slug_integrity(
    project_root: Path, repo_slug: str
) -> Finding | None:
    """Check .mir/memory.db for rows stamped with a foreign family identity (mode=ro).

    Q1: external_archives.owner != 'family:<slug>' -> WARN listing foreign owners+counts.
    Q2: external_documents.source_slug NOT NULL AND != slug -> WARN listing foreign slugs+counts.
    DB absent -> skip (no finding). sqlite3.OperationalError (pre-015/017 schema) -> skip.
    Never writes. Mode=ro only. No subprocess.
    """
    db_path = project_root / ".mir" / "memory.db"
    if not db_path.exists():
        return None
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            # Q1: foreign owners in external_archives
            cur = conn.execute(
                "SELECT owner, COUNT(*) FROM external_archives "
                "WHERE owner != ? GROUP BY owner",
                (f"family:{repo_slug}",),
            )
            foreign_owners = cur.fetchall()

            # Q2: foreign source_slugs in external_documents
            cur = conn.execute(
                "SELECT source_slug, COUNT(*) FROM external_documents "
                "WHERE source_slug IS NOT NULL AND source_slug != ? GROUP BY source_slug",
                (repo_slug,),
            )
            foreign_slugs = cur.fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None  # Pre-015/017 schema: skip silently

    findings_parts: list[str] = []
    if foreign_owners:
        owner_summary = ", ".join(
            f"{owner}({count})" for owner, count in foreign_owners
        )
        findings_parts.append(f"foreign owners: {owner_summary}")
    if foreign_slugs:
        slug_summary = ", ".join(
            f"{slug}({count})" for slug, count in foreign_slugs
        )
        findings_parts.append(f"foreign source_slugs: {slug_summary}")

    if not findings_parts:
        return None

    return Finding(
        rule_id="R16",
        rule_name="template_parity",
        severity="WARN",
        message="probe: slug_integrity — " + "; ".join(findings_parts),
        location=".mir/memory.db",
        drift_class=8,
    )


def _check_file_verdict(
    project_root: Path,
    file_entry: dict,
    repo_slug: str,
    exclude_paths: set[str],
) -> tuple[str, str | None]:
    """Check one file entry. Returns (verdict, detail_or_None).

    verdict: 'IN_SYNC' | 'BEHIND' | 'LOCAL_DIVERGED' | 'EXCLUDED' | 'SKIPPED'
    """
    path_str = file_entry["path"]
    ownership_class = file_entry["ownership_class"]

    if path_str in exclude_paths:
        return "EXCLUDED", None

    if ownership_class == "family-owned":
        return "SKIPPED", None

    live_path = project_root / path_str
    if not live_path.exists():
        return "LOCAL_DIVERGED", f"file absent: {path_str}"

    params = file_entry.get("params", {})
    try:
        raw = live_path.read_text(encoding="utf-8")
    except OSError as exc:
        return "LOCAL_DIVERGED", f"read error: {exc}"

    try:
        normalized = _normalize_content(raw, ownership_class, params, slug=repo_slug)
    except _MANAGED_KEY_EXCEPTIONS as exc:
        return "LOCAL_DIVERGED", f"managed-keys projection failed: {path_str} ({exc})"
    if not normalized and ownership_class == "marker-block":
        return "LOCAL_DIVERGED", f"marker block missing: {path_str}"
    live_hash = _sha256(normalized)

    manifest_hash = file_entry.get("hash")
    if live_hash == manifest_hash:
        return "IN_SYNC", None

    previous = file_entry.get("previous_hashes", [])
    if live_hash in previous:
        return "BEHIND", None

    return "LOCAL_DIVERGED", f"hash mismatch: {path_str}"


def template_parity(project_root: Path, rule_inputs: dict) -> list[Finding]:
    """R16 template_parity checker rule.

    rule_inputs keys:
        template_repo: str — absolute path to template repo
        manifest_path: str — relative path to parity manifest
            (default config/parity-manifest.json)
        probes_enabled: bool
        exclude_paths: list[str] (optional)
    """
    findings: list[Finding] = []

    template_repo_str = rule_inputs.get("template_repo", "")
    template_repo = Path(template_repo_str) if template_repo_str else Path(".")

    # Resolve template_repo relative to project_root if it is "."
    if template_repo_str == ".":
        template_repo = project_root

    manifest_rel = rule_inputs.get("manifest_path", "config/parity-manifest.json")
    probes_enabled = rule_inputs.get("probes_enabled", True)
    exclude_paths: set[str] = set(rule_inputs.get("exclude_paths") or [])

    # Degradation: template unreachable
    if not template_repo.exists():
        findings.append(Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message="template repo unreachable — parity check skipped",
            location=str(template_repo),
            drift_class=8,
        ))
        return findings

    # Manifest path: relative to project_root
    manifest_path = template_repo / manifest_rel
    if not manifest_path.exists():
        findings.append(Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message="parity manifest absent — generate-parity not yet run",
            location=manifest_rel,
            drift_class=8,
        ))
        # Still run probes even when manifest is absent
        if probes_enabled:
            _run_probes(project_root, findings)
        return findings

    # Load manifest
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        findings.append(Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message=f"parity manifest unreadable: {exc}",
            location=manifest_rel,
            drift_class=8,
        ))
        return findings

    # Staleness guard
    stale_finding = _check_staleness(template_repo, manifest)
    if stale_finding:
        findings.append(stale_finding)

    # Get repo slug for parameterized normalization.
    # When template_repo_str == '.' this is a template self-check:
    # use _TEMPLATE_SLUG ('your-harness') so parameterized normalization matches.
    if template_repo_str == '.':
        repo_slug = _TEMPLATE_SLUG
    else:
        # 3-step slug resolution for fleet repos:
        # 1. Explicit override in rule_inputs (highest precedence)
        # 2. config/harness-consistency.json -> repo.slug
        #    (Path read only — checker read-only contract)
        # 3. project_root.name last-resort with an observable WARN finding
        _explicit_slug = rule_inputs.get('repo_slug')
        if _explicit_slug:
            repo_slug = str(_explicit_slug)
        else:
            _cfg_slug: str | None = None
            try:
                _cfg_path = project_root / 'config' / 'harness-consistency.json'
                _cfg_data = json.loads(_cfg_path.read_text(encoding='utf-8'))
                _raw = _cfg_data.get('repo', {}).get('slug', '')
                if isinstance(_raw, str) and _raw.strip():
                    _cfg_slug = _raw.strip()
            except Exception:
                pass
            if _cfg_slug:
                repo_slug = _cfg_slug
            else:
                repo_slug = project_root.name
                findings.append(Finding(
                    rule_id='R16',
                    rule_name='template_parity',
                    severity='WARN',
                    drift_class=8,
                    location='config/harness-consistency.json',
                    message=(
                        f'slug unresolved from config: directory-name fallback '
                        f"'{project_root.name}' used for parameterized normalization — "
                        'verdicts for parameterized files may be unreliable'
                    ),
                ))

    # Per-file verdicts
    behind_files: list[str] = []
    diverged_files: list[str] = []

    for file_entry in manifest.get("files", []):
        path_str = file_entry.get("path", "<unknown>")
        ownership_class = file_entry.get("ownership_class")
        if ownership_class not in _KNOWN_OWNERSHIP_CLASSES:
            findings.append(Finding(
                rule_id="R16",
                rule_name="template_parity",
                severity="WARN",
                message=(
                    f"unknown ownership_class {ownership_class} in manifest — "
                    f"engine older than manifest; skipping {path_str}"
                ),
                location=manifest_rel,
                drift_class=8,
            ))
            continue
        params = file_entry.get("params", {})
        if (
            ownership_class == "managed-keys"
            and params.get("projection") not in _MANAGED_KEY_PROJECTIONS
        ):
            findings.append(Finding(
                rule_id="R16",
                rule_name="template_parity",
                severity="WARN",
                message=(
                    f"unknown projection {params.get('projection')} in manifest — "
                    f"engine older than manifest; skipping {path_str}"
                ),
                location=manifest_rel,
                drift_class=8,
            ))
            continue
        verdict, detail = _check_file_verdict(project_root, file_entry, repo_slug, exclude_paths)
        if verdict == "BEHIND":
            behind_files.append(file_entry["path"])
        elif verdict == "LOCAL_DIVERGED":
            diverged_files.append(file_entry["path"] + (f" ({detail})" if detail else ""))

    if behind_files:
        findings.append(Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message=(
                f"BEHIND: {len(behind_files)} file(s) lag template "
                f"(wave pending): {', '.join(behind_files[:3])}"
                f"{'...' if len(behind_files) > 3 else ''}"
            ),
            location="config/parity-manifest.json",
            drift_class=8,
        ))

    if diverged_files:
        findings.append(Finding(
            rule_id="R16",
            rule_name="template_parity",
            severity="WARN",
            message=(
                f"LOCAL_DIVERGED: {len(diverged_files)} file(s) differ "
                f"from template and history: {', '.join(diverged_files[:3])}"
                f"{'...' if len(diverged_files) > 3 else ''}"
            ),
            location="config/parity-manifest.json",
            drift_class=8,
        ))

    # Probes
    if probes_enabled:
        _run_probes(project_root, findings, repo_slug)

    return findings


def _run_probes(project_root: Path, findings: list[Finding], repo_slug: str = '') -> None:
    """Run probes and append findings in place."""
    probe_migration = _probe_migration_head(project_root)
    if probe_migration:
        findings.append(probe_migration)

    probe_venv = _probe_venv_mir_resolution(project_root)
    if probe_venv:
        findings.append(probe_venv)

    if repo_slug:
        probe_slug = _probe_slug_integrity(project_root, repo_slug)
        if probe_slug:
            findings.append(probe_slug)
