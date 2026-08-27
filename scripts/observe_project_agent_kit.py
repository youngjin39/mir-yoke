#!/usr/bin/env python3
"""Observe one Project Agent Kit clean-room run without trusting runtime claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scripts.verify_project_agent_kit_evidence import (  # noqa: E402
    ALLOWED_TARGET_LOCAL_GIT_KEYS,
    BASE_TARGET_FILES,
    ROOT,
    _mapping,
    _run_git,
    _sha256,
    _target_contract,
    _verify_run_artifacts,
    _verify_target_checkout,
    content_hashes,
    redact_private_paths,
    reject_sensitive_text,
    tracked_tree_sha256,
    validate_evidence_payload,
)

COMMIT_MESSAGE = "chore(harness): bootstrap project agent kit"
GIT_POLICY_KEYS = (
    "user.name",
    "user.email",
    "user.signingkey",
    "commit.gpgsign",
    "gpg.format",
    "gpg.program",
    "gpg.ssh.program",
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _candidate_digest(root: Path) -> str:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    digest = hashlib.sha256()
    for raw_relative in sorted(item for item in completed.stdout.split(b"\0") if item):
        relative = raw_relative.decode("utf-8")
        path = root / relative
        if not path.exists() and not path.is_symlink():
            digest.update(b"deleted\0")
            digest.update(raw_relative)
            digest.update(b"\0")
            continue
        mode = stat.S_IMODE(path.lstat().st_mode)
        digest.update(f"{mode:o}".encode("ascii"))
        digest.update(b"\0")
        digest.update(raw_relative)
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _provider_snapshot(root: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "provider-git-candidate",
        "head": _run_git(root, "rev-parse", "HEAD"),
        "status_sha256": hashlib.sha256(
            _run_git(root, "status", "--porcelain=v1", "--untracked-files=all").encode()
        ).hexdigest(),
        "candidate_sha256": _candidate_digest(root),
    }


def _git_config(root: Path, key: str) -> str | None:
    completed = subprocess.run(
        ["git", "config", "--get", key],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 1:
        return None
    if completed.returncode != 0:
        raise ValueError(f"cannot inspect Git policy key: {key}")
    return completed.stdout.strip()


def _git_policy(root: Path) -> dict[str, str | None]:
    return {key: _git_config(root, key) for key in GIT_POLICY_KEYS}


def _outside_snapshot(paths: list[Path]) -> dict[str, object]:
    snapshots: list[dict[str, object]] = []
    for index, root in enumerate(paths, start=1):
        digest = hashlib.sha256()
        count = 0
        if root.exists():
            candidates = [root, *sorted(root.rglob("*"))]
            for path in candidates:
                metadata = path.lstat()
                relative = "." if path == root else path.relative_to(root).as_posix()
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(
                    f"{stat.S_IFMT(metadata.st_mode):o}:{stat.S_IMODE(metadata.st_mode):o}:"
                    f"{metadata.st_size}:{metadata.st_mtime_ns}".encode("ascii")
                )
                digest.update(b"\0")
                if path.is_symlink():
                    digest.update(os.readlink(path).encode("utf-8"))
                elif path.is_file():
                    with path.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                digest.update(b"\0")
                count += 1
        snapshots.append(
            {
                "label": f"outside-{index}",
                "exists": root.exists(),
                "entry_count": count,
                "metadata_sha256": digest.hexdigest(),
            }
        )
    return {"schema_version": 1, "kind": "outside-content", "paths": snapshots}


def _sanitize(text: str, replacements: dict[str, str]) -> str:
    sanitized = text
    for source, replacement in sorted(replacements.items(), key=lambda item: -len(item[0])):
        if source:
            sanitized = sanitized.replace(source, replacement)
    sanitized = re.sub(
        r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@",
        r"\1<REDACTED_CREDENTIAL>@",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\b(?:sk-[a-z0-9_-]{16,}|gh[oprsu]_[a-z0-9]{16,})\b",
        "<REDACTED_SECRET>",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,}\]]+",
        r"\1<REDACTED_SECRET>",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "<REDACTED_EMAIL>",
        sanitized,
    )
    sanitized = redact_private_paths(sanitized)
    reject_sensitive_text(sanitized, "sanitized observer output")
    return sanitized


def prepare(target: Path, state_dir: Path, outside_paths: list[Path]) -> dict[str, object]:
    target = target.resolve()
    state_dir = state_dir.resolve()
    outside_paths = [path.resolve() for path in outside_paths]
    if not target.is_dir() or any(target.iterdir()):
        raise ValueError("target must be an existing empty directory")
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        raise ValueError("target must be outside every existing Git worktree")
    if _is_within(state_dir, target) or _is_within(state_dir, ROOT):
        raise ValueError("observer state directory must be outside target and provider")
    if not outside_paths:
        raise ValueError("at least one bounded outside path must be observed")
    if any(
        _is_within(target, path)
        or _is_within(path, target)
        or _is_within(state_dir, path)
        or _is_within(path, state_dir)
        for path in outside_paths
    ):
        raise ValueError("outside observations must exclude target and observer state")
    if state_dir.exists() and any(state_dir.iterdir()):
        raise ValueError("observer state directory must be absent or empty")
    state_dir.mkdir(parents=True, exist_ok=True)

    provider = _provider_snapshot(ROOT)
    outside = _outside_snapshot(outside_paths)
    git_policy = _git_policy(target)
    if not git_policy["user.name"] or not git_policy["user.email"]:
        raise ValueError("effective Git user.name and user.email must exist before the run")
    email = str(git_policy["user.email"]).lower()
    if not (email.endswith("@invalid") or email.endswith("@users.noreply.github.com")):
        raise ValueError("release evidence requires a preconfigured publishable Git email")
    _write_json(state_dir / "provider-before.json", provider)
    _write_json(state_dir / "outside-before.json", outside)
    prompt_template, purpose, rendered_prompt, recipe = content_hashes(ROOT)
    preflight = {
        "schema_version": 1,
        "target": str(target),
        "outside_paths": [str(path) for path in outside_paths],
        "before_empty": True,
        "outside_existing_worktree": True,
        "git_policy": git_policy,
        "binding": {
            "prompt_template_sha256": prompt_template,
            "purpose_sha256": purpose,
            "rendered_prompt_sha256": rendered_prompt,
            "recipe_sha256": recipe,
            "provider_revision": provider["head"],
        },
    }
    _write_json(state_dir / "preflight.json", preflight)
    return preflight


def _execution_environment(target: Path) -> dict[str, str]:
    runtime_root = target / ".harness-runtime"
    home = runtime_root / "home"
    cache = runtime_root / "cache"
    temporary = runtime_root / "tmp"
    for path in (home, cache, temporary):
        path.mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(runtime_root / "config"),
        "XDG_DATA_HOME": str(runtime_root / "data"),
        "TMPDIR": str(temporary),
        "UV_CACHE_DIR": str(cache / "uv"),
        "UV_OFFLINE": "1",
        "PIP_NO_INDEX": "1",
        "npm_config_cache": str(cache / "npm"),
        "npm_config_offline": "true",
        "CARGO_HOME": str(runtime_root / "cargo"),
        "CARGO_NET_OFFLINE": "true",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    for key in ("SYSTEMROOT", "PATHEXT"):
        if key in os.environ:
            environment[key] = os.environ[key]
    return environment


def _run_observed(
    target: Path,
    argv: list[str],
    replacements: dict[str, str],
    environment: dict[str, str],
) -> dict[str, object]:
    completed = subprocess.run(
        argv,
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    stdout = _sanitize(completed.stdout, replacements)
    stderr = _sanitize(completed.stderr, replacements)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
    }


def _mutation_probe(
    target: Path,
    path: str,
    argv: list[str],
    replacements: dict[str, str],
    environment: dict[str, str],
) -> dict[str, object]:
    source = target / path
    hidden = source.with_name(f".{source.name}.observer-missing")
    source.rename(hidden)
    try:
        observation = _run_observed(target, argv, replacements, environment)
    finally:
        hidden.rename(source)
    observation["mutation"] = f"missing:{path}"
    if observation["exit_code"] == 0:
        raise ValueError(f"target command did not detect its missing required input: {argv}")
    return observation


def _run_common_harness_cycle(
    target: Path,
    contract: dict[str, Any],
    replacements: dict[str, str],
    environment: dict[str, str],
) -> dict[str, object]:
    common_harness = _mapping(contract, "common_harness")
    commands = _mapping(common_harness, "commands")
    observations: dict[str, object] = {}
    for name in (
        "hook_render",
        "hook_parity",
        "memory_init",
        "memory_sync",
        "memory_doctor",
        "context_pull",
    ):
        argv = commands.get(name)
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            raise ValueError(f"common harness command {name} is invalid")
        observation = _run_observed(target, argv, replacements, environment)
        observations[name] = observation
        if observation["exit_code"] != 0:
            raise ValueError(f"common harness command failed: {name}")

    paths = _mapping(common_harness, "paths")
    database = target / str(paths["database"])
    if not database.is_file():
        raise ValueError("common harness commands did not create the memory database")
    doctor = _mapping(observations, "memory_doctor")
    try:
        doctor_payload = json.loads(str(doctor["stdout"]))
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError("memory doctor did not emit valid JSON evidence") from exc
    if not isinstance(doctor_payload, dict) or doctor_payload.get("status") != "ready":
        raise ValueError("memory doctor did not report ready")
    purpose = _mapping(contract, "intent")["purpose"]
    context = _mapping(observations, "context_pull")
    normalized_purpose = " ".join(str(purpose).split())
    normalized_context = " ".join(str(context.get("stdout", "")).split())
    if normalized_purpose not in normalized_context:
        raise ValueError("context pull did not recover the project purpose from memory")
    return observations


def _probe_hook_requires_memory(
    target: Path,
    contract: dict[str, Any],
    replacements: dict[str, str],
    environment: dict[str, str],
) -> dict[str, object]:
    common_harness = _mapping(contract, "common_harness")
    paths = _mapping(common_harness, "paths")
    database = target / str(paths["database"])
    hook_log = target / ".git" / "project-agent-kit-pre-commit.log"
    hook_log_before = hook_log.read_bytes()
    moved: list[tuple[Path, Path]] = []
    for suffix in ("", "-wal", "-shm"):
        source = Path(f"{database}{suffix}")
        if source.exists():
            hidden = source.with_name(f".{source.name}.observer-missing")
            source.rename(hidden)
            moved.append((source, hidden))
    try:
        hook_environment = {**environment, "PROJECT_AGENT_KIT_HOOK_PHASE": "direct"}
        observation = _run_observed(
            target,
            [str(paths["memory_sync_hook"])],
            replacements,
            hook_environment,
        )
    finally:
        hook_log.write_bytes(hook_log_before)
        for source, hidden in reversed(moved):
            hidden.rename(source)
    observation["mutation"] = f"missing:{paths['database']}"
    if observation["exit_code"] == 0:
        raise ValueError("pre-commit hook succeeded without the required memory database")
    return observation


def _tracked_paths(target: Path) -> set[str]:
    return set(_run_git(target, "ls-files").splitlines())


def _product_file_count(target: Path, contract: dict[str, Any]) -> int:
    foundation = _mapping(contract, "foundation")
    reviewer_paths = {
        path.relative_to(target).as_posix()
        for pattern in (
            ".claude/agents/*-code-reviewer.md",
            ".codex/agents/*-code-reviewer.toml",
            ".claude/skills/*-code-review/SKILL.md",
            ".agents/skills/*-code-review/SKILL.md",
        )
        for path in target.glob(pattern)
    }
    allowed = BASE_TARGET_FILES | reviewer_paths | {
        foundation["manifest"],
        foundation["lockfile"],
        *foundation["compile_targets"],
        *foundation["smoke_tests"],
    }
    return len(_tracked_paths(target) - allowed)


def collect(
    state_dir: Path,
    evidence_root: Path,
    runtime: str,
    runtime_version: str,
    run_id: str,
    runtime_log_path: Path,
) -> Path:
    state_dir = state_dir.resolve()
    preflight = json.loads((state_dir / "preflight.json").read_text(encoding="utf-8"))
    target = Path(preflight["target"]).resolve()
    evidence_root = evidence_root.resolve()
    runtime_log_path = runtime_log_path.resolve()
    outside_paths = [Path(path) for path in preflight["outside_paths"]]
    if runtime not in ("claude", "codex"):
        raise ValueError("runtime must be claude or codex")
    if not runtime_version.strip() or not run_id.strip():
        raise ValueError("runtime version and run id must be non-empty")
    if any(
        _is_within(evidence_root, boundary) or _is_within(boundary, evidence_root)
        for boundary in (target, state_dir)
    ):
        raise ValueError("evidence root must be isolated from target and observer state")
    if not _is_within(runtime_log_path, state_dir):
        raise ValueError("runtime log input must be inside the observer state directory")
    if content_hashes(ROOT) != (
        preflight["binding"]["prompt_template_sha256"],
        preflight["binding"]["purpose_sha256"],
        preflight["binding"]["rendered_prompt_sha256"],
        preflight["binding"]["recipe_sha256"],
    ):
        raise ValueError("provider recipe changed after preflight")
    if _run_git(target, "status", "--porcelain"):
        raise ValueError("target worktree must be clean before observation")
    if _run_git(target, "branch", "--show-current") != "main":
        raise ValueError("target branch must be main")
    if int(_run_git(target, "rev-list", "--count", "HEAD")) != 1:
        raise ValueError("target must have exactly one commit")
    if _run_git(target, "log", "-1", "--format=%s") != COMMIT_MESSAGE:
        raise ValueError("target initial commit message is incorrect")
    remotes = _run_git(target, "remote").splitlines()
    hooks_path = _run_git(target, "config", "--get", "core.hooksPath")
    hook_log_path = target / ".git" / "project-agent-kit-pre-commit.log"
    hook_log = hook_log_path.read_text(encoding="utf-8").splitlines()
    if remotes or hooks_path != ".githooks" or hook_log != ["direct:0", "commit:0"]:
        raise ValueError("target Git or hook observation does not satisfy the recipe")
    local_keys = set(
        _run_git(target, "config", "--local", "--name-only", "--list").splitlines()
    )
    unexpected_local_keys = sorted(local_keys - ALLOWED_TARGET_LOCAL_GIT_KEYS)
    if unexpected_local_keys:
        raise ValueError(f"target contains unauthorized local Git config: {unexpected_local_keys}")
    if _git_policy(target) != preflight["git_policy"]:
        raise ValueError("target overrides the effective Git identity or signing policy")
    if str(preflight["git_policy"].get("commit.gpgsign", "")).lower() == "true":
        signature = _run_git(target, "log", "-1", "--format=%G?")
        if signature not in {"G", "U", "X", "Y", "R"}:
            raise ValueError("initial commit did not preserve the required signing policy")

    contract = _target_contract(target)
    result = {
        "ready_marker": "READY_FOR_DEVELOPMENT_PLANNING",
        "artifacts": "pass",
        "generated_parity": "pass",
        "read_only_reviewer": "pass",
        "lint_exit_code": 0,
        "build_exit_code": 0,
        "test_exit_code": 0,
        "hook_direct_exit_code": 0,
        "hook_commit_invocations": hook_log.count("commit:0"),
        "branch": "main",
        "commit_count": 1,
        "commit_message": COMMIT_MESSAGE,
        "initial_commit": _run_git(target, "rev-parse", "HEAD"),
        "worktree_clean": True,
        "remote_count": len(remotes),
        "product_implementation_files": _product_file_count(target, contract),
    }
    static_evidence = {
        "binding": preflight["binding"],
        "observation": {"target_tree_sha256": tracked_tree_sha256(target)},
        "result": result,
    }
    _verify_target_checkout(target, static_evidence)

    common_paths = _mapping(_mapping(contract, "common_harness"), "paths")
    memory_database = target / str(common_paths["database"])
    if not memory_database.is_file():
        raise ValueError("target did not create the required memory database before observation")
    target_replacements = {
        str(target): "<TARGET_ROOT>",
        str(ROOT): "<PROVIDER_ROOT>",
        str(state_dir): "<OBSERVER_STATE>",
        str(Path.home()): "<HOME>",
        **{
            str(path): f"<OUTSIDE_{index}>"
            for index, path in enumerate(outside_paths, start=1)
        },
    }
    target_environment = _execution_environment(target)
    common_initial = _run_common_harness_cycle(
        target,
        contract,
        target_replacements,
        target_environment,
    )
    missing_database_hook = _probe_hook_requires_memory(
        target,
        contract,
        target_replacements,
        target_environment,
    )
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{memory_database}{suffix}")
        if candidate.exists():
            candidate.unlink()
    common_rehydrated = _run_common_harness_cycle(
        target,
        contract,
        target_replacements,
        target_environment,
    )
    if _run_git(target, "status", "--porcelain"):
        raise ValueError("common harness verification changed the tracked target worktree")

    commands = _mapping(contract, "commands")
    observed_commands: dict[str, object] = {}
    observed_probes: dict[str, object] = {}
    runtime_area = target / ".harness-runtime"
    runtime_area.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="observer-checkout-", dir=runtime_area) as raw:
        sandbox = Path(raw) / "target"
        completed = subprocess.run(
            ["git", "clone", "-q", "--no-hardlinks", str(target), str(sandbox)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ValueError(f"cannot create target verification sandbox: {completed.stderr}")
        replacements = {
            str(sandbox): "<TARGET_SANDBOX>",
            str(target): "<TARGET_ROOT>",
            str(ROOT): "<PROVIDER_ROOT>",
            str(state_dir): "<OBSERVER_STATE>",
            str(Path.home()): "<HOME>",
            **{
                str(path): f"<OUTSIDE_{index}>"
                for index, path in enumerate(outside_paths, start=1)
            },
        }
        environment = _execution_environment(sandbox)
        for name in ("generated_parity", "lint", "build", "test"):
            argv = commands[name]
            if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
                raise ValueError(f"target command {name} is invalid")
            observation = _run_observed(sandbox, argv, replacements, environment)
            observed_commands[name] = observation
            if observation["exit_code"] != 0:
                raise ValueError(f"target command failed: {name}")

        foundation = _mapping(contract, "foundation")
        generation = _mapping(contract, "generation")
        probe_specs = {
            "parity_skill_source": (
                generation["canonical"][0],
                commands["generated_parity"],
            ),
            "parity_agent_source": (
                generation["canonical"][1],
                commands["generated_parity"],
            ),
            "parity_skill": (generation["generated"][0], commands["generated_parity"]),
            "parity_agent": (generation["generated"][1], commands["generated_parity"]),
            "lint_missing_compile": (foundation["compile_targets"][0], commands["lint"]),
            "build_missing_compile": (foundation["compile_targets"][0], commands["build"]),
            "build_missing_manifest": (foundation["manifest"], commands["build"]),
            "build_missing_lock": (foundation["lockfile"], commands["build"]),
            "test_missing_smoke": (foundation["smoke_tests"][0], commands["test"]),
        }
        for name, (relative, argv) in probe_specs.items():
            observed_probes[name] = _mutation_probe(
                sandbox, relative, argv, replacements, environment
            )
        restored = _run_observed(
            sandbox, commands["generated_parity"], replacements, environment
        )
        if restored["exit_code"] != 0 or _run_git(sandbox, "status", "--porcelain"):
            raise ValueError("target verification sandbox did not restore after mutation probes")
    if _run_git(target, "status", "--porcelain"):
        raise ValueError("target worktree changed during verification")

    provider_after = _provider_snapshot(ROOT)
    outside_after = _outside_snapshot(outside_paths)
    provider_before_path = state_dir / "provider-before.json"
    outside_before_path = state_dir / "outside-before.json"
    provider_before = json.loads(provider_before_path.read_text(encoding="utf-8"))
    outside_before = json.loads(outside_before_path.read_text(encoding="utf-8"))
    if provider_after != provider_before or outside_after != outside_before:
        raise ValueError("provider or declared outside state changed during the clean-room run")

    raw_runtime_log = runtime_log_path.read_text(encoding="utf-8")
    runtime_log = _sanitize(raw_runtime_log, replacements)
    if runtime_log.count("READY_FOR_DEVELOPMENT_PLANNING") != 1:
        raise ValueError("runtime log must contain exactly one READY marker")

    run_root = evidence_root / runtime
    if run_root.exists() and any(run_root.iterdir()):
        raise ValueError("runtime evidence directory must be absent or empty")
    run_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(provider_before_path, run_root / "provider-before.json")
    shutil.copy2(outside_before_path, run_root / "outside-before.json")
    _write_json(run_root / "provider-after.json", provider_after)
    _write_json(run_root / "outside-after.json", outside_after)
    (run_root / "runtime.log").write_text(runtime_log, encoding="utf-8")

    bundle = run_root / "target.bundle"
    completed = subprocess.run(
        ["git", "bundle", "create", str(bundle), "main"],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(f"cannot create target bundle: {completed.stderr.strip()}")

    observer_hash = _sha256(ROOT / "scripts/observe_project_agent_kit.py")
    verification = {
        "schema_version": 4,
        "observer_sha256": observer_hash,
        "commands": observed_commands,
        "common_harness": {
            "database_existed_before": True,
            "initial": common_initial,
            "missing_database_hook": missing_database_hook,
            "database_deleted": True,
            "rehydrated": common_rehydrated,
            "database_recreated": memory_database.is_file(),
        },
        "mutation_probes": observed_probes,
        "git": {
            "status_porcelain": "",
            "remotes": remotes,
            "core_hooks_path": hooks_path,
            "hook_log": hook_log,
            "local_config_keys": sorted(local_keys),
            "effective_policy_sha256": hashlib.sha256(
                json.dumps(preflight["git_policy"], sort_keys=True).encode()
            ).hexdigest(),
        },
        "ready_marker_count": 1,
        "hook_commit_invocations": hook_log.count("commit:0"),
    }
    _write_json(run_root / "verification.json", verification)

    prompt_template, purpose, rendered_prompt, recipe = content_hashes(ROOT)
    evidence = {
        "schema_version": 1,
        "runtime": {"name": runtime, "version": runtime_version},
        "binding": {
            "prompt_template_sha256": prompt_template,
            "purpose_sha256": purpose,
            "rendered_prompt_sha256": rendered_prompt,
            "recipe_sha256": recipe,
            "provider_revision": preflight["binding"]["provider_revision"],
        },
        "observation": {
            "run_id": run_id,
            "before_empty": preflight["before_empty"],
            "outside_existing_worktree": preflight["outside_existing_worktree"],
            "provider_before_sha256": _sha256(run_root / "provider-before.json"),
            "provider_after_sha256": _sha256(run_root / "provider-after.json"),
            "outside_before_sha256": _sha256(run_root / "outside-before.json"),
            "outside_after_sha256": _sha256(run_root / "outside-after.json"),
            "target_tree_sha256": tracked_tree_sha256(target),
            "target_bundle_sha256": _sha256(bundle),
            "verification_log_sha256": _sha256(run_root / "verification.json"),
            "runtime_log_sha256": _sha256(run_root / "runtime.log"),
        },
        "result": result,
    }
    _write_json(run_root / "evidence.json", evidence)
    validate_evidence_payload(
        evidence,
        expected_runtime=runtime,
        prompt_template_sha256=prompt_template,
        purpose_sha256=purpose,
        rendered_prompt_sha256=rendered_prompt,
        recipe_sha256=recipe,
    )
    _verify_run_artifacts(run_root, evidence, ROOT)
    if _run_git(target, "status", "--porcelain"):
        raise ValueError("target worktree changed while evidence was written")
    return run_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--target", type=Path, required=True)
    prepare_parser.add_argument("--state-dir", type=Path, required=True)
    prepare_parser.add_argument("--outside", type=Path, action="append", required=True)
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--state-dir", type=Path, required=True)
    collect_parser.add_argument("--evidence-root", type=Path, required=True)
    collect_parser.add_argument("--runtime", choices=("claude", "codex"), required=True)
    collect_parser.add_argument("--runtime-version", required=True)
    collect_parser.add_argument("--run-id", required=True)
    collect_parser.add_argument("--runtime-log", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            report = prepare(args.target, args.state_dir, args.outside)
            print(json.dumps({"status": "prepared", "target": report["target"]}))
        else:
            run_root = collect(
                args.state_dir,
                args.evidence_root,
                args.runtime,
                args.runtime_version,
                args.run_id,
                args.runtime_log,
            )
            print(json.dumps({"status": "collected", "evidence": str(run_root)}))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"project agent kit observer: ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
