"""Cross-platform coordinator for a ready Mir project baseline."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import yaml

from mir.core.config.loader import ConfigLoadError, load_config, resolve_memory_db
from mir.core.engine.memory import store

from . import context as context_cli
from . import memory as memory_cli

_PROFILE_CHOICES = ("code_app", "hybrid_pipeline", "infra_runtime", "content_workspace")
_PROFILE_ALIASES = {"hybrid": "hybrid_pipeline", "infra": "infra_runtime"}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ARCHITECTURE_OUTPUTS = (
    "spec/STATE.md",
    "spec/index.yaml",
    "spec/graph.yaml",
    "spec/gaps.yaml",
)
_ARCHITECTURE_SEQUENCE = ("mir-core:design", "mir-core:spec-architect")
_CONTENT_EXTENSIONS = (".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv")
_DISCOVERABLE_CONTENT_EXTENSIONS = _CONTENT_EXTENSIONS + (
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".odt",
    ".pages",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".xls",
    ".xlsx",
)
_CONTENT_SCAN_EXCLUDES = {
    ".agents",
    ".ai-harness",
    ".claude",
    ".codex",
    ".git",
    ".github",
    ".mir",
    ".venv",
    "app",
    "config",
    "docs",
    "examples",
    "global-rules",
    "lib",
    "plugins",
    "scripts",
    "spec",
    "src",
    "tasks",
    "tests",
    "tools",
}
_ROOT_CONTENT_EXCLUDES = {
    "AGENTS.md",
    "ARCHITECTURE.md",
    "BOOTSTRAP.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "MIGRATION.md",
    "README.md",
    "SECURITY.md",
    "harness_a.toml",
    "llms.txt",
    "pyproject.toml",
    "template_protected_paths.yaml",
    "uv.lock",
}
_PLACEHOLDER_RE = re.compile(r"\b(?:describe|placeholder|replace[ -]?me|tbd|todo|unknown)\b", re.I)
_EXTERNAL_STORAGE_PATHS = {
    "UV_CACHE_DIR": Path("uv/cache"),
    "UV_PYTHON_INSTALL_DIR": Path("uv/python"),
    "UV_TOOL_DIR": Path("uv/tools"),
    "MIR_CAPABILITY_HOME": Path("mir/capabilities"),
}


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mir bootstrap")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--slug", default=None)
    parser.add_argument(
        "--profile",
        required=True,
        help="required project archetype; no implicit code_app default",
    )
    parser.add_argument("--purpose", help="non-placeholder project mission (required in phase 1)")
    parser.add_argument(
        "--stack",
        action="append",
        default=[],
        help="technology or working-medium item; repeat or pass comma-separated values",
    )
    parser.add_argument(
        "--archive",
        action="append",
        default=[],
        metavar="CLASSIFICATION=PATH",
        help="classify an existing content path for onboarding (content_workspace)",
    )
    parser.add_argument(
        "--storage-root",
        type=Path,
        help="shared external-volume root configured by setup.sh or setup.ps1",
    )
    parser.add_argument("--json", action="store_true", default=False, dest="json")
    parser.add_argument(
        "--finalize",
        action="store_true",
        default=False,
        help="phase 2: verify capabilities after restarting the agent runtime",
    )
    parser.add_argument(
        "--architecture-initialized",
        action="store_true",
        default=False,
        help="attest that mir-core:design then mir-core:spec-architect initialized the project",
    )
    parser.add_argument(
        "--skip-capability-activation",
        action="store_true",
        default=False,
        help="test/development only: leave bootstrap incomplete unless --allow-incomplete",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def _storage_preflight(root: Path, requested: Path | None) -> tuple[list[str], dict]:
    if requested is None:
        return [], {
            "mode": "host-default",
            "root": None,
            "same_filesystem_as_project": None,
            "large_payloads": {},
        }

    storage_root = requested.expanduser().resolve(strict=False)
    report = {
        "mode": "external-first",
        "root": str(storage_root),
        "project_environment": str((root / ".venv").resolve(strict=False)),
        "same_filesystem_as_project": False,
        "large_payloads": {},
    }
    errors: list[str] = []
    if not storage_root.is_dir():
        errors.append(f"external storage root is not a directory: {storage_root}")
        return errors, report
    if not os.access(storage_root, os.W_OK):
        errors.append(f"external storage root is not writable: {storage_root}")

    configured_paths: list[Path] = []
    for name, relative in _EXTERNAL_STORAGE_PATHS.items():
        expected = (storage_root / relative).resolve(strict=False)
        raw = os.environ.get(name)
        if not raw:
            errors.append(
                f"{name} is not configured; invoke bootstrap through setup.sh/setup.ps1 "
                "with --storage-root"
            )
            continue
        actual = Path(raw).expanduser().resolve(strict=False)
        report["large_payloads"][name] = str(actual)
        if actual != expected:
            errors.append(f"{name} must resolve to {expected}, got {actual}")
        elif not actual.is_dir():
            errors.append(f"{name} directory is missing: {actual}")
        else:
            configured_paths.append(actual)

    expected_environment = (root / ".venv").resolve(strict=False)
    raw_environment = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if not raw_environment:
        errors.append("UV_PROJECT_ENVIRONMENT is not configured for project-local .venv")
    else:
        actual_environment = Path(raw_environment).expanduser().resolve(strict=False)
        if actual_environment != expected_environment:
            errors.append(
                f"UV_PROJECT_ENVIRONMENT must resolve to {expected_environment}, "
                f"got {actual_environment}"
            )

    try:
        project_device = os.stat(root).st_dev
        same_filesystem = (
            len(configured_paths) == len(_EXTERNAL_STORAGE_PATHS)
            and os.stat(storage_root).st_dev == project_device
            and all(os.stat(path).st_dev == project_device for path in configured_paths)
        )
    except OSError as exc:
        errors.append(f"external storage filesystem check failed: {exc}")
    else:
        report["same_filesystem_as_project"] = same_filesystem
        if not same_filesystem:
            errors.append(
                "external storage root and project must use the same filesystem so uv can "
                "clone/link cached packages instead of copying them"
            )
    return errors, report


def _normalise_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-_")
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"project slug {raw!r} cannot be normalized to a valid slug")
    return slug


def _normalise_stack(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            item.strip()
            for value in values
            for item in value.split(",")
            if item.strip()
        )
    )


def _validate_project_identity(purpose: str | None, stack: list[str]) -> list[str]:
    errors: list[str] = []
    if not purpose or not purpose.strip():
        errors.append("--purpose is required during bootstrap phase 1")
    elif "\n" in purpose or "\r" in purpose:
        errors.append("--purpose must be a single line")
    elif _PLACEHOLDER_RE.search(purpose):
        errors.append("--purpose must not contain placeholder text")
    if not stack:
        errors.append("at least one --stack value is required during bootstrap phase 1")
    for item in stack:
        if _PLACEHOLDER_RE.search(item):
            errors.append(f"--stack must not contain placeholder text: {item!r}")
    return errors


def _project_relative(root: Path, raw: str) -> tuple[Path, str]:
    authored = Path(raw)
    if authored.is_absolute():
        raise ValueError(f"content archive path must be project-relative: {raw}")
    resolved = (root / authored).resolve(strict=False)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"content archive path escapes the project: {raw}") from exc
    if relative in ("", "."):
        raise ValueError("content archive path must name a file or directory, not project root")
    return resolved, relative


def _discoverable_content_files(root: Path, path: Path) -> list[Path]:
    if path.is_symlink():
        raise ValueError(f"content archive path must not be a symlink: {path.relative_to(root)}")
    candidates = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
    files: list[Path] = []
    for candidate in candidates:
        if candidate.is_symlink():
            raise ValueError(
                f"content archive contains a symlink: {candidate.relative_to(root).as_posix()}"
            )
        if candidate.is_file() and candidate.suffix.lower() in _DISCOVERABLE_CONTENT_EXTENSIONS:
            files.append(candidate)
    return files


def _supported_content_files(root: Path, path: Path) -> list[Path]:
    return [
        candidate
        for candidate in _discoverable_content_files(root, path)
        if candidate.suffix.lower() in _CONTENT_EXTENSIONS
    ]


def _acceptance_query(body: str, label: str) -> str:
    for token in re.findall(r"[\w]+", body, flags=re.UNICODE):
        if len(token) >= 6 and not _PLACEHOLDER_RE.fullmatch(token):
            return token
    raise ValueError(
        f"content archive {label!r} has no searchable token of at least six characters"
    )


def _project_definition_text(purpose: str, stack: list[str]) -> str:
    rendered_stack = ", ".join(stack)
    return f"# Project definition\n\nPurpose: {purpose}\n\nWorking stack: {rendered_stack}\n"


def _scan_content_candidates(root: Path) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.name in _CONTENT_SCAN_EXCLUDES or child.name in _ROOT_CONTENT_EXCLUDES:
            continue
        if child.name.startswith("."):
            continue
        files = _discoverable_content_files(root, child)
        if not files:
            continue
        formats = sorted({path.suffix.lower().lstrip(".") for path in files})
        candidates.append(
            {
                "path": child.relative_to(root).as_posix(),
                "kind": "directory" if child.is_dir() else "file",
                "formats": formats,
                "document_count": len(files),
                "memory_indexable": any(
                    path.suffix.lower() in _CONTENT_EXTENSIONS for path in files
                ),
            }
        )
    return candidates


def _parse_content_archives(
    root: Path, raw_archives: list[str]
) -> list[dict[str, object]]:
    archives: list[dict[str, object]] = []
    seen_classifications: set[str] = set()
    resolved_paths: list[tuple[str, Path]] = []
    for raw in raw_archives:
        classification, separator, authored_path = raw.partition("=")
        classification = classification.strip().lower()
        if not separator or not _SLUG_RE.fullmatch(classification):
            raise ValueError(
                f"invalid --archive {raw!r}; expected lowercase CLASSIFICATION=PATH"
            )
        if classification in seen_classifications:
            raise ValueError(f"duplicate content classification: {classification}")
        path, relative = _project_relative(root, authored_path.strip())
        if not path.exists():
            raise ValueError(f"content archive path does not exist: {relative}")
        for prior_label, prior_path in resolved_paths:
            if path == prior_path or path in prior_path.parents or prior_path in path.parents:
                raise ValueError(
                    f"content archive paths overlap: {prior_label!r} and {classification!r}"
                )
        discovered_files = _discoverable_content_files(root, path)
        files = [
            candidate
            for candidate in discovered_files
            if candidate.suffix.lower() in _CONTENT_EXTENSIONS
        ]
        if not discovered_files:
            raise ValueError(f"content archive has no recognized record files: {relative}")
        if not files:
            formats = sorted(
                {candidate.suffix.lower().lstrip(".") for candidate in discovered_files}
            )
            raise ValueError(
                f"content archive {relative!r} contains only non-indexable formats {formats}; "
                "add a tracked UTF-8 text projection before bootstrap"
            )
        acceptance_path = files[0]
        try:
            acceptance_body = acceptance_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"content archive file is not UTF-8: {acceptance_path.relative_to(root)}"
            ) from exc
        archives.append(
            {
                "classification": classification,
                "path": relative,
                "kind": "directory" if path.is_dir() else "file",
                "formats": sorted(
                    {item.suffix.lower().lstrip(".") for item in discovered_files}
                ),
                "indexed_formats": sorted(
                    {item.suffix.lower().lstrip(".") for item in files}
                ),
                "document_count": len(discovered_files),
                "indexed_document_count": len(files),
                "acceptance": {
                    "query": _acceptance_query(acceptance_body, relative),
                    "expected_path": acceptance_path.relative_to(root).as_posix(),
                },
            }
        )
        seen_classifications.add(classification)
        resolved_paths.append((classification, path))
    return archives


def _build_content_onboarding(
    root: Path, purpose: str, stack: list[str], raw_archives: list[str]
) -> tuple[dict[str, object], str]:
    definition_body = _project_definition_text(purpose, stack)
    archives = [
        {
            "classification": "project-definition",
            "path": "docs/project-purpose.md",
            "kind": "file",
            "formats": ["md"],
            "indexed_formats": ["md"],
            "document_count": 1,
            "indexed_document_count": 1,
            "acceptance": {
                "query": _acceptance_query(definition_body, "project-definition"),
                "expected_path": "docs/project-purpose.md",
            },
        },
        *_parse_content_archives(root, raw_archives),
    ]
    candidates = _scan_content_candidates(root)
    classified_paths = [Path(str(item["path"])) for item in archives[1:]]
    unclassified = [
        candidate
        for candidate in candidates
        if not any(
            Path(str(candidate["path"])) == classified
            or classified in Path(str(candidate["path"])).parents
            for classified in classified_paths
        )
    ]
    return (
        {
            "schema_version": 1,
            "profile": "content_workspace",
            "purpose": purpose,
            "technology_stack": stack,
            "archives": archives,
            "scan": {"candidates": candidates, "unclassified": unclassified},
        },
        definition_body,
    )


def _load_content_onboarding(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid config/content-onboarding.json: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("config/content-onboarding.json schema_version must be 1")
    if raw.get("profile") != "content_workspace":
        raise ValueError("content onboarding manifest profile must be content_workspace")
    archives = raw.get("archives")
    scan = raw.get("scan")
    if not isinstance(archives, list) or not archives:
        raise ValueError("content onboarding manifest must contain classified archives")
    if not isinstance(scan, dict) or scan.get("unclassified"):
        raise ValueError("content onboarding manifest contains unclassified archive candidates")
    return raw


def _content_archive_globs(onboarding: dict[str, object]) -> list[str]:
    globs = {"docs/**/*.md", "tasks/**/*.md", ".ai-harness/**/*.md"}
    for item in onboarding.get("archives", []):
        if not isinstance(item, dict):
            continue
        relative = str(item.get("path", ""))
        if item.get("kind") == "file":
            globs.add(relative)
        else:
            for suffix in _CONTENT_EXTENSIONS:
                globs.add(f"{relative}/**/*{suffix}")
    return sorted(globs)


def _content_archive_args(onboarding: dict[str, object]) -> list[str]:
    return [
        f"{item['classification']}={item['path']}"
        for item in onboarding.get("archives", [])
        if isinstance(item, dict) and item.get("classification") != "project-definition"
    ]


def _memory_config_text(
    slug: str, profile: str, onboarding: dict[str, object] | None
) -> str:
    header = '''# Active portable memory baseline. Managed by `mir bootstrap` when absent.

[memory]
enabled = true
required = true
backend = "sqlite_fts5"
db_path = ".mir/memory.db"
vector_mode = "off"
plugin_mode = "disabled"
recall_policy = "progressive"

[memory.embedding]
enabled = false
required = false
'''
    if profile == "content_workspace":
        assert onboarding is not None
        globs = json.dumps(_content_archive_globs(onboarding), ensure_ascii=False)
        return header + f'''

[[memory.external_archives]]
slug = "{slug}-content"
root = "."
mode = "indexed"
glob_include = {globs}
'''
    return header + f'''

[[memory.external_archives]]
slug = "{slug}-docs"
root = "docs"
mode = "indexed"
glob_include = ["**/*.md"]

[[memory.external_archives]]
slug = "{slug}-tasks"
root = "tasks"
mode = "indexed"
glob_include = ["**/*.md"]

[[memory.external_archives]]
slug = "{slug}-rules"
root = ".ai-harness"
mode = "indexed"
glob_include = ["**/*.md"]
'''


def _repo_profile_text(
    root: Path, slug: str, profile: str, purpose: str, stack: list[str]
) -> str:
    root_value = json.dumps(str(root.resolve()), ensure_ascii=False)
    purpose_value = json.dumps(purpose, ensure_ascii=False)
    stack_value = json.dumps(stack, ensure_ascii=False)
    return f'''# Repository identity generated by `mir bootstrap`.

[repo]
slug = "{slug}"
display_name = "{slug.replace("-", " ").title()}"
path = {root_value}
repository_type = "starter_project"
rollout_class = "bootstrap_only"
overlay_archetype = "template_transitional"
status = "active"
purpose = {purpose_value}
technology_stack = {stack_value}
profile_base_commit = "unverified"
profile_verified_at = ""

[ownership]
main_role = "control_plane"
delegated_execution = "codex_first"
main_agent_contract = "shared_parity"
codex_backend_role = "code_tdd_review_plane"
codex_default_enabled = true
allow_role_override = true
override_requires_record = true

[paths]
code_paths = ["src/", "scripts/", "tools/"]
non_code_paths = ["docs/", "tasks/", ".ai-harness/", "README.md", "CLAUDE.md", "AGENTS.md"]
protected_paths = [".env", ".env.*", "secrets/**", ".mir/memory.db*"]
generated_paths = ["AGENTS.md", ".codex/**", "docs/memory-map.md", "tasks/lessons.md"]
architecture_refs = ["ARCHITECTURE.md", "docs/decisions/"]
configuration_paths = ["pyproject.toml", "config/"]
verification_paths = ["tests/"]
workflow_refs = ["CLAUDE.md", ".ai-harness/", ".claude/", "tasks/plan.md"]
exception_refs = [".mir/boundary.md", ".mir-preserve.toml"]

[preserve]
skills = []
claude_sections = []
agent_memory_paths = [".mir/memory.db"]
commands = []
extra_docs = []

[boundaries]
live_runtime = []
secrets = [".env", ".env.*", "secrets/**"]
data_sensitivity = "low"
release_window = "anytime"
external_services = []

[execution]
delegated_execution_contract = "subagents_codex_first"
delegation_required_tasks = ["adopter_wide_template_contract_or_bootstrap_change", "release_review"]
delegation_recommended_tasks = ["implementation", "tests", "independent_review"]
main_direct_tasks = ["small_documentation_change", "configuration_inspection", "final_judgment"]
codex_allowed_modes = ["code", "review", "tdd"]
codex_blocked_modes = []
review_scope = ["src/", "scripts/", "tools/", "tests/"]
tdd_scope = ["src/", "scripts/", "tools/"]
non_code_profile = "{profile}"

[gates]
requires_phase_gate = false
requires_secrets_vault = false
requires_dynamic_egress = false
requires_release_window = false
requires_external_store = true
requires_memory_store = true
requires_global_capabilities = true
'''


def _validate_existing_profile(path: Path, expected_profile: str) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid existing .mir/repo-profile.toml: {exc}") from exc
    repo = raw.get("repo", {})
    execution = raw.get("execution", {})
    purpose = repo.get("purpose") if isinstance(repo, dict) else None
    stack = repo.get("technology_stack") if isinstance(repo, dict) else None
    identity_errors = _validate_project_identity(
        purpose if isinstance(purpose, str) else None,
        [str(item) for item in stack] if isinstance(stack, list) else [],
    )
    if identity_errors:
        raise ValueError(
            "existing .mir/repo-profile.toml has incomplete project identity: "
            + "; ".join(identity_errors)
        )
    if not isinstance(execution, dict) or execution.get("non_code_profile") != expected_profile:
        raise ValueError(
            "existing .mir/repo-profile.toml profile does not match "
            f"--profile {expected_profile!r}"
        )
    gates = raw.get("gates", {})
    if (
        gates.get("requires_memory_store") is not True
        or gates.get("requires_global_capabilities") is not True
    ):
        raise ValueError(
            "existing .mir/repo-profile.toml must explicitly set "
            "[gates].requires_memory_store=true and requires_global_capabilities=true; "
            "bootstrap will not overwrite authored policy"
        )
    return raw


def _ensure_authored_files(
    root: Path,
    slug: str,
    profile: str,
    purpose: str,
    stack: list[str],
    onboarding: dict[str, object] | None,
    definition_body: str | None,
) -> None:
    (root / ".mir").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "tasks").mkdir(parents=True, exist_ok=True)
    (root / ".ai-harness").mkdir(parents=True, exist_ok=True)

    harness_path = root / "harness_a.toml"
    if not harness_path.exists():
        _atomic_write_text(harness_path, _memory_config_text(slug, profile, onboarding))

    profile_path = root / ".mir" / "repo-profile.toml"
    if not profile_path.exists():
        _atomic_write_text(
            profile_path,
            _repo_profile_text(root, slug, profile, purpose, stack),
        )

    if profile == "content_workspace":
        assert onboarding is not None and definition_body is not None
        onboarding_path = root / "config" / "content-onboarding.json"
        onboarding_path.parent.mkdir(parents=True, exist_ok=True)
        if onboarding_path.exists():
            _load_content_onboarding(onboarding_path)
        _atomic_write_json(onboarding_path, onboarding)
        definition_path = root / "docs" / "project-purpose.md"
        if not definition_path.exists():
            _atomic_write_text(definition_path, definition_body)

    tdd_path = root / "tasks" / "tdd.json"
    if not tdd_path.exists():
        _atomic_write_text(tdd_path, '{\n  "version": 1,\n  "changes": []\n}\n')
    plan_path = root / "tasks" / "plan.md"
    if not plan_path.exists():
        _atomic_write_text(plan_path, "# Plan\n\nNo active work.\n")


def _load_capability_sources(root: Path, profile: str) -> dict:
    path = root / "config" / "capability-sources.json"
    if not path.is_file():
        raise ValueError("tracked config/capability-sources.json is missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid config/capability-sources.json: {exc}") from exc
    if not isinstance(raw, dict) or not raw:
        raise ValueError("config/capability-sources.json must be a non-empty JSON object")
    source = raw.get("source")
    profiles = raw.get("profiles")
    if not isinstance(source, dict) or not source.get("url") or not source.get("ref"):
        raise ValueError("capability source must declare source.url and source.ref")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("capability source must declare non-empty profiles")
    packs = profiles.get("packs")
    aliases = profiles.get("aliases", {})
    selected = aliases.get(profile, profile) if isinstance(aliases, dict) else profile
    if not isinstance(packs, dict) or selected not in packs:
        raise ValueError(f"capability source has no pack for profile {profile!r}")
    return raw


def _activate_capabilities(root: Path, profile: str) -> tuple[str, dict]:
    try:
        from . import capability as capability_cli
    except ImportError as exc:
        return "failed", {"reason": f"capability CLI unavailable: {exc}"}
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        code = capability_cli.main(
            [
                "sync",
                "--profile",
                profile,
                "--project-root",
                str(root),
                "--apply",
                "--json",
            ]
        )
    if code != 0:
        return "failed", {"reason": output.getvalue().strip() or f"capability sync exited {code}"}
    return _capability_lock_evidence(root)


def _capability_lock_evidence(root: Path) -> tuple[str, dict]:
    lock_path = root / ".mir" / "capability-lock.json"
    if not lock_path.is_file():
        return "failed", {"reason": "capability sync did not write .mir/capability-lock.json"}
    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "failed", {"reason": f"invalid capability lock: {exc}"}
    if not isinstance(lock_data, dict):
        return "failed", {"reason": "capability lock must be a JSON object"}
    source = lock_data.get("source")
    plugins = lock_data.get("plugins")
    if (
        not isinstance(source, dict)
        or not re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit", "")))
        or not isinstance(plugins, dict)
        or not plugins
    ):
        return "failed", {"reason": "capability lock requires source.commit and non-empty plugins"}
    lock_hash = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    return "ready", {
        "lock_path": ".mir/capability-lock.json",
        "lock_sha256": lock_hash,
        "lock_version": lock_data.get("schema_version"),
        "source_commit": source["commit"],
        "profile": lock_data.get("profile"),
        "selected_plugins": sorted(plugins),
        "selected_agents": sorted(lock_data.get("agents", {})),
        "registration": lock_data.get("registration"),
    }


def _finalize_capabilities(root: Path, prior_receipt: dict | None) -> tuple[str, dict]:
    if not prior_receipt or prior_receipt.get("status") != "restart_required":
        return "failed", {
            "reason": "--finalize requires a prior restart_required bootstrap receipt"
        }
    try:
        from . import capability as capability_cli
    except ImportError as exc:
        return "failed", {"reason": f"capability CLI unavailable: {exc}"}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = capability_cli.main(
            [
                "finalize",
                "--project-root",
                str(root),
                "--apply",
                "--after-restart",
                "--json",
            ]
        )
    if code != 0:
        return "failed", {"reason": output.getvalue().strip() or f"capability status exited {code}"}
    status, evidence = _capability_lock_evidence(root)
    registration = evidence.get("registration")
    if not isinstance(registration, dict) or registration.get("status") != "active":
        return "failed", {"reason": "capability activation lock is not active"}
    return status, evidence


def _validate_architecture_evidence(root: Path) -> tuple[list[str], dict[str, object]]:
    evidence_path = root / "spec" / "bootstrap-evidence.json"
    lock_path = root / ".mir" / "capability-lock.json"
    errors: list[str] = []
    if evidence_path.is_symlink() or not evidence_path.is_file():
        return ["architecture evidence is missing: spec/bootstrap-evidence.json"], {}
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"architecture evidence or capability lock is invalid: {exc}"], {}
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 2:
        errors.append("architecture evidence schema_version must be 2")
        evidence = {}
    sequence = evidence.get("sequence")
    if sequence != list(_ARCHITECTURE_SEQUENCE):
        errors.append("architecture evidence must record design then spec-architect")
    source = lock.get("source") if isinstance(lock, dict) else None
    locked_commit = source.get("commit") if isinstance(source, dict) else None
    if evidence.get("capability_commit") != locked_commit or not isinstance(
        locked_commit, str
    ):
        errors.append("architecture evidence capability_commit does not match the lock")
    outputs = evidence.get("outputs")
    if outputs != list(_ARCHITECTURE_OUTPUTS):
        errors.append("architecture evidence must list the required spec outputs")

    coverage = evidence.get("coverage")
    expected_totals = {"l1": None, "l2": None, "l3": 9, "l4": 10}
    if not isinstance(coverage, dict):
        errors.append("architecture evidence must contain four-layer spec coverage")
        coverage = {}
    for layer, exact_total in expected_totals.items():
        row = coverage.get(layer)
        if not isinstance(row, dict):
            errors.append(f"architecture coverage is missing {layer}")
            continue
        values = {key: row.get(key) for key in ("total", "filled", "derived", "na", "tbd")}
        if any(not isinstance(value, int) or value < 0 for value in values.values()):
            errors.append(f"architecture coverage {layer} counts must be non-negative integers")
            continue
        total = values["total"]
        if total == 0 or (exact_total is not None and total != exact_total):
            expected = f"exactly {exact_total}" if exact_total is not None else "greater than zero"
            errors.append(f"architecture coverage {layer}.total must be {expected}")
        if values["filled"] + values["derived"] + values["na"] + values["tbd"] != total:
            errors.append(f"architecture coverage {layer} counts do not sum to total")
        if values["tbd"] != 0:
            errors.append(f"architecture coverage {layer} still contains TBD requirements")
    ai_ready = coverage.get("ai_ready")
    l1 = coverage.get("l1")
    l1_total = l1.get("total") if isinstance(l1, dict) else None
    if not isinstance(ai_ready, dict) or any(
        not isinstance(ai_ready.get(key), int) or ai_ready.get(key) < 0
        for key in ("ready", "incomplete", "blocked")
    ):
        errors.append("architecture coverage ai_ready counts are missing or invalid")
    elif (
        ai_ready["ready"] == 0
        or ai_ready["ready"] != l1_total
        or ai_ready["incomplete"] != 0
        or ai_ready["blocked"] != 0
    ):
        errors.append("all requirements must be AI-ready with no incomplete or blocked items")

    full_review = evidence.get("full_review")
    required_reviews = (
        "project_structure",
        "memory",
        "discoverability",
        "requirements",
        "organization",
    )
    if not isinstance(full_review, dict) or any(
        full_review.get(item) != "pass" for item in required_reviews
    ):
        errors.append("architecture evidence must record a passing full project review")

    output_hashes: dict[str, str] = {}
    for relative in _ARCHITECTURE_OUTPUTS:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"architecture output is missing or linked: {relative}")
            continue
        body = path.read_bytes()
        if not body.strip():
            errors.append(f"architecture output is empty: {relative}")
            continue
        if _PLACEHOLDER_RE.search(body.decode("utf-8", errors="replace")):
            errors.append(f"architecture output contains placeholder text: {relative}")
        output_hashes[relative] = hashlib.sha256(body).hexdigest()

    gaps_path = root / "spec" / "gaps.yaml"
    open_gaps = -1
    try:
        gaps_doc = yaml.safe_load(gaps_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        errors.append(f"spec/gaps.yaml is invalid: {exc}")
    else:
        gaps = gaps_doc.get("gaps") if isinstance(gaps_doc, dict) else None
        if not isinstance(gaps, list):
            errors.append("spec/gaps.yaml must contain a gaps list")
        else:
            open_gaps = sum(
                1
                for gap in gaps
                if not isinstance(gap, dict)
                or gap.get("status") not in {"resolved", "dismissed", "na"}
            )
            if open_gaps:
                errors.append(f"spec/gaps.yaml contains {open_gaps} open gap(s)")
    if evidence.get("open_gaps") != open_gaps or open_gaps != 0:
        errors.append("architecture evidence open_gaps must match spec/gaps.yaml and equal zero")

    for name in ("index.yaml", "graph.yaml"):
        path = root / "spec" / name
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            errors.append(f"spec/{name} is invalid: {exc}")
            continue
        if not isinstance(document, dict):
            errors.append(f"spec/{name} must be a mapping")
        elif name == "index.yaml":
            requirements = document.get("requirements")
            if not isinstance(requirements, list):
                errors.append("spec/index.yaml must contain a requirements list")
            elif len(requirements) != l1_total or any(
                not isinstance(requirement, dict)
                or requirement.get("status") != "ready"
                for requirement in requirements
            ):
                errors.append(
                    "spec/index.yaml requirements must match L1 total and all be ready"
                )
        elif name == "graph.yaml" and (
            not isinstance(document.get("nodes"), list)
            or not document.get("nodes")
            or not isinstance(document.get("edges"), list)
        ):
            errors.append("spec/graph.yaml must contain non-empty nodes and an edges list")
    return errors, {
        "path": "spec/bootstrap-evidence.json",
        "sequence": list(_ARCHITECTURE_SEQUENCE),
        "capability_commit": locked_commit,
        "coverage": coverage,
        "open_gaps": open_gaps,
        "full_review": full_review,
        "output_hashes": output_hashes,
    }


def _validate_json_file(path: Path) -> str | None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"invalid JSON surface {path}: {exc}"
    return None


def _validate_surfaces(root: Path) -> tuple[list[str], dict]:
    errors: list[str] = []
    required_files = (
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/settings.json",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".ai-harness/deny-list.yaml",
        ".claude/agents/main-orchestrator.md",
        ".codex/agents/main-orchestrator.toml",
        "config/sub-agent-policy.json",
        "config/capability-sources.json",
    )
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"required harness surface is missing: {relative}")
    for relative in (
        ".claude/settings.json",
        ".codex/hooks.json",
        "config/sub-agent-policy.json",
        "config/capability-sources.json",
    ):
        path = root / relative
        if path.is_file():
            error = _validate_json_file(path)
            if error:
                errors.append(error)
    if not any((root / ".claude" / "agents").glob("*.md")):
        errors.append("Claude sub-agent registry is empty")
    if not any((root / ".codex" / "agents").glob("*.toml")):
        errors.append("Codex sub-agent registry is empty")
    if not any((root / ".claude" / "hooks").glob("*.sh")):
        errors.append("Claude hook registry is empty")

    settings_path = root / ".claude" / "settings.json"
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            if not isinstance(settings.get("hooks"), dict) or not settings["hooks"]:
                errors.append(".claude/settings.json has no active hooks")
        except (OSError, json.JSONDecodeError):
            pass
    codex_config = root / ".codex" / "config.toml"
    if codex_config.is_file():
        config_text = codex_config.read_text(encoding="utf-8")
        for field in ("approval_policy", "sandbox_mode"):
            if not re.search(rf"(?m)^{field}\s*=", config_text):
                errors.append(f".codex/config.toml is missing {field}")

    hook_runtime = {
        "kind": "bash",
        "required_on_windows": True,
        "bash": "not_checked",
        "jq": "not_checked",
        "syntax": "not_checked",
    }
    representative_hook = root / ".claude" / "hooks" / "session-start.sh"
    bash_path = shutil.which("bash")
    jq_path = shutil.which("jq")
    hook_runtime["jq"] = jq_path or "missing"
    if jq_path is None:
        errors.append("hook runtime requires jq on PATH for JSON payload parsing")
    if platform.system() == "Windows":
        if bash_path is None:
            errors.append("Windows hook runtime requires bash from Git for Windows or WSL on PATH")
            hook_runtime["bash"] = "missing"
        elif not representative_hook.is_file():
            errors.append("representative Bash hook is missing: .claude/hooks/session-start.sh")
        else:
            result = subprocess.run(
                [bash_path, "-n", str(representative_hook)],
                check=False,
                capture_output=True,
                text=True,
            )
            hook_runtime["bash"] = bash_path
            hook_runtime["syntax"] = "ok" if result.returncode == 0 else "failed"
            if result.returncode != 0:
                errors.append(
                    "Windows Bash hook syntax check failed: "
                    + (result.stderr.strip() or f"exit {result.returncode}")
                )
    else:
        hook_runtime["bash"] = bash_path or "not_required_for_bootstrap"
        hook_runtime["syntax"] = "not_required"
    return errors, hook_runtime


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.close(descriptor)
        temp_path = Path(temp_name)
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path = Path(temp_name)
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.close(descriptor)
        temp_path = Path(temp_name)
        temp_path.write_text(body, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path = Path(temp_name)
        if temp_path.exists():
            temp_path.unlink()


def _stage_memory_db(db_path: Path) -> Path:
    """Create an isolated SQLite snapshot so a failed bootstrap cannot mutate the live index."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=".memory.bootstrap.", suffix=".db", dir=db_path.parent
    )
    os.close(descriptor)
    staged_path = Path(staged_name)
    if not db_path.exists():
        return staged_path
    source = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    destination = sqlite3.connect(staged_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return staged_path


def _build_projection_updates(root: Path, db_path: Path) -> dict[Path, str]:
    connection = store.connect(db_path)
    try:
        targets = {
            root / "docs" / "memory-map.md": memory_cli._render_memory_map_section(connection.conn),
            root / "tasks" / "lessons.md": memory_cli._render_lessons_section(connection.conn),
        }
    finally:
        connection.conn.close()
    updates: dict[Path, str] = {}
    for path, generated_body in targets.items():
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        updates[path] = memory_cli._inject_markers(existing, generated_body)
    return updates


def _validate_content_memory_acceptance(
    root: Path,
    db_path: Path,
    slug: str,
    onboarding: dict[str, object],
) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    results: list[dict[str, object]] = []
    expected_archive = f"{slug}-content"
    connection = store.connect(db_path)
    try:
        for archive in onboarding.get("archives", []):
            if not isinstance(archive, dict):
                errors.append("content onboarding archive entry must be an object")
                continue
            acceptance = archive.get("acceptance")
            if not isinstance(acceptance, dict):
                errors.append(
                    f"content classification {archive.get('classification')!r} lacks acceptance"
                )
                continue
            query = acceptance.get("query")
            expected_path = acceptance.get("expected_path")
            if not isinstance(query, str) or not isinstance(expected_path, str):
                classification = archive.get("classification")
                errors.append(
                    f"content classification {classification!r} has invalid acceptance"
                )
                continue
            row = connection.conn.execute(
                "SELECT a.slug, d.relative_path "
                "FROM external_chunks_fts f "
                "JOIN external_chunks c ON c.id = f.rowid "
                "JOIN external_documents d ON d.id = c.document_id "
                "JOIN external_archives a ON a.id = d.archive_id "
                "WHERE external_chunks_fts MATCH ? "
                "AND a.slug = ? AND d.relative_path = ? LIMIT 1",
                (query, expected_archive, expected_path),
            ).fetchone()
            passed = row is not None
            results.append(
                {
                    "classification": archive.get("classification"),
                    "query": query,
                    "expected_path": expected_path,
                    "status": "pass" if passed else "fail",
                }
            )
            if not passed:
                errors.append(
                    "project-specific memory query returned no matching path for "
                    f"{archive.get('classification')!r}: {query!r} -> {expected_path!r}"
                )
    finally:
        connection.conn.close()
    return errors, {
        "status": "pass" if not errors else "fail",
        "manifest": "config/content-onboarding.json",
        "archive_slug": expected_archive,
        "classifications": [
            {
                "classification": item.get("classification"),
                "path": item.get("path"),
                "formats": item.get("formats"),
                "document_count": item.get("document_count"),
                "indexed_document_count": item.get("indexed_document_count"),
            }
            for item in onboarding.get("archives", [])
            if isinstance(item, dict)
        ],
        "queries": results,
    }


def _emit(ns: argparse.Namespace, receipt: dict) -> None:
    if ns.json:
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    else:
        print(f"mir bootstrap: {receipt['status']}")
        for error in receipt.get("errors", []):
            print(f"  [not-ready] {error}")
        if receipt["status"] == "restart_required":
            print("  selected global plugins are installed and hash-verified")
            print("  restart Claude Code and begin a new Codex session")
            print("  attest the namespaced skill catalog once from each runtime")
            print("  run mir-core:design then mir-core:spec-architect, then finalize")
        print("  receipt: .mir/bootstrap-receipt.json")


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    root = ns.project_root.expanduser().resolve(strict=False)
    if not root.is_dir():
        print(f"project root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        slug = _normalise_slug(ns.slug or root.name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    profile = _PROFILE_ALIASES.get(ns.profile, ns.profile)
    if profile not in _PROFILE_CHOICES:
        print(
            f"unknown profile {ns.profile!r}; choose one of {', '.join(_PROFILE_CHOICES)}",
            file=sys.stderr,
        )
        return 2

    purpose = ns.purpose.strip() if isinstance(ns.purpose, str) else None
    stack = _normalise_stack(ns.stack)
    onboarding: dict[str, object] | None = None
    definition_body: str | None = None

    errors: list[str] = []
    invalid_config = False
    capability: dict = {"status": "not_checked"}
    memory_report: dict = {}
    hook_runtime: dict = {}
    projection_updates: dict[Path, str] = {}
    working_db_path: Path | None = None
    staged_db = False
    architecture_evidence: dict[str, object] = {}
    architecture_attested = False
    content_acceptance: dict[str, object] = {"status": "not_required"}
    storage_errors, storage_report = _storage_preflight(root, ns.storage_root)
    if storage_errors:
        errors.extend(storage_errors)
        invalid_config = True
    receipt_path = root / ".mir" / "bootstrap-receipt.json"
    prior_receipt = None
    if receipt_path.is_file():
        try:
            candidate = json.loads(receipt_path.read_text(encoding="utf-8"))
            prior_receipt = candidate if isinstance(candidate, dict) else None
        except (OSError, json.JSONDecodeError):
            prior_receipt = None

    onboarding_path = root / "config" / "content-onboarding.json"
    if ns.finalize:
        if profile == "content_workspace":
            if not onboarding_path.is_file():
                errors.append(
                    "content_workspace finalize requires config/content-onboarding.json"
                )
                invalid_config = True
            else:
                try:
                    onboarding = _load_content_onboarding(onboarding_path)
                    manifest_purpose = onboarding.get("purpose")
                    manifest_stack = onboarding.get("technology_stack")
                    if not isinstance(manifest_purpose, str) or not isinstance(
                        manifest_stack, list
                    ):
                        raise ValueError(
                            "content onboarding manifest requires purpose and technology_stack"
                        )
                    purpose = manifest_purpose
                    stack = [str(item) for item in manifest_stack]
                    definition_body = _project_definition_text(purpose, stack)
                    if ns.purpose and ns.purpose.strip() != purpose:
                        raise ValueError("--purpose conflicts with content onboarding manifest")
                    if ns.stack and _normalise_stack(ns.stack) != stack:
                        raise ValueError("--stack conflicts with content onboarding manifest")
                    refreshed, _ = _build_content_onboarding(
                        root,
                        purpose,
                        stack,
                        _content_archive_args(onboarding),
                    )
                    if refreshed != onboarding:
                        raise ValueError(
                            "content onboarding manifest is stale; rerun Phase 1 with all "
                            "--archive classifications before finalize"
                        )
                except ValueError as exc:
                    errors.append(str(exc))
                    invalid_config = True
    else:
        identity_errors = _validate_project_identity(purpose, stack)
        if identity_errors:
            errors.extend(identity_errors)
            invalid_config = True
        elif profile == "content_workspace":
            try:
                if onboarding_path.is_file() and not ns.archive:
                    existing_onboarding = _load_content_onboarding(onboarding_path)
                    if existing_onboarding.get("purpose") != purpose or existing_onboarding.get(
                        "technology_stack"
                    ) != stack:
                        raise ValueError(
                            "bootstrap identity conflicts with config/content-onboarding.json"
                        )
                    onboarding, definition_body = _build_content_onboarding(
                        root,
                        purpose or "",
                        stack,
                        _content_archive_args(existing_onboarding),
                    )
                else:
                    onboarding, definition_body = _build_content_onboarding(
                        root, purpose or "", stack, ns.archive
                    )
                unclassified = onboarding.get("scan", {}).get("unclassified", [])
                if unclassified:
                    paths = ", ".join(
                        f"{item.get('path')} [{', '.join(item.get('formats', []))}]"
                        for item in unclassified
                        if isinstance(item, dict)
                    )
                    raise ValueError(
                        "unclassified existing content detected; rerun with "
                        f"--archive CLASSIFICATION=PATH for: {paths}"
                    )
            except ValueError as exc:
                errors.append(str(exc))
                invalid_config = True
        elif ns.archive:
            errors.append("--archive is supported only with --profile content_workspace")
            invalid_config = True

    if not (os.environ.get("VIRTUAL_ENV") or sys.prefix != sys.base_prefix):
        errors.append("mir bootstrap must run inside `uv run` after the wrapper executes `uv sync`")

    # Read-only preflight: do not create config, DBs, or projections when the
    # copied harness surfaces or existing authored policy are invalid.
    surface_errors, hook_runtime = _validate_surfaces(root)
    errors.extend(surface_errors)
    try:
        _load_capability_sources(root, profile)
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        invalid_config = True
    existing_profile = root / ".mir" / "repo-profile.toml"
    if existing_profile.exists():
        try:
            profile_data = _validate_existing_profile(existing_profile, profile)
            repo_data = profile_data.get("repo", {})
            if ns.finalize and isinstance(repo_data, dict):
                profile_purpose = repo_data.get("purpose")
                profile_stack = repo_data.get("technology_stack")
                if purpose is not None and profile_purpose != purpose:
                    raise ValueError(
                        "project purpose conflicts between profile and onboarding manifest"
                    )
                if stack and profile_stack != stack:
                    raise ValueError(
                        "project stack conflicts between profile and onboarding manifest"
                    )
                purpose = str(profile_purpose)
                stack = [str(item) for item in profile_stack]
        except ValueError as exc:
            errors.append(str(exc))
            invalid_config = True
    elif ns.finalize:
        errors.append("--finalize requires the phase 1 .mir/repo-profile.toml")
        invalid_config = True
    existing_harness = root / "harness_a.toml"
    if existing_harness.exists():
        try:
            load_config(root)
        except ConfigLoadError as exc:
            errors.append(str(exc))
            invalid_config = True

    cfg = None
    db_path = root / ".mir" / "memory.db"
    if not errors:
        try:
            assert purpose is not None and stack
            _ensure_authored_files(
                root,
                slug,
                profile,
                purpose,
                stack,
                onboarding,
                definition_body,
            )
            cfg = load_config(root)
            if not cfg.memory.enabled or not cfg.memory.required:
                errors.append("bootstrap requires memory enabled=true and required=true")
            db_path = resolve_memory_db(root, cfg)
            working_db_path = _stage_memory_db(db_path)
            staged_db = True
        except (ConfigLoadError, OSError, ValueError) as exc:
            errors.append(str(exc))
            invalid_config = True

    if cfg is not None and not errors:
        try:
            assert working_db_path is not None
            connection = store.connect(working_db_path)
            try:
                store.apply_migrations(connection.conn)
                if cfg.memory.vector_mode == "required":
                    connection.conn.execute(
                        "DELETE FROM external_store_meta "
                        "WHERE key LIKE 'schema_metadata_version:archive:%'"
                    )
                    connection.conn.commit()
            finally:
                connection.conn.close()

            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                sync_code = context_cli.main(
                    [
                        "sync",
                        "--db",
                        str(working_db_path),
                        "--project-root",
                        str(root),
                    ]
                )
            if sync_code != 0:
                errors.append(
                    "memory archive sync failed: "
                    + (captured.getvalue().strip() or f"exit {sync_code}")
                )
        except Exception as exc:
            errors.append(f"memory bootstrap failed: {exc}")

        if not errors:
            doctor_code, memory_report = memory_cli.run_doctor(root, db_override=working_db_path)
            if doctor_code != 0:
                errors.extend(
                    f"memory doctor: {message}"
                    for message in memory_report.get("errors", [])
                    if f"memory doctor: {message}" not in errors
                )
            else:
                try:
                    projection_updates = _build_projection_updates(root, working_db_path)
                except Exception as exc:
                    errors.append(f"memory projection preparation failed: {exc}")
                if profile == "content_workspace" and not errors:
                    assert onboarding is not None
                    acceptance_errors, content_acceptance = _validate_content_memory_acceptance(
                        root, working_db_path, slug, onboarding
                    )
                    errors.extend(acceptance_errors)

    if ns.skip_capability_activation:
        capability = {"status": "skipped", "reason": "explicit test/development boundary"}
        if not ns.allow_incomplete:
            errors.append("capability activation was skipped; bootstrap cannot be ready")
    elif not errors:
        if ns.finalize:
            if not ns.architecture_initialized:
                capability_status = "failed"
                evidence = {
                    "reason": "--finalize requires --architecture-initialized after "
                    "explicit mir-core:design then mir-core:spec-architect execution"
                }
            else:
                architecture_errors, architecture_evidence = _validate_architecture_evidence(root)
                if architecture_errors:
                    capability_status = "failed"
                    evidence = {"reason": "; ".join(architecture_errors)}
                else:
                    capability_status, evidence = _finalize_capabilities(root, prior_receipt)
                    architecture_attested = capability_status == "ready"
            capability = {"status": capability_status, **evidence}
        else:
            capability_status, evidence = _activate_capabilities(root, profile)
            capability = {
                "status": "restart_required" if capability_status == "ready" else capability_status,
                **evidence,
            }
        if capability_status != "ready":
            errors.append(f"capability activation failed: {evidence.get('reason', 'unknown')}")
    else:
        capability = {"status": "not_run", "reason": "preflight or memory failure"}

    unique_errors = list(dict.fromkeys(errors))
    complete = not unique_errors and capability.get("status") == "ready"
    restart_required = not unique_errors and capability.get("status") == "restart_required"
    allowed_incomplete = bool(
        not unique_errors and ns.allow_incomplete and ns.skip_capability_activation
    )
    if not unique_errors and (complete or restart_required or allowed_incomplete):
        try:
            if staged_db:
                assert working_db_path is not None
                for suffix in ("-shm", "-wal"):
                    Path(f"{db_path}{suffix}").unlink(missing_ok=True)
                os.replace(working_db_path, db_path)
                working_db_path = db_path
            for output_path, body in projection_updates.items():
                _atomic_write_text(output_path, body)
        except OSError as exc:
            unique_errors.append(f"memory projection publish failed: {exc}")
            complete = False
            allowed_incomplete = False
    if staged_db and working_db_path is not None and working_db_path != db_path:
        for suffix in ("", "-shm", "-wal"):
            staged_artifact = Path(f"{working_db_path}{suffix}")
            if staged_artifact.exists():
                staged_artifact.unlink()
    if complete:
        status = "ready"
    elif restart_required:
        status = "restart_required"
    else:
        status = "incomplete"
    receipt = {
        "schema_version": 1,
        "status": status,
        "project_slug": slug,
        "profile": profile,
        "platform": {
            "os": platform.system().lower(),
            "release": platform.release(),
            "python": platform.python_version(),
            "hook_runtime": hook_runtime,
        },
        "storage": storage_report,
        "memory": {
            **memory_report.get("memory", {}),
            "topology": "per_repository_sqlite_fts5",
            "portable_sources": "tracked_markdown_archives_reindexable_cross_machine",
            "shared_database_or_vector_service": "unsupported",
        },
        "content_onboarding": content_acceptance,
        "vector": memory_report.get("vector", {}),
        "shared_embedding_endpoint": "optional",
        "capabilities": capability,
        "architecture_initialization": {
            "required": True,
            "sequence": list(_ARCHITECTURE_SEQUENCE),
            "applies_regardless_of_first_request_type": True,
            "attested": architecture_attested,
            "evidence": architecture_evidence,
        },
        "errors": unique_errors,
    }
    _atomic_write_json(receipt_path, receipt)
    _emit(ns, receipt)
    if complete or restart_required or allowed_incomplete:
        return 0
    return 2 if invalid_config else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
