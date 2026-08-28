"""macOS, Linux, and WSL coordinator for a ready Mir project baseline."""

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
from urllib.parse import urlsplit

import yaml

from mir.core.adoption import (
    SlimError,
    apply_adopter_slim,
    commit_adopter_slim,
    rollback_adopter_slim,
)
from mir.core.adoption.boundary import is_provider_owner, load_boundary, load_profile
from mir.core.config.loader import ConfigLoadError, load_config, resolve_memory_db
from mir.core.engine.memory import store

from . import context as context_cli
from . import memory as memory_cli
from ._changes import changed_paths, snapshot_project

_PROFILE_CHOICES = ("code_app", "hybrid_pipeline", "infra_runtime", "content_workspace")
_PROFILE_ALIASES = {"hybrid": "hybrid_pipeline", "infra": "infra_runtime"}
_PROFILE_CODE_PATHS = {
    "code_app": ["app/", "apps/", "packages/"],
    "hybrid_pipeline": ["app/", "apps/", "packages/", "pipelines/"],
    "infra_runtime": ["infra/", "scripts/"],
    "content_workspace": ["content/", "docs/"],
}
_CATALOG_TEMPLATE_BY_PROFILE = {
    "code_app": "code_app",
    "hybrid_pipeline": "hybrid_pipeline",
    "infra_runtime": "infra_runtime",
    "content_workspace": "ontology_content",
}
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
    "MIR_CAPABILITY_HOME": Path("mir/capabilities"),
}
_NATIVE_WINDOWS_GUIDANCE = (
    "Native Windows automated bootstrap is unsupported. "
    "Run setup.sh inside WSL, or use agent-guided existing-repository/reference adaptation."
)
_UNSUPPORTED_PLATFORM_GUIDANCE = (
    "Automated bootstrap supports macOS, Linux, and WSL. "
    "Use agent-guided existing-repository/reference adaptation on this platform."
)
_GIT_OWNERSHIP_GUIDANCE = (
    "Git push remote still targets the Mir Yoke provider. "
    "Rename it (for example: git remote rename origin mir-yoke-upstream), "
    "disable provider pushes (git remote set-url --push mir-yoke-upstream DISABLED), "
    "then optionally add a product-owned origin."
)


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
        help="shared external-volume root configured by setup.sh",
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
                f"{name} is not configured; invoke bootstrap through setup.sh "
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

    runtime_id = os.environ.get("MIR_BOOTSTRAP_RUNTIME_ID", "")
    runtime_root = (storage_root / "mir" / "cli" / runtime_id).resolve(strict=False)
    for name, leaf in (("UV_TOOL_DIR", "tools"), ("UV_TOOL_BIN_DIR", "bin")):
        raw = os.environ.get(name)
        if not raw:
            errors.append(
                f"{name} is not configured; invoke bootstrap through setup.sh "
                "with --storage-root"
            )
            continue
        actual = Path(raw).expanduser().resolve(strict=False)
        report["large_payloads"][name] = str(actual)
        expected = runtime_root / leaf
        if not runtime_id or actual != expected:
            errors.append(
                f"{name} must use the setup-derived project runtime under "
                f"{storage_root / 'mir' / 'cli'}, got {actual}"
            )
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
            len(configured_paths) == len(_EXTERNAL_STORAGE_PATHS) + 2
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
    root: Path,
    slug: str,
    profile: str,
    purpose: str,
    stack: list[str],
    *,
    base_commit: str = "unverified",
) -> str:
    root_value = json.dumps(str(root.resolve()), ensure_ascii=False)
    purpose_value = json.dumps(purpose, ensure_ascii=False)
    stack_value = json.dumps(stack, ensure_ascii=False)
    code_paths = json.dumps(_PROFILE_CODE_PATHS[profile])
    return f'''# Repository identity generated by `mir bootstrap`.

[repo]
slug = "{slug}"
display_name = "{slug.replace("-", " ").title()}"
path = {root_value}
repository_type = "{profile}"
overlay_archetype = "product_adopter"
status = "active"
purpose = {purpose_value}
technology_stack = {stack_value}
profile_base_commit = "{base_commit}"
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
code_paths = {code_paths}
non_code_paths = ["docs/", "tasks/", ".ai-harness/", "README.md", "CLAUDE.md", "AGENTS.md"]
protected_paths = [
  ".env", ".env.*", "secrets/**", ".mir/memory.db*",
  ".mir/bootstrap-receipt.json",
  ".mir/capability-lock.json",
  "config/adopter-boundary.json", "config/adopter-payload.json",
  "profiles/**", "playwright/.auth/**", "state/**", "logs/**",
]
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
review_scope = {code_paths}
tdd_scope = {code_paths}
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
    *,
    replace_provider_profile: bool = False,
) -> None:
    authored_directories = [
        root / relative for relative in (".mir", "docs", "tasks", ".ai-harness")
    ]
    for directory in authored_directories:
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError(
                "bootstrap authored directory is unsafe: "
                + directory.relative_to(root).as_posix()
            )
    for directory in authored_directories:
        directory.mkdir(parents=True, exist_ok=True)

    harness_path = root / "harness_a.toml"
    if not harness_path.exists():
        _atomic_write_text(harness_path, _memory_config_text(slug, profile, onboarding))

    profile_path = root / ".mir" / "repo-profile.toml"
    if not profile_path.exists() or replace_provider_profile:
        base_commit = "unverified"
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", candidate):
            base_commit = candidate
        _atomic_write_text(
            profile_path,
            _repo_profile_text(
                root,
                slug,
                profile,
                purpose,
                stack,
                base_commit=base_commit,
            ),
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

    if replace_provider_profile:
        _reset_provider_contract_state(root, slug, profile, purpose)
        _reset_provider_task_state(root, purpose)

    tdd_path = root / "tasks" / "tdd.json"
    if not tdd_path.exists():
        _atomic_write_text(tdd_path, '{\n  "version": 1,\n  "changes": []\n}\n')
    plan_path = root / "tasks" / "plan.md"
    if not plan_path.exists():
        _atomic_write_text(plan_path, "# Plan\n\nNo active work.\n")


def _release_payload_digests(root: Path) -> dict[str, str]:
    payload_path = root / "config" / "adopter-payload.json"
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(item.get("path")): str(item.get("sha256"))
        for item in payload.get("files", [])
        if isinstance(item, dict)
    }


def _is_safe_existing_project_file(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root)
        relative = path.relative_to(root)
    except (OSError, ValueError):
        return False
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return False
    return path.is_file()


def _is_raw_provider_checkout(root: Path) -> bool:
    """Recognize only an unprofiled, Git-bound Mir Yoke release checkout."""
    try:
        boundary = load_boundary(root)
    except (OSError, ValueError):
        return False
    payload_path = root / "config" / "adopter-payload.json"
    controls = (root / "config" / "adopter-boundary.json", payload_path)
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        return False
    for control in controls:
        relative = control.relative_to(root).as_posix()
        release = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if release.returncode != 0 or not _is_safe_existing_project_file(root, control):
            return False
        if control.read_bytes() != release.stdout:
            return False
    digests = _release_payload_digests(root)
    contract = root / "CLAUDE.md"
    if (
        not _is_safe_existing_project_file(root, contract)
        or hashlib.sha256(contract.read_bytes()).hexdigest() != digests.get("CLAUDE.md")
    ):
        return False
    text_markers = boundary.get("provider_text_markers", [])
    has_provider_contract = any(
        isinstance(marker, dict)
        and marker.get("path") == "CLAUDE.md"
        and isinstance(marker.get("contains"), str)
        and str(marker["contains"]) in contract.read_text(encoding="utf-8")
        for marker in text_markers
    )
    marker_paths = boundary.get("provider_markers", [])
    has_provider_payload = any(
        isinstance(relative, str)
        and ((root / relative).exists() or (root / relative).is_symlink())
        for relative in marker_paths
    )
    return has_provider_contract and has_provider_payload


def _rewrite_release_matched(
    root: Path, updates: dict[str, str]
) -> list[str]:
    entries = _release_payload_digests(root)
    changed: list[str] = []
    for relative, body in updates.items():
        path = root / relative
        expected = entries.get(relative)
        if not expected or not _is_safe_existing_project_file(root, path):
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            _atomic_write_text(path, body)
            changed.append(relative)
    return changed


def _normalise_git_url(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw):
        try:
            parsed = urlsplit(raw)
            host = (parsed.hostname or "").lower()
            port = parsed.port
        except ValueError:
            normalised = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://", "", raw)
            normalised = re.sub(r"^[^@/]+@", "", normalised)
        else:
            if port and not (
                (parsed.scheme.lower() == "ssh" and port == 22)
                or (parsed.scheme.lower() == "https" and port == 443)
            ):
                host = f"{host}:{port}"
            normalised = f"{host}/{parsed.path.lstrip('/')}"
    else:
        normalised = re.sub(r"^[^@/]+@", "", raw)
        normalised = re.sub(r"^([^/:]+):", r"\1/", normalised)
    normalised = re.sub(r"\.git/?$", "", normalised).rstrip("/")
    return normalised.lower()


def _source_control_ownership(root: Path) -> tuple[list[str], dict[str, object]]:
    config_path = root / "config" / "capability-sources.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["Git ownership cannot be verified: provider source is unavailable."], {
            "status": "provider_source_unavailable"
        }
    source = config.get("source", {}) if isinstance(config, dict) else {}
    provider_url = source.get("url") if isinstance(source, dict) else None
    if not isinstance(provider_url, str) or not provider_url:
        return ["Git ownership cannot be verified: provider source is unavailable."], {
            "status": "provider_source_unavailable"
        }
    provider_identity = _normalise_git_url(provider_url)
    remotes = subprocess.run(
        ["git", "remote"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if remotes.returncode != 0:
        return [], {"status": "local_only", "provider": provider_identity, "remotes": []}
    evidence: list[dict[str, object]] = []
    provider_push_remotes: list[str] = []
    for remote in sorted(filter(None, (line.strip() for line in remotes.stdout.splitlines()))):
        completed = subprocess.run(
            ["git", "remote", "get-url", "--push", "--all", remote],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        push_urls = (
            sorted(filter(None, (line.strip() for line in completed.stdout.splitlines())))
            if completed.returncode == 0
            else []
        )
        evidence.append(
            {
                "name": remote,
                "push_destinations": sorted(_normalise_git_url(url) for url in push_urls),
            }
        )
        if any(_normalise_git_url(url) == provider_identity for url in push_urls):
            provider_push_remotes.append(remote)
    if provider_push_remotes:
        names = ", ".join(provider_push_remotes)
        return [f"{_GIT_OWNERSHIP_GUIDANCE} Provider push remote(s): {names}."], {
            "status": "provider_push_rejected",
            "provider": provider_identity,
            "remotes": evidence,
        }
    return [], {
        "status": "product_owned" if evidence else "local_only",
        "provider": provider_identity,
        "remotes": evidence,
    }


def _product_contract_text(slug: str, profile: str, purpose: str) -> str:
    return f'''# {slug} — Repository Contract

## Outcome and completion

- Build and maintain this repository for: {purpose}
- Finish when the requested product outcome and the smallest relevant checks pass.

## Sources

- `.mir/repo-profile.toml` owns identity, paths, protected scope, and execution boundaries.
- Product requirements and architecture under `spec/` are authoritative after Phase 2.
- Use `scripts/mir.sh context pull "<query>"` for task-scoped retained context.

## Authority and safety

- Read/review requests are non-mutating; change requests authorize only scoped local edits.
- Get explicit direction before destructive actions, secrets, external writes, or scope expansion.
- Edit canonical sources first and regenerate `AGENTS.md` and `.codex/` derivatives.
- Mir Yoke provider source is external; do not add `src/mir`, provider plugins, or maintainer tests.

## Execution and evidence

- Product profile: `{profile}`. Prefer paths declared by the Profile.
- Run the smallest check that can fail for changed behavior; broaden only for coupled risk.
- Existing-repository adoption is receipt-only; greenfield slim runs only during final bootstrap.

Commands: `scripts/mir.sh capability status --project-root . --json`,
`scripts/mir.sh memory doctor --project-root . --json`, and product-owned test commands.
'''


def _compile_adopter_agent_catalog(root: Path, profile: str) -> list[str]:
    """Replace the provider catalog with the selected external capability surface."""
    path = root / "config" / "repo-agent-management.json"
    expected = _release_payload_digests(root).get("config/repo-agent-management.json")
    if (
        not expected
        or not _is_safe_existing_project_file(root, path)
        or hashlib.sha256(path.read_bytes()).hexdigest() != expected
    ):
        return []
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid repository agent catalog: {exc}") from exc
    if not isinstance(catalog, dict):
        raise ValueError("repository agent catalog must be a JSON object")

    capabilities = _load_capability_sources(root, profile)
    profiles = capabilities.get("profiles", {})
    aliases = profiles.get("aliases", {}) if isinstance(profiles, dict) else {}
    packs = profiles.get("packs", {}) if isinstance(profiles, dict) else {}
    selected_profile = aliases.get(profile, profile) if isinstance(aliases, dict) else profile
    pack = packs.get(selected_profile) if isinstance(packs, dict) else None
    plugins = capabilities.get("plugins")
    if not isinstance(pack, dict) or not isinstance(plugins, dict):
        raise ValueError(f"capability source has no usable pack for profile {profile!r}")

    selected_agent_slugs = {
        Path(relative).stem
        for relative in pack.get("agents", [])
        if isinstance(relative, str)
    }
    selected_skill_slugs = {
        skill
        for plugin_name in pack.get("plugins", [])
        if isinstance(plugin_name, str)
        for skill in (
            plugins.get(plugin_name, {}).get("skills", [])
            if isinstance(plugins.get(plugin_name), dict)
            else []
        )
        if isinstance(skill, str)
    }

    inventory = catalog.get("catalog")
    templates = catalog.get("templates")
    template_name = _CATALOG_TEMPLATE_BY_PROFILE[profile]
    if not isinstance(inventory, dict) or not isinstance(templates, dict):
        raise ValueError("repository agent catalog is missing catalog or templates")
    agents = inventory.get("agents")
    skills = inventory.get("skills")
    template = templates.get(template_name)
    if not isinstance(agents, dict) or not isinstance(skills, dict) or not isinstance(
        template, dict
    ):
        raise ValueError(f"repository agent catalog has no template for {profile!r}")

    selected_agents = {
        slug: metadata
        for slug, metadata in agents.items()
        if slug in selected_agent_slugs and isinstance(metadata, dict)
    }
    if set(selected_agents) != selected_agent_slugs:
        missing = sorted(selected_agent_slugs - set(selected_agents))
        raise ValueError(f"repository agent catalog is missing selected agents: {missing}")
    selected_skills = {
        slug: {**metadata, "status": "external", "source_path": "external"}
        for slug, metadata in skills.items()
        if slug in selected_skill_slugs and isinstance(metadata, dict)
    }
    if set(selected_skills) != selected_skill_slugs:
        missing = sorted(selected_skill_slugs - set(selected_skills))
        raise ValueError(f"repository agent catalog is missing selected skills: {missing}")
    for metadata in selected_agents.values():
        recommended = metadata.get("recommended_skills")
        if isinstance(recommended, list):
            metadata["recommended_skills"] = [
                skill for skill in recommended if skill in selected_skills
            ]

    roles = {
        role: [
            slug
            for slug, metadata in selected_agents.items()
            if metadata.get("role") == role
        ]
        for role in ("control_plane", "execution", "review", "specialist")
    }
    if len(roles["control_plane"]) != 1 or len(roles["execution"]) > 1:
        raise ValueError(
            "selected adopter catalog requires one orchestrator and at most one executor"
        )
    agent_pack = {
        "orchestrator": roles["control_plane"][0],
        "reviewers": roles["review"],
        "specialists": roles["specialist"],
    }
    if roles["execution"]:
        agent_pack["executor"] = roles["execution"][0]
    template["default_agent_pack"] = agent_pack
    skill_pack = template.get("default_skill_pack")
    if isinstance(skill_pack, dict):
        for bucket in ("core", "code", "domain"):
            values = skill_pack.get(bucket)
            if isinstance(values, list):
                skill_pack[bucket] = [value for value in values if value in selected_skills]
    tracked_paths = template.get("tracked_paths")
    if isinstance(tracked_paths, dict):
        for values in tracked_paths.values():
            if isinstance(values, list):
                values[:] = [
                    value
                    for value in values
                    if not (isinstance(value, str) and value.startswith("plugins/"))
                ]
        harness_paths = tracked_paths.get("harness_structure")
        if isinstance(harness_paths, list):
            for capability_path in (
                "config/capability-sources.json",
                ".mir/capability-lock.json",
            ):
                if capability_path not in harness_paths:
                    harness_paths.append(capability_path)

    inventory["agents"] = selected_agents
    inventory["skills"] = selected_skills
    catalog["templates"] = {profile: template}
    catalog.pop("repositories_dir", None)
    catalog["repositories"] = []
    catalog["purpose"] = (
        "Repository-local adopter catalog; reusable skills are supplied by pinned external "
        "Mir capabilities."
    )
    return _rewrite_release_matched(
        root,
        {"config/repo-agent-management.json": json.dumps(catalog, indent=2) + "\n"},
    )


def _reset_provider_contract_state(
    root: Path, slug: str, profile: str, purpose: str
) -> None:
    code_paths = ", ".join(_PROFILE_CODE_PATHS[profile])
    changed = _rewrite_release_matched(
        root,
        {
            "CLAUDE.md": _product_contract_text(slug, profile, purpose),
            ".ai-harness/bluebricks.md": (
                "# Product Bluebricks\n\n"
                f"Purpose: {purpose}\n\n"
                "Phase 2 design owns the product module map. Keep dependencies directed, "
                "interfaces explicit, and verification proportional to the changed boundary.\n"
            ),
            ".mir/boundary.md": (
                f"# Boundary: {slug}\n\n"
                f"Allowed product code roots: {code_paths}.\n"
                "Protected paths and external-service boundaries are canonical in "
                "`.mir/repo-profile.toml`.\n\n"
                "Blocked: Mir Yoke provider source, maintainer tests, local plugin copies, "
                "credentials, and undeclared external writes.\n"
            ),
        },
    )
    changed.extend(_compile_adopter_agent_catalog(root, profile))
    if not changed:
        return
    generator = root / "scripts/generate_codex_derivatives.sh"
    if not generator.is_file():
        return
    completed = subprocess.run(
        ["bash", str(generator)],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise ValueError(f"product contract derivative generation failed: {detail}")


def _reset_provider_task_state(root: Path, purpose: str) -> None:
    """Rewrite only task files that still match the release payload exactly."""
    intent = {
        "goal": purpose,
        "goal_type": "product",
        "scope": "local",
        "priority": "normal",
        "history": [],
    }
    updates = {
        "tasks/change_log.md": "# Change log\n\nOne bullet per non-trivial product change.\n",
        "tasks/checklist.md": "# Checklist\n\n- [ ] Define the first product outcome.\n",
        "tasks/handoffs/session-handoff-LATEST.md": (
            "# Session Handoff\n\nNo product handoff has been recorded.\n"
        ),
        "tasks/intent.json": json.dumps(intent, indent=2, ensure_ascii=False) + "\n",
        "tasks/plan.md": "# Plan\n\nNo active work.\n",
        "tasks/tdd.json": '{\n  "version": 1,\n  "changes": []\n}\n',
    }
    _rewrite_release_matched(root, updates)


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
        "config/adopter-boundary.json",
        "config/adopter-payload.json",
    )
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"required harness surface is missing: {relative}")
    for relative in (
        ".claude/settings.json",
        ".codex/hooks.json",
        "config/sub-agent-policy.json",
        "config/capability-sources.json",
        "config/adopter-boundary.json",
        "config/adopter-payload.json",
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
        try:
            codex_payload = tomllib.loads(codex_config.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"invalid TOML surface {codex_config}: {exc}")
        else:
            if "approval_policy" not in codex_payload:
                errors.append(".codex/config.toml is missing approval_policy")
            has_legacy_sandbox = any(
                field in codex_payload
                for field in ("sandbox_mode", "sandbox_workspace_write")
            )
            has_permission_profile = any(
                field in codex_payload
                for field in ("default_permissions", "permissions")
            )
            if has_legacy_sandbox and has_permission_profile:
                errors.append(
                    ".codex/config.toml mixes legacy sandbox settings with permission profiles"
                )

    hook_runtime = {
        "kind": "bash",
        "bash": "not_checked",
        "jq": "not_checked",
        "syntax": "not_checked",
    }
    bash_path = shutil.which("bash")
    jq_path = shutil.which("jq")
    hook_runtime["jq"] = jq_path or "missing"
    if jq_path is None:
        errors.append("hook runtime requires jq on PATH for JSON payload parsing")
    hook_runtime["bash"] = bash_path or "not_required_for_bootstrap"
    hook_runtime["syntax"] = "not_required"
    return errors, hook_runtime


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
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
            print("  selected global plugins are hash-verified for required runtimes")
            print("  begin a new session for every required activation runtime")
            print("  attest the namespaced skill catalog from each required session")
            print("  optional runtime installation and discovery evidence is advisory")
            print("  run mir-core:design then mir-core:spec-architect, then finalize")
        print("  receipt: .mir/bootstrap-receipt.json")


def main(argv: list[str]) -> int:
    if argv in (["-h"], ["--help"]):
        _parse(argv)
        return 0
    platform_name = platform.system()
    if platform_name == "Windows":
        print(_NATIVE_WINDOWS_GUIDANCE, file=sys.stderr)
        return 2
    if platform_name not in {"Darwin", "Linux"}:
        print(_UNSUPPORTED_PLATFORM_GUIDANCE, file=sys.stderr)
        return 2
    ns = _parse(argv)
    root = ns.project_root.expanduser().resolve(strict=False)
    if not root.is_dir():
        print(f"project root is not a directory: {root}", file=sys.stderr)
        return 2
    source_control_errors, source_control_report = _source_control_ownership(root)
    if source_control_errors:
        for error in source_control_errors:
            print(error, file=sys.stderr)
        return 2
    before = snapshot_project(root)
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
        errors.append("mir bootstrap must run from the copied uv tool environment")

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
    replace_provider_profile = False
    if existing_profile.exists():
        try:
            current_profile = load_profile(root)
            current_boundary = load_boundary(root)
            replace_provider_profile = bool(
                not ns.finalize and is_provider_owner(current_profile, current_boundary)
            )
            profile_data = (
                current_profile
                if replace_provider_profile
                else _validate_existing_profile(existing_profile, profile)
            )
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
    else:
        replace_provider_profile = _is_raw_provider_checkout(root)
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
                replace_provider_profile=replace_provider_profile,
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
    slim_report: dict[str, object] = {"status": "not_run"}
    cli_path_raw = os.environ.get("MIR_BOOTSTRAP_CLI_PATH")
    if complete:
        try:
            slim_report = apply_adopter_slim(
                root,
                external_cli=Path(cli_path_raw) if cli_path_raw else Path(sys.argv[0]),
                defer_commit=True,
            )
        except SlimError as exc:
            unique_errors.append(f"adopter slim failed: {exc}")
            complete = False
    if complete:
        status = "ready"
    elif restart_required:
        status = "restart_required"
    else:
        status = "incomplete"
    receipt_cli_raw = slim_report.get("external_cli") or cli_path_raw
    receipt_cli_path = None
    receipt_cli_hash = None
    if isinstance(receipt_cli_raw, str) and receipt_cli_raw:
        candidate_cli = Path(os.path.abspath(Path(receipt_cli_raw).expanduser()))
        receipt_cli_path = str(candidate_cli)
        if candidate_cli.is_file():
            receipt_cli_hash = hashlib.sha256(candidate_cli.read_bytes()).hexdigest()
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
        "source_control": source_control_report,
        "cli": {
            "executable": receipt_cli_path,
            "sha256": receipt_cli_hash,
            "externalized": receipt_cli_path is not None,
            "runtime_id": os.environ.get("MIR_BOOTSTRAP_RUNTIME_ID"),
            "source_url": os.environ.get("MIR_BOOTSTRAP_SOURCE_URL"),
            "source_commit": os.environ.get("MIR_BOOTSTRAP_SOURCE_COMMIT"),
            "source_lock_sha256": os.environ.get(
                "MIR_BOOTSTRAP_SOURCE_LOCK_SHA256"
            ),
            "constraints_sha256": os.environ.get(
                "MIR_BOOTSTRAP_CONSTRAINTS_SHA256"
            ),
            "runtime_manifest": os.environ.get("MIR_BOOTSTRAP_RUNTIME_MANIFEST"),
            "runtime_manifest_sha256": os.environ.get(
                "MIR_BOOTSTRAP_RUNTIME_MANIFEST_SHA256"
            ),
        },
        "slim": slim_report,
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
    # @spec FR-001 FR-004 IR-002 QR-001
    projected_after = snapshot_project(root)
    if slim_report.get("status") == "applied":
        projected_after.pop(".mir/slim-transaction.json", None)
        projected_after.pop(".mir/slim.lock", None)
    receipt["changed_paths"] = sorted(
        set(changed_paths(before, projected_after))
        | {receipt_path.relative_to(root).as_posix()}
    )
    try:
        _atomic_write_json(receipt_path, receipt)
    except OSError as exc:
        rollback_error = None
        try:
            rollback_adopter_slim(root, slim_report)
        except SlimError as rollback_exc:
            rollback_error = str(rollback_exc)
        receipt["status"] = "incomplete"
        receipt["errors"].append(f"bootstrap receipt publish failed: {exc}")
        if rollback_error:
            receipt["errors"].append(rollback_error)
        _emit(ns, receipt)
        return 1
    try:
        commit_adopter_slim(root, slim_report)
    except SlimError as exc:
        receipt["errors"].append(f"slim commit cleanup failed: {exc}")
        _emit(ns, receipt)
        return 1
    _emit(ns, receipt)
    if complete or restart_required or allowed_incomplete:
        return 0
    return 2 if invalid_config else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
