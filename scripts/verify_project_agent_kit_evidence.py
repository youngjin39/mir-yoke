#!/usr/bin/env python3
"""Validate Claude and Codex clean-room evidence for the Project Agent Kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = Path("recipes/project-agent-kit/prompt.txt")
PURPOSE_FIXTURE_PATH = Path("release-evidence/project-agent-kit/fixture/purpose.md")
RENDERED_PROMPT_PATH = Path(
    "release-evidence/project-agent-kit/fixture/rendered-prompt.txt"
)
RECIPE_PATHS = (
    Path("recipes/project-agent-kit/README.md"),
    Path("recipes/project-agent-kit/reviewer.md"),
    Path("recipes/project-agent-kit/verification.md"),
    Path("recipes/project-agent-kit/project-agent-kit.schema.json"),
    Path("templates/common-harness/harness_a.toml"),
    Path("templates/common-harness/scripts/mir.sh"),
    Path("templates/common-harness/scripts/memory-sync.sh"),
    Path("templates/common-harness/scripts/render-hook-configs.py"),
    Path("templates/common-harness/harness/project-hooks.json"),
    Path("templates/common-harness/.claude/hooks/_lib/invocation_log.sh"),
    Path("templates/common-harness/.claude/hooks/_lib/run-python.sh"),
    Path("templates/common-harness/.claude/hooks/pre-compact.sh"),
    Path("templates/common-harness/.claude/hooks/post-compact.sh"),
    Path("templates/common-harness/.claude/hooks/compact-resume.sh"),
    Path("templates/common-harness/tasks/handoffs/session-handoff-LATEST.md"),
)
TARGET_SCHEMA_PATH = Path("recipes/project-agent-kit/project-agent-kit.schema.json")
RUNTIMES = ("claude", "codex")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_PROJECT_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PRIVATE_PATH = re.compile(
    r"(?:/"
    + r"Users/|/"
    + r"home/|/"
    + r"Volumes/|[A-Za-z]:\\Users\\)[^\s\"']+"
)
_SECRET = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{16,}|gh[oprsu]_[a-z0-9]{16,}|"
    r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,}\]]+)"
)
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
TARGET_CONTRACT_PATH = Path("harness/project-agent-kit.json")
BASE_TARGET_FILES = {
    "PROJECT.md",
    "HARNESS.md",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    ".gitignore",
    "docs/harness-bootstrap.md",
    "harness_a.toml",
    TARGET_CONTRACT_PATH.as_posix(),
    "scripts/generate_agent_derivatives.py",
    "scripts/memory-sync.sh",
    "scripts/mir.sh",
    "scripts/render-hook-configs.py",
    "scripts/verify.sh",
    "harness/project-hooks.json",
    ".claude/hooks/_lib/invocation_log.sh",
    ".claude/hooks/_lib/run-python.sh",
    ".claude/hooks/pre-compact.sh",
    ".claude/hooks/post-compact.sh",
    ".claude/hooks/compact-resume.sh",
    ".claude/settings.json",
    ".codex/hooks.json",
    "tasks/handoffs/session-handoff-LATEST.md",
    ".githooks/pre-commit",
}
EXPECTED_TARGET_COMMANDS = {
    "lint": ["scripts/verify.sh", "lint"],
    "build": ["scripts/verify.sh", "build"],
    "test": ["scripts/verify.sh", "test"],
}
FRESH_SESSION_CONTEXT_COMMAND = (
    'scripts/mir.sh context pull "<task query>" '
    "--db .mir/memory.db --project-root ."
)
EXPECTED_COMMON_HARNESS_PATHS = {
    "config": "harness_a.toml",
    "database": ".mir/memory.db",
    "handoff": "tasks/handoffs/session-handoff-LATEST.md",
    "mir_wrapper": "scripts/mir.sh",
    "memory_sync_wrapper": "scripts/memory-sync.sh",
    "memory_sync_hook": ".githooks/pre-commit",
    "lifecycle_sources": [
        "harness/project-hooks.json",
        "scripts/render-hook-configs.py",
        ".claude/hooks/_lib/invocation_log.sh",
        ".claude/hooks/_lib/run-python.sh",
        ".claude/hooks/pre-compact.sh",
        ".claude/hooks/post-compact.sh",
        ".claude/hooks/compact-resume.sh",
    ],
    "generated_hooks": [".claude/settings.json", ".codex/hooks.json"],
}
EXPECTED_COMMON_HARNESS_COMMANDS = {
    "memory_init": ["scripts/mir.sh", "migrate", "up", "--db", ".mir/memory.db"],
    "memory_sync": ["scripts/memory-sync.sh"],
    "memory_doctor": [
        "scripts/mir.sh",
        "memory",
        "doctor",
        "--project-root",
        ".",
        "--json",
    ],
    "hook_render": [
        "scripts/mir.sh",
        "run-python",
        "--project-root",
        ".",
        "--",
        "scripts/render-hook-configs.py",
    ],
    "hook_parity": [
        "scripts/mir.sh",
        "run-python",
        "--project-root",
        ".",
        "--",
        "scripts/render-hook-configs.py",
        "--check",
    ],
}
FORBIDDEN_RUNTIME_PREFIXES = ("src/mir/", "tools/", "plugins/")
ALLOWED_TARGET_LOCAL_GIT_KEYS = {
    "core.repositoryformatversion",
    "core.filemode",
    "core.bare",
    "core.logallrefupdates",
    "core.ignorecase",
    "core.precomposeunicode",
    "core.symlinks",
    "core.protectntfs",
    "core.protecthfs",
    "core.hookspath",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hashes(root: Path = ROOT) -> tuple[str, str, str, str]:
    template = (root / PROMPT_PATH).read_text(encoding="utf-8")
    purpose = (root / PURPOSE_FIXTURE_PATH).read_text(encoding="utf-8").strip()
    rendered = (root / RENDERED_PROMPT_PATH).read_text(encoding="utf-8")
    expected_rendered = template.replace("[Prepared project purpose and goals]", purpose)
    if rendered != expected_rendered:
        raise ValueError("tracked rendered prompt does not match the purpose fixture and template")
    prompt_template_sha256 = hashlib.sha256(template.encode("utf-8")).hexdigest()
    purpose_sha256 = hashlib.sha256(purpose.encode("utf-8")).hexdigest()
    rendered_prompt_sha256 = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    digest = hashlib.sha256()
    for relative in RECIPE_PATHS:
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return (
        prompt_template_sha256,
        purpose_sha256,
        rendered_prompt_sha256,
        digest.hexdigest(),
    )


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _require_hash(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _require_exact(mapping: dict[str, Any], key: str, expected: object) -> None:
    actual = mapping.get(key)
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError(f"{key} must be {expected!r}")


def reject_sensitive_text(text: str, label: str) -> None:
    if _PRIVATE_PATH.search(text):
        raise ValueError(f"{label} contains a private local path")
    if re.search(r"(?i)https?://[^\s/@:]+:[^\s/@]+@", text):
        raise ValueError(f"{label} contains URL credentials")
    if _SECRET.search(text):
        raise ValueError(f"{label} contains a credential-like value")
    if _EMAIL.search(text):
        raise ValueError(f"{label} contains a public email address")


def redact_private_paths(text: str) -> str:
    return _PRIVATE_PATH.sub("<PRIVATE_PATH>", text)


def _relative_file(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"{label} must be a normalized target-relative path")
    return value


def _target_contract(target: Path, source_root: Path = ROOT) -> dict[str, Any]:
    path = target / TARGET_CONTRACT_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid target contract: {exc}") from exc
    schema = json.loads((source_root / TARGET_SCHEMA_PATH).read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as exc:
        raise ValueError(
            f"target contract does not match the recipe schema: {exc.message}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("target contract must be an object")
    slug = payload.get("project_slug")
    if not isinstance(slug, str) or _PROJECT_SLUG.fullmatch(slug) is None:
        raise ValueError("target contract project_slug is invalid")

    intent = _mapping(payload, "intent")
    purpose = intent.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("target contract purpose must be non-empty")
    _require_exact(
        intent,
        "purpose_sha256",
        hashlib.sha256(purpose.strip().encode()).hexdigest(),
    )
    context_probe = intent.get("context_probe")
    if (
        not isinstance(context_probe, str)
        or len(context_probe) < 3
        or context_probe.casefold() not in purpose.casefold()
    ):
        raise ValueError("target contract context_probe must be a purpose-owned search token")
    provider = _mapping(payload, "provider")
    _require_exact(provider, "url", "https://github.com/youngjin39/mir-yoke")

    common_harness = _mapping(payload, "common_harness")
    common_paths = _mapping(common_harness, "paths")
    common_commands = _mapping(common_harness, "commands")
    for name, expected in EXPECTED_COMMON_HARNESS_PATHS.items():
        _require_exact(common_paths, name, expected)
        if isinstance(expected, list):
            for index, relative in enumerate(expected):
                _relative_file(relative, f"common_harness.paths.{name}[{index}]")
        else:
            _relative_file(expected, f"common_harness.paths.{name}")
    for name, expected in EXPECTED_COMMON_HARNESS_COMMANDS.items():
        _require_exact(common_commands, name, expected)
    _require_exact(
        common_commands,
        "context_pull",
        [
            "scripts/mir.sh",
            "context",
            "pull",
            context_probe,
            "--db",
            ".mir/memory.db",
            "--project-root",
            ".",
        ],
    )

    foundation = _mapping(payload, "foundation")
    manifest = _relative_file(foundation.get("manifest"), "foundation.manifest")
    lockfile = _relative_file(foundation.get("lockfile"), "foundation.lockfile")
    compile_targets = foundation.get("compile_targets")
    smoke_tests = foundation.get("smoke_tests")
    if not isinstance(compile_targets, list) or len(compile_targets) != 1:
        raise ValueError("foundation.compile_targets must contain exactly one path")
    if not isinstance(smoke_tests, list) or len(smoke_tests) != 1:
        raise ValueError("foundation.smoke_tests must contain exactly one path")
    compile_target = _relative_file(compile_targets[0], "foundation.compile_targets[0]")
    smoke_test = _relative_file(smoke_tests[0], "foundation.smoke_tests[0]")
    if "harness" not in Path(compile_target).name or "harness" not in Path(smoke_test).name:
        raise ValueError("foundation probes must use domain-neutral harness filenames")
    foundation_paths = (manifest, lockfile, compile_target, smoke_test)
    if len(set(foundation_paths)) != 4:
        raise ValueError("target foundation paths must be distinct")
    missing = [relative for relative in foundation_paths if not (target / relative).is_file()]
    if missing:
        raise ValueError(f"target foundation is missing files: {missing}")
    if any(not (target / relative).read_bytes() for relative in foundation_paths):
        raise ValueError("target foundation files must be non-empty")
    try:
        compile_probe = (target / compile_target).read_text(encoding="utf-8")
        smoke_probe = (target / smoke_test).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("foundation probes must be reviewable UTF-8 text") from exc
    if len(compile_probe.encode()) > 1024 or len(smoke_probe.encode()) > 2048:
        raise ValueError("foundation probes exceed the domain-neutral bootstrap size limit")
    forbidden_product_markers = (
        "http://",
        "https://",
        "socket",
        "database",
        "sqlite",
        "endpoint",
        "controller",
        "markdown",
        "argparse",
        "click.command",
        "typer.",
        "open(",
        ".read_text(",
        ".write_text(",
    )
    normalized_probes = f"{compile_probe}\n{smoke_probe}".lower()
    if any(marker in normalized_probes for marker in forbidden_product_markers):
        raise ValueError("foundation probes contain product, I/O, or integration behavior")
    if "harness" not in normalized_probes or "ready" not in normalized_probes:
        raise ValueError("foundation probes must remain an explicit harness readiness check")

    commands = _mapping(payload, "commands")
    for name, expected in EXPECTED_TARGET_COMMANDS.items():
        _require_exact(commands, name, expected)
    parity = commands.get("generated_parity")
    if (
        not isinstance(parity, list)
        or len(parity) < 3
        or not all(isinstance(item, str) and item for item in parity)
        or parity[-2:] != ["scripts/generate_agent_derivatives.py", "--check"]
    ):
        raise ValueError("generated_parity must run the target generator with --check")
    if any(Path(item).is_absolute() for item in parity):
        raise ValueError("generated_parity argv must not contain absolute paths")

    generation = _mapping(payload, "generation")
    expected_canonical = [
        f".claude/skills/{slug}-code-review/SKILL.md",
        f".claude/agents/{slug}-code-reviewer.md",
    ]
    expected_generated = [
        f".agents/skills/{slug}-code-review/SKILL.md",
        f".codex/agents/{slug}-code-reviewer.toml",
    ]
    _require_exact(generation, "canonical", expected_canonical)
    _require_exact(generation, "generated", expected_generated)
    return payload


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def tracked_tree_sha256(root: Path) -> str:
    rows = _run_git(root, "ls-files", "-s", "-z").split("\0")
    digest = hashlib.sha256()
    for row in sorted(item for item in rows if item):
        metadata, relative = row.split("\t", 1)
        mode = metadata.split(" ", 1)[0]
        path = root / relative
        digest.update(mode.encode("ascii"))
        digest.update(b"\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _frontmatter(text: str, label: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{label} lacks YAML frontmatter")
    raw_header, body = text.split("\n---\n", 1)
    header: dict[str, str] = {}
    for line in raw_header.splitlines()[1:]:
        if not line or line[0].isspace() or ":" not in line:
            raise ValueError(f"{label} has unsupported YAML frontmatter")
        key, value = line.split(":", 1)
        if key in header or not value.strip():
            raise ValueError(f"{label} has duplicate or blank frontmatter")
        header[key] = value.strip().strip('"')
    return header, body


def _verify_common_harness(
    target: Path,
    contract: dict[str, Any],
    tracked: set[str],
) -> None:
    common_harness = _mapping(contract, "common_harness")
    paths = _mapping(common_harness, "paths")
    provider = _mapping(contract, "provider")
    tracked_paths: set[str] = set()
    for name, value in paths.items():
        if name == "database":
            continue
        if isinstance(value, list):
            tracked_paths.update(str(relative) for relative in value)
        else:
            tracked_paths.add(str(value))
    missing = sorted(tracked_paths - tracked)
    if missing:
        raise ValueError(f"bundled common harness is missing tracked files: {missing}")
    database = paths["database"]
    if database in tracked:
        raise ValueError("local memory database must never be tracked")
    forbidden = sorted(
        relative
        for relative in tracked
        if relative.startswith(FORBIDDEN_RUNTIME_PREFIXES)
    )
    if forbidden:
        raise ValueError(f"bundled target copies provider runtime source: {forbidden}")

    gitignore = (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    if ".mir/" not in gitignore:
        raise ValueError("target must ignore the complete .mir runtime directory")
    executable_paths = {
        str(paths["mir_wrapper"]),
        str(paths["memory_sync_wrapper"]),
        str(paths["memory_sync_hook"]),
        *(relative for relative in paths["lifecycle_sources"] if relative.endswith((".sh", ".py"))),
    }
    for relative in executable_paths:
        if not (target / relative).stat().st_mode & 0o111:
            raise ValueError(f"common harness executable bit is missing: {relative}")

    config = tomllib.loads((target / paths["config"]).read_text(encoding="utf-8"))
    memory = config.get("memory")
    if not isinstance(memory, dict):
        raise ValueError("harness_a.toml must contain the required memory configuration")
    expected_memory = {
        "enabled": True,
        "required": True,
        "backend": "sqlite_fts5",
        "db_path": database,
        "vector_mode": "off",
    }
    for name, expected in expected_memory.items():
        _require_exact(memory, name, expected)
    archives = memory.get("external_archives")
    if archives != [
        {
            "slug": "project-harness",
            "root": ".",
            "mode": "indexed",
            "glob_include": [
                "PROJECT.md",
                "HARNESS.md",
                "docs/**/*.md",
                "tasks/**/*.md",
            ],
        }
    ]:
        raise ValueError("common harness archives must rehydrate from tracked project context")
    durable_sources = {
        "PROJECT.md",
        "HARNESS.md",
        "docs/harness-bootstrap.md",
        paths["handoff"],
    }
    if not durable_sources <= tracked:
        raise ValueError("common harness lacks the tracked sources needed for rehydration")

    wrapper = (target / paths["mir_wrapper"]).read_text(encoding="utf-8")
    exact_source = f"git+{provider['url']}@{provider['revision']}"
    required_wrapper_markers = (
        f'uvx --from "{exact_source}" mir "$@"',
        '.mir/runtime',
        "export HOME=",
        "export XDG_CACHE_HOME=",
        "export XDG_CONFIG_HOME=",
        "export XDG_DATA_HOME=",
        "export TMPDIR=",
        "export UV_CACHE_DIR=",
        "export UV_TOOL_DIR=",
        "export UV_PYTHON_INSTALL_DIR=",
    )
    if not all(marker in wrapper for marker in required_wrapper_markers):
        raise ValueError("Mir wrapper must pin the provider and confine all runtime state")
    forbidden_wrapper_markers = ("file://", "--project", "src/mir", "tools/", "plugins/")
    if any(marker in wrapper for marker in forbidden_wrapper_markers):
        raise ValueError("Mir wrapper must use only the pinned external provider")

    sync_wrapper = (target / paths["memory_sync_wrapper"]).read_text(encoding="utf-8")
    for marker in (
        ".mir/memory.db",
        "scripts/mir.sh context sync --db .mir/memory.db --project-root .",
    ):
        if marker not in sync_wrapper:
            raise ValueError(f"memory sync wrapper lacks required marker: {marker}")
    handoff = " ".join(
        (target / paths["handoff"]).read_text(encoding="utf-8").split()
    )
    for marker in (
        "Product planning and implementation have not started",
        "context_pull",
        "memory_init",
        "memory_sync",
        "memory_doctor",
    ):
        if marker not in handoff:
            raise ValueError(f"common harness handoff lacks required marker: {marker}")
    hook = (target / paths["memory_sync_hook"]).read_text(encoding="utf-8")
    if paths["memory_sync_wrapper"] not in hook:
        raise ValueError("pre-commit hook must invoke the project-owned memory sync wrapper")
    if re.search(r"(?s)if\s+.*memory\.db.*memory-sync", hook):
        raise ValueError("pre-commit hook must not skip memory sync when the database is absent")

    definition = json.loads(
        (target / paths["lifecycle_sources"][0]).read_text(encoding="utf-8")
    )
    if set(definition.get("events", {})) != {"PreCompact", "PostCompact", "SessionStart"}:
        raise ValueError("compact lifecycle definition must declare the exact supported events")
    compact_groups = definition["events"]["SessionStart"]
    if len(compact_groups) != 1 or compact_groups[0].get("matcher") != "^compact$":
        raise ValueError("compact resume must be limited to SessionStart(source=compact)")


def _verify_target_checkout(target: Path, payload: dict[str, Any]) -> None:
    result = _mapping(payload, "result")
    observation = _mapping(payload, "observation")
    _require_exact(result, "branch", _run_git(target, "branch", "--show-current"))
    _require_exact(result, "commit_count", int(_run_git(target, "rev-list", "--count", "HEAD")))
    _require_exact(result, "commit_message", _run_git(target, "log", "-1", "--format=%s"))
    _require_exact(result, "initial_commit", _run_git(target, "rev-parse", "HEAD"))
    if _run_git(target, "status", "--porcelain"):
        raise ValueError("bundled target checkout is not clean")
    _require_exact(
        observation,
        "target_tree_sha256",
        tracked_tree_sha256(target),
    )

    contract = _target_contract(target)
    intent = _mapping(contract, "intent")
    provider = _mapping(contract, "provider")
    binding = _mapping(payload, "binding")
    _require_exact(intent, "purpose_sha256", binding["purpose_sha256"])
    _require_exact(intent, "rendered_prompt_sha256", binding["rendered_prompt_sha256"])
    _require_exact(provider, "revision", binding["provider_revision"])
    missing = [relative for relative in BASE_TARGET_FILES if not (target / relative).is_file()]
    if missing:
        raise ValueError(f"bundled target is missing required artifacts: {missing}")
    if not (target / ".githooks/pre-commit").stat().st_mode & 0o111:
        raise ValueError("bundled pre-commit hook is not executable")
    if not (target / "scripts/verify.sh").stat().st_mode & 0o111:
        raise ValueError("bundled verification entrypoint is not executable")
    tracked = set(_run_git(target, "ls-files").splitlines())
    symlinks = sorted(relative for relative in tracked if (target / relative).is_symlink())
    if symlinks:
        raise ValueError(f"bundled target contains tracked symlinks: {symlinks}")
    _verify_common_harness(target, contract, tracked)

    purpose = intent["purpose"].strip()
    project = (target / "PROJECT.md").read_text(encoding="utf-8")
    if purpose not in project:
        raise ValueError("PROJECT.md does not preserve the exact project purpose")
    for section in (
        "Goals",
        "Users",
        "Success conditions",
        "Non-goals",
        "Assumptions",
        "Open product decisions",
    ):
        if section.lower() not in project.lower():
            raise ValueError(f"PROJECT.md lacks required section: {section}")
    harness = (target / "HARNESS.md").read_text(encoding="utf-8")
    for section in (
        "Outcome",
        "Authority",
        "Protected",
        "Generated",
        "Work style",
        "Verification",
    ):
        if section.lower() not in harness.lower():
            raise ValueError(f"HARNESS.md lacks required contract section: {section}")
    normalized_harness = " ".join(harness.split())
    for fragment in (
        "fresh session",
        "task-scoped",
        FRESH_SESSION_CONTEXT_COMMAND,
    ):
        if fragment not in normalized_harness:
            raise ValueError(
                "HARNESS.md lacks the required fresh-session task-scoped context pull"
            )
    for entrypoint in ("CLAUDE.md", "AGENTS.md"):
        text = (target / entrypoint).read_text(encoding="utf-8")
        if "HARNESS.md" not in text or len(text) > 500:
            raise ValueError(f"{entrypoint} must be a thin HARNESS.md entrypoint")
    readme = (target / "README.md").read_text(encoding="utf-8")
    if not readme.startswith("# "):
        raise ValueError("README.md must identify the project")
    provenance = (target / "docs/harness-bootstrap.md").read_text(encoding="utf-8")
    if provider["url"] not in provenance or f"Revision: {provider['revision']}" not in provenance:
        raise ValueError("bootstrap provenance lacks the exact source and revision")

    generator = (target / "scripts/generate_agent_derivatives.py").read_text(
        encoding="utf-8"
    )
    if len(generator) < 200 or "--check" not in generator:
        raise ValueError("bundled derivative generator is empty or lacks parity mode")
    generation = _mapping(contract, "generation")
    for relative in [*generation["canonical"], *generation["generated"]]:
        if relative not in generator:
            raise ValueError(f"bundled derivative generator does not own {relative}")
    verify_script = (target / "scripts/verify.sh").read_text(encoding="utf-8")
    forbidden_noops = ("exit 0", "echo skip", "--if-present", " true", "\n:\n")
    if len(verify_script) < 120 or any(item in verify_script for item in forbidden_noops):
        raise ValueError("bundled verification entrypoint is a placeholder or no-op")
    if not all(name in verify_script for name in ("lint", "build", "test")):
        raise ValueError("bundled verification entrypoint lacks lint/build/test dispatch")
    unsafe_script_markers = (
        "../",
        "curl ",
        "wget ",
        "git push",
        ".ssh",
        ".aws",
        "/dev/tcp",
        "os.environ",
        "socket",
        "urllib",
        "requests",
        "http://",
        "https://",
        "ssh ",
        "scp ",
        "rsync ",
    )
    for relative, script in (
        ("scripts/generate_agent_derivatives.py", generator),
        ("scripts/verify.sh", verify_script),
    ):
        if any(marker in script for marker in unsafe_script_markers):
            raise ValueError(
                f"bundled executable contains an unsafe host-access marker: {relative}"
            )
    gitignore = (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    if ".harness-runtime/" not in gitignore:
        raise ValueError("target must ignore the observer's target-local runtime directory")
    hook = (target / ".githooks/pre-commit").read_text(encoding="utf-8")
    for marker in (
        "PROJECT_AGENT_KIT_HOOK_PHASE",
        "project-agent-kit-pre-commit.log",
        "scripts/verify.sh",
    ):
        if marker not in hook:
            raise ValueError(f"bundled pre-commit hook lacks required marker: {marker}")
    if any(marker in hook for marker in unsafe_script_markers):
        raise ValueError("bundled pre-commit hook contains an unsafe host-access marker")

    slug = contract["project_slug"]
    claude_agents = [target / generation["canonical"][1]]
    codex_agents = [target / generation["generated"][1]]
    claude_skills = [target / generation["canonical"][0]]
    codex_skills = [target / generation["generated"][0]]
    reviewer_surfaces = (claude_agents, codex_agents, claude_skills, codex_skills)
    if not all(paths[0].is_file() for paths in reviewer_surfaces):
        raise ValueError("bundled target must contain the declared reviewer and skill surfaces")
    claude_agent = claude_agents[0].read_text(encoding="utf-8")
    codex_agent = codex_agents[0].read_text(encoding="utf-8")
    claude_skill = claude_skills[0].read_text(encoding="utf-8")
    agent_header, agent_body = _frontmatter(claude_agent, "Claude reviewer agent")
    if set(agent_header) != {"name", "description", "tools", "disallowedTools"}:
        raise ValueError("bundled Claude reviewer agent frontmatter is not exact")
    _require_exact(agent_header, "name", f"{slug}-code-reviewer")
    _require_exact(agent_header, "tools", "Read, Glob, Grep")
    _require_exact(agent_header, "disallowedTools", "Write, Edit")
    if not agent_header["description"] or len(agent_body.strip()) < 40:
        raise ValueError("bundled Claude reviewer agent lacks usable instructions")
    try:
        codex_payload = tomllib.loads(codex_agent)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"bundled Codex reviewer is invalid TOML: {exc}") from exc
    if set(codex_payload) != {
        "name",
        "description",
        "developer_instructions",
        "sandbox_mode",
    }:
        raise ValueError("bundled Codex reviewer contains unsupported top-level fields")
    _require_exact(codex_payload, "name", f"{slug}-code-reviewer")
    _require_exact(codex_payload, "sandbox_mode", "read-only")
    for field in ("description", "developer_instructions"):
        if not isinstance(codex_payload.get(field), str) or not codex_payload[field].strip():
            raise ValueError(f"bundled Codex reviewer lacks {field}")
    canonical_agent_path = generation["canonical"][1]
    if not codex_agent.startswith(f"# Generated from {canonical_agent_path}\n"):
        raise ValueError("bundled Codex reviewer lacks canonical-source provenance")
    source_digest = hashlib.sha256(claude_agent.encode()).hexdigest()
    if f"# Source SHA-256: {source_digest}\n" not in codex_agent:
        raise ValueError("bundled Codex reviewer is stale from its Claude source")
    skill_header, skill_body = _frontmatter(claude_skill, "Claude reviewer skill")
    if set(skill_header) != {"name", "description"}:
        raise ValueError("bundled Claude reviewer skill frontmatter must be name+description only")
    _require_exact(skill_header, "name", f"{slug}-code-review")
    if not skill_header["description"] or len(skill_body.strip()) < 40:
        raise ValueError("bundled Claude reviewer skill lacks usable instructions")
    canonical_skill_path = generation["canonical"][0]
    if canonical_skill_path not in claude_skill:
        raise ValueError("bundled reviewer skill lacks canonical-source provenance")
    foundation = _mapping(contract, "foundation")
    project_specific_markers = (
        "PROJECT.md",
        "HARNESS.md",
        "scripts/verify.sh",
        "risk",
        foundation["manifest"],
        foundation["compile_targets"][0],
        foundation["smoke_tests"][0],
    )
    if not all(marker.lower() in skill_body.lower() for marker in project_specific_markers):
        raise ValueError("bundled reviewer skill lacks project-specific paths and risks")
    if claude_skills[0].read_bytes() != codex_skills[0].read_bytes():
        raise ValueError("bundled generated reviewer skill differs from its Claude source")

    allowed = BASE_TARGET_FILES | {
        foundation["manifest"],
        foundation["lockfile"],
        *foundation["compile_targets"],
        *foundation["smoke_tests"],
        *(path.relative_to(target).as_posix() for paths in reviewer_surfaces for path in paths),
    }
    extras = sorted(tracked - allowed)
    _require_exact(_mapping(payload, "result"), "product_implementation_files", len(extras))
    if extras:
        raise ValueError(f"bundled target contains files outside the foundation: {extras}")

    for relative in sorted(tracked):
        path = target / relative
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        reject_sensitive_text(text, f"bundled target file {relative}")
        if relative not in {
            "docs/harness-bootstrap.md",
            TARGET_CONTRACT_PATH.as_posix(),
            _mapping(_mapping(contract, "common_harness"), "paths")["mir_wrapper"],
        } and re.search(
            r"(?i)mir[ -]yoke|youngjin39/mir-yoke", text
        ):
            raise ValueError(f"bundled target retains provider identity in {relative}")
        if any(marker in text for marker in ("<project-slug>", "[Prepared project", "TODO", "TBD")):
            raise ValueError(f"bundled target contains an unresolved placeholder in {relative}")


def _verify_run_artifacts(
    run_root: Path,
    payload: dict[str, Any],
    source_root: Path,
) -> None:
    observation = _mapping(payload, "observation")
    artifact_hashes = {
        "target.bundle": "target_bundle_sha256",
        "verification.json": "verification_log_sha256",
        "runtime.log": "runtime_log_sha256",
        "provider-before.json": "provider_before_sha256",
        "provider-after.json": "provider_after_sha256",
        "outside-before.json": "outside_before_sha256",
        "outside-after.json": "outside_after_sha256",
    }
    for relative, field in artifact_hashes.items():
        path = run_root / relative
        if not path.is_file():
            raise ValueError(f"missing clean-room artifact: {path}")
        _require_exact(observation, field, _sha256(path))
        if relative != "target.bundle":
            reject_sensitive_text(path.read_text(encoding="utf-8"), relative)
    runtime_log = (run_root / "runtime.log").read_text(encoding="utf-8")
    if not runtime_log.strip():
        raise ValueError("runtime transcript is empty")
    reject_sensitive_text(runtime_log, "runtime transcript")
    if runtime_log.count("READY_FOR_DEVELOPMENT_PLANNING") != 1:
        raise ValueError("runtime transcript must contain exactly one READY marker")
    if (run_root / "provider-before.json").read_bytes() != (
        run_root / "provider-after.json"
    ).read_bytes():
        raise ValueError("provider snapshots differ")
    if (run_root / "outside-before.json").read_bytes() != (
        run_root / "outside-after.json"
    ).read_bytes():
        raise ValueError("outside snapshots differ")
    provider_snapshot = json.loads(
        (run_root / "provider-before.json").read_text(encoding="utf-8")
    )
    _require_exact(
        _mapping(payload, "binding"),
        "provider_revision",
        provider_snapshot.get("head"),
    )

    verification_text = (run_root / "verification.json").read_text(encoding="utf-8")
    reject_sensitive_text(verification_text, "verification record")
    verification = json.loads(verification_text)
    if not isinstance(verification, dict) or verification.get("schema_version") != 4:
        raise ValueError("verification.json has an unsupported schema")
    _require_exact(
        verification,
        "observer_sha256",
        _sha256(source_root / "scripts/observe_project_agent_kit.py"),
    )
    commands = verification.get("commands")
    if not isinstance(commands, dict):
        raise ValueError("verification.json commands must be an object")
    if set(commands) != {"generated_parity", "lint", "build", "test"}:
        raise ValueError("verification.json must contain exactly the four observed commands")
    common_observation = _mapping(verification, "common_harness")
    _require_exact(common_observation, "database_existed_before", True)
    _require_exact(common_observation, "database_deleted", True)
    _require_exact(common_observation, "database_recreated", True)
    missing_database_hook = _mapping(common_observation, "missing_database_hook")
    _require_exact(missing_database_hook, "argv", [".githooks/pre-commit"])
    hook_exit_code = missing_database_hook.get("exit_code")
    if not isinstance(hook_exit_code, int) or hook_exit_code == 0:
        raise ValueError("observed pre-commit hook did not fail without the memory database")
    _require_exact(missing_database_hook, "mutation", "missing:.mir/memory.db")
    for stream in ("stdout", "stderr"):
        value = missing_database_hook.get(stream)
        if not isinstance(value, str):
            raise ValueError(f"common harness missing_database_hook.{stream} must be text")
        reject_sensitive_text(value, f"common harness missing_database_hook.{stream}")
    probes = verification.get("mutation_probes")
    expected_probe_names = {
        "parity_skill_source",
        "parity_agent_source",
        "parity_skill",
        "parity_agent",
        "lint_missing_compile",
        "build_missing_compile",
        "build_missing_manifest",
        "build_missing_lock",
        "test_missing_smoke",
    }
    if not isinstance(probes, dict) or set(probes) != expected_probe_names:
        raise ValueError("verification.json lacks the exact mutation probes")
    git_observation = _mapping(verification, "git")
    _require_exact(git_observation, "status_porcelain", "")
    _require_exact(git_observation, "remotes", [])
    _require_exact(git_observation, "core_hooks_path", ".githooks")
    _require_exact(git_observation, "hook_log", ["direct:0", "commit:0"])
    local_config_keys = git_observation.get("local_config_keys")
    if not isinstance(local_config_keys, list) or "core.hookspath" not in local_config_keys:
        raise ValueError("verification record lacks observed local hook configuration")
    if any(
        not isinstance(key, str) or key not in ALLOWED_TARGET_LOCAL_GIT_KEYS
        for key in local_config_keys
    ):
        raise ValueError("verification record contains unauthorized local Git configuration")
    _require_hash(
        git_observation.get("effective_policy_sha256"),
        "git.effective_policy_sha256",
    )
    _require_exact(verification, "ready_marker_count", 1)
    _require_exact(
        verification,
        "hook_commit_invocations",
        _mapping(payload, "result")["hook_commit_invocations"],
    )

    with tempfile.TemporaryDirectory(prefix="project-agent-kit-evidence-") as raw:
        target = Path(raw) / "target"
        completed = subprocess.run(
            ["git", "clone", "-q", "-b", "main", str(run_root / "target.bundle"), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(f"cannot inspect target bundle: {detail}")
        _verify_target_checkout(target, payload)
        contract_commands = _mapping(_target_contract(target), "commands")
        contract = _target_contract(target)
        common_commands = _mapping(_mapping(contract, "common_harness"), "commands")
        intent = _mapping(contract, "intent")
        for phase in ("initial", "rehydrated"):
            phase_observations = _mapping(common_observation, phase)
            expected_names = {
                "hook_render",
                "hook_parity",
                "memory_init",
                "memory_sync",
                "memory_doctor",
                "context_pull",
            }
            if set(phase_observations) != expected_names:
                raise ValueError(f"common harness {phase} observation is incomplete")
            for name in sorted(expected_names):
                observation = _mapping(phase_observations, name)
                _require_exact(observation, "argv", common_commands[name])
                _require_exact(observation, "exit_code", 0)
                for stream in ("stdout", "stderr"):
                    value = observation.get(stream)
                    if not isinstance(value, str):
                        raise ValueError(
                            f"common harness {phase}.{name}.{stream} must be text"
                        )
                    reject_sensitive_text(value, f"common harness {phase}.{name}.{stream}")
            try:
                doctor_payload = json.loads(
                    str(_mapping(phase_observations, "memory_doctor")["stdout"])
                )
            except (KeyError, json.JSONDecodeError) as exc:
                raise ValueError("observed memory doctor output is not valid JSON") from exc
            if not isinstance(doctor_payload, dict) or doctor_payload.get("status") != "ready":
                raise ValueError("observed memory doctor did not report ready")
            context_stdout = str(
                _mapping(phase_observations, "context_pull").get("stdout", "")
            )
            normalized_purpose = " ".join(str(intent["purpose"]).split())
            normalized_context = " ".join(context_stdout.split())
            if normalized_purpose not in normalized_context:
                raise ValueError("observed context pull did not recover project purpose")
        foundation = _mapping(contract, "foundation")
        generation = _mapping(contract, "generation")
        for name in ("generated_parity", "lint", "build", "test"):
            command = _mapping(commands, name)
            _require_exact(command, "argv", contract_commands[name])
            _require_exact(command, "exit_code", 0)
            for stream in ("stdout", "stderr"):
                value = command.get(stream)
                if not isinstance(value, str):
                    raise ValueError(f"commands.{name}.{stream} must be text")
                reject_sensitive_text(value, f"commands.{name}.{stream}")
                _require_exact(
                    command,
                    f"{stream}_sha256",
                    hashlib.sha256(value.encode()).hexdigest(),
                )
        expected_probes = {
            "parity_skill_source": (
                generation["canonical"][0],
                contract_commands["generated_parity"],
            ),
            "parity_agent_source": (
                generation["canonical"][1],
                contract_commands["generated_parity"],
            ),
            "parity_skill": (
                generation["generated"][0],
                contract_commands["generated_parity"],
            ),
            "parity_agent": (
                generation["generated"][1],
                contract_commands["generated_parity"],
            ),
            "lint_missing_compile": (
                foundation["compile_targets"][0],
                contract_commands["lint"],
            ),
            "build_missing_compile": (
                foundation["compile_targets"][0],
                contract_commands["build"],
            ),
            "build_missing_manifest": (
                foundation["manifest"],
                contract_commands["build"],
            ),
            "build_missing_lock": (
                foundation["lockfile"],
                contract_commands["build"],
            ),
            "test_missing_smoke": (
                foundation["smoke_tests"][0],
                contract_commands["test"],
            ),
        }
        for name, (relative, argv) in expected_probes.items():
            probe = _mapping(probes, name)
            _require_exact(probe, "argv", argv)
            _require_exact(probe, "mutation", f"missing:{relative}")
            exit_code = probe.get("exit_code")
            if not isinstance(exit_code, int) or exit_code == 0:
                raise ValueError(f"mutation probe must fail: {name}")
            for stream in ("stdout", "stderr"):
                value = probe.get(stream)
                if not isinstance(value, str):
                    raise ValueError(f"mutation probe {name} lacks {stream}")
                reject_sensitive_text(value, f"mutation_probes.{name}.{stream}")
                _require_exact(
                    probe,
                    f"{stream}_sha256",
                    hashlib.sha256(value.encode()).hexdigest(),
                )


def validate_evidence_payload(
    payload: dict[str, Any],
    *,
    expected_runtime: str,
    prompt_template_sha256: str,
    purpose_sha256: str,
    rendered_prompt_sha256: str,
    recipe_sha256: str,
) -> None:
    reject_sensitive_text(json.dumps(payload, sort_keys=True), "evidence payload")
    if payload.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")

    runtime = _mapping(payload, "runtime")
    _require_exact(runtime, "name", expected_runtime)
    if not isinstance(runtime.get("version"), str) or not runtime["version"].strip():
        raise ValueError("runtime.version must be non-empty")

    binding = _mapping(payload, "binding")
    _require_exact(binding, "prompt_template_sha256", prompt_template_sha256)
    _require_exact(binding, "purpose_sha256", purpose_sha256)
    _require_exact(binding, "rendered_prompt_sha256", rendered_prompt_sha256)
    _require_exact(binding, "recipe_sha256", recipe_sha256)
    provider_revision = binding.get("provider_revision")
    if not isinstance(provider_revision, str) or _COMMIT.fullmatch(provider_revision) is None:
        raise ValueError("binding.provider_revision must be a full Git object id")

    observation = _mapping(payload, "observation")
    if not isinstance(observation.get("run_id"), str) or not observation["run_id"].strip():
        raise ValueError("observation.run_id must identify one actual clean-room run")
    _require_exact(observation, "before_empty", True)
    _require_exact(observation, "outside_existing_worktree", True)
    provider_before = _require_hash(
        observation.get("provider_before_sha256"), "provider_before_sha256"
    )
    provider_after = _require_hash(
        observation.get("provider_after_sha256"), "provider_after_sha256"
    )
    outside_before = _require_hash(
        observation.get("outside_before_sha256"), "outside_before_sha256"
    )
    outside_after = _require_hash(
        observation.get("outside_after_sha256"), "outside_after_sha256"
    )
    _require_hash(observation.get("target_tree_sha256"), "target_tree_sha256")
    _require_hash(observation.get("target_bundle_sha256"), "target_bundle_sha256")
    _require_hash(
        observation.get("verification_log_sha256"), "verification_log_sha256"
    )
    _require_hash(observation.get("runtime_log_sha256"), "runtime_log_sha256")
    if provider_before != provider_after:
        raise ValueError("provider state changed during the clean-room run")
    if outside_before != outside_after:
        raise ValueError("outside state changed during the clean-room run")

    result = _mapping(payload, "result")
    expected_results: dict[str, object] = {
        "ready_marker": "READY_FOR_DEVELOPMENT_PLANNING",
        "artifacts": "pass",
        "generated_parity": "pass",
        "read_only_reviewer": "pass",
        "lint_exit_code": 0,
        "build_exit_code": 0,
        "test_exit_code": 0,
        "hook_direct_exit_code": 0,
        "hook_commit_invocations": 1,
        "branch": "main",
        "commit_count": 1,
        "commit_message": "chore(harness): bootstrap project agent kit",
        "worktree_clean": True,
        "remote_count": 0,
        "product_implementation_files": 0,
    }
    for key, expected in expected_results.items():
        _require_exact(result, key, expected)
    initial_commit = result.get("initial_commit")
    if not isinstance(initial_commit, str) or _COMMIT.fullmatch(initial_commit) is None:
        raise ValueError("initial_commit must be a full Git object id")


def verify_evidence_root(evidence_root: Path, source_root: Path = ROOT) -> dict[str, object]:
    (
        prompt_template_sha256,
        purpose_sha256,
        rendered_prompt_sha256,
        recipe_sha256,
    ) = content_hashes(source_root)
    run_ids: set[str] = set()
    for runtime in RUNTIMES:
        run_root = evidence_root / runtime
        path = run_root / "evidence.json"
        if not path.is_file():
            raise ValueError(f"missing clean-room evidence: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"evidence must be an object: {path}")
        validate_evidence_payload(
            payload,
            expected_runtime=runtime,
            prompt_template_sha256=prompt_template_sha256,
            purpose_sha256=purpose_sha256,
            rendered_prompt_sha256=rendered_prompt_sha256,
            recipe_sha256=recipe_sha256,
        )
        _verify_run_artifacts(run_root, payload, source_root)
        run_id = payload["observation"]["run_id"]
        if run_id in run_ids:
            raise ValueError("Claude and Codex evidence must come from separate clean-room runs")
        run_ids.add(run_id)
    return {
        "prompt_template_sha256": prompt_template_sha256,
        "purpose_sha256": purpose_sha256,
        "rendered_prompt_sha256": rendered_prompt_sha256,
        "recipe_sha256": recipe_sha256,
        "runtimes": list(RUNTIMES),
    }


def main(argv: list[str] | None = None) -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "release-evidence" / "project-agent-kit" / version,
    )
    args = parser.parse_args(argv)
    try:
        report = verify_evidence_root(args.evidence_root, ROOT)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"project agent kit evidence: ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
