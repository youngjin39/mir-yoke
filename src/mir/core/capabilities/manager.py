"""Pinned, fail-closed capability synchronization for shared Mir plugins."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .config import CapabilityConfig, load_capability_config

_SHA = re.compile(r"^[0-9a-f]{40}$")
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_PLUGIN_ROOT_ENTRIES = {".claude-plugin", ".codex-plugin", "skills"}
_PLUGIN_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_RUNTIMES = ("claude-code", "codex-cli-desktop")
_SESSION_ENV = {
    "claude-code": ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"),
    "codex-cli-desktop": ("CODEX_THREAD_ID", "CODEX_SESSION_ID"),
}


class CapabilityError(RuntimeError):
    """Capability state is unsafe, divergent, or unavailable."""


Run = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def _run_process(args: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, **kwargs)  # noqa: S603 - fixed executable and argv-only calls


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    return environment


class GitClient:
    """Minimal git transport with no shell, prompts, hooks, or broad checkout."""

    def __init__(self, runner: Run = _run_process) -> None:
        self._runner = runner

    def _run(self, args: Sequence[str], *, cwd: Path | None = None) -> str:
        completed = self._runner(
            list(args),
            cwd=cwd,
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "git failed"
            raise CapabilityError(detail)
        return completed.stdout

    def resolve(self, url: str, ref: str) -> str:
        output = self._run(
            [
                "git",
                "ls-remote",
                "--exit-code",
                url,
                f"refs/heads/{ref}",
                f"refs/tags/{ref}",
                f"refs/tags/{ref}^{{}}",
            ]
        )
        candidates: list[tuple[str, str]] = []
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 2 and _SHA.fullmatch(fields[0]):
                candidates.append((fields[1], fields[0]))
        if not candidates:
            raise CapabilityError(f"source ref not found: {ref}")
        peeled = [sha for name, sha in candidates if name.endswith("^{}")]
        return peeled[0] if peeled else candidates[0][1]

    def export(
        self,
        url: str,
        ref: str,
        commit: str,
        paths: Sequence[str],
        destination: Path,
    ) -> None:
        destination.mkdir(parents=True, exist_ok=False)
        self._run(["git", "init", "--quiet"], cwd=destination)
        self._run(["git", "remote", "add", "origin", url], cwd=destination)
        try:
            self._run(
                [
                    "git",
                    "-c",
                    "protocol.file.allow=never",
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    "origin",
                    commit,
                ],
                cwd=destination,
            )
        except CapabilityError:
            self._run(
                [
                    "git",
                    "-c",
                    "protocol.file.allow=never",
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    "origin",
                    ref,
                ],
                cwd=destination,
            )
        fetched = self._run(["git", "rev-parse", "FETCH_HEAD^{commit}"], cwd=destination).strip()
        if fetched != commit:
            raise CapabilityError(
                f"fetched commit {fetched!r} does not match required commit {commit!r}"
            )
        gitmodules = self._run(
            ["git", "ls-tree", "--name-only", commit, "--", ".gitmodules"],
            cwd=destination,
        )
        if gitmodules.strip():
            raise CapabilityError("capability source contains a submodule declaration")
        listing = self._run(
            ["git", "ls-tree", "-z", "-r", "-t", commit, "--", *paths], cwd=destination
        )
        found_paths: set[str] = set()
        for line in listing.split("\0"):
            metadata, separator, raw_path = line.partition("\t")
            if not separator:
                continue
            mode = metadata.split(" ", 1)[0]
            if mode in {"120000", "160000"}:
                raise CapabilityError(f"remote symlink or submodule rejected: {raw_path}")
            if mode == "100755":
                raise CapabilityError(f"remote executable content rejected: {raw_path}")
            found_paths.add(raw_path)
        for required in paths:
            prefix = f"{required}/"
            if required not in found_paths and not any(
                path.startswith(prefix) for path in found_paths
            ):
                raise CapabilityError(f"required capability path is missing: {required}")
        self._run(
            [
                "git",
                "-c",
                f"core.hooksPath={os.devnull}",
                "checkout",
                "--quiet",
                commit,
                "--",
                *paths,
            ],
            cwd=destination,
        )
        shutil.rmtree(destination / ".git")


def default_capability_home() -> Path:
    override = os.environ.get("MIR_CAPABILITY_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Mir" / "capabilities"
    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Caches" / "mir" / "capabilities"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mir" / "capabilities"


def sys_platform() -> str:
    """Small seam for platform-specific cache tests."""
    import sys

    return sys.platform


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityError(f"invalid JSON state file: {path}") from exc
    if not isinstance(value, dict):
        raise CapabilityError(f"JSON state file must contain an object: {path}")
    return value


def _configured_provider_home(codex_home: Path, source_url: str) -> Path | None:
    """Recover a verified external provider root from persistent Codex state."""
    config_path = codex_home / "config.toml"
    if not config_path.is_file():
        return None
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    marketplaces = config.get("marketplaces")
    marketplace = marketplaces.get("mir-yoke") if isinstance(marketplaces, dict) else None
    if not isinstance(marketplace, dict) or marketplace.get("source_type") != "local":
        return None
    raw_source = marketplace.get("source")
    if not isinstance(raw_source, str):
        return None
    source = Path(raw_source).expanduser().resolve()
    if source.name != "active" or source.is_symlink() or not source.is_dir():
        return None
    receipt = _read_json(source.parent / "active.json")
    if receipt is None or receipt.get("source_url") != source_url:
        return None
    materialized_root = receipt.get("materialized_root")
    if not isinstance(materialized_root, str):
        return None
    if Path(materialized_root).expanduser().resolve() != source:
        return None
    return source.parent


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise CapabilityError(f"capability tree is not a real directory: {root}")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CapabilityError(f"capability tree contains a symlink: {path}")
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.is_file():
            if path.stat().st_mode & 0o111:
                raise CapabilityError(f"capability tree contains executable content: {path}")
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CapabilityError(f"capability file is missing or linked: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_plugin(plugin_root: Path, expected_name: str) -> str:
    entries = {path.name for path in plugin_root.iterdir()}
    if entries != _PLUGIN_ROOT_ENTRIES:
        extra = ", ".join(sorted(entries - _PLUGIN_ROOT_ENTRIES)) or "none"
        raise CapabilityError(f"non-skill plugin content rejected in {expected_name}: {extra}")
    manifests: list[dict[str, object]] = []
    for runtime in ("claude", "codex"):
        manifest_path = plugin_root / f".{runtime}-plugin" / "plugin.json"
        payload = _read_json(manifest_path)
        if payload is None or payload.get("name") != expected_name:
            raise CapabilityError(f"invalid {runtime} manifest for {expected_name}")
        manifests.append(payload)
    if manifests[0].get("version") != manifests[1].get("version"):
        raise CapabilityError(f"dual-runtime manifest version drift for {expected_name}")
    if manifests[1].get("skills") != "./skills/":
        raise CapabilityError(f"Codex skills path drift for {expected_name}")
    for forbidden in ("hooks", "mcpServers", "apps", "scripts", "agents"):
        if any(forbidden in manifest for manifest in manifests):
            raise CapabilityError(f"remote plugin component rejected: {expected_name}.{forbidden}")

    skill_files = list((plugin_root / "skills").glob("*/SKILL.md"))
    if not skill_files:
        raise CapabilityError(f"plugin has no skills: {expected_name}")
    for markdown in plugin_root.rglob("*.md"):
        text = markdown.read_text(encoding="utf-8")
        if "archive/skills/" in text or "memory_gc_runner.py" in text:
            raise CapabilityError(f"plugin references an unavailable resource: {markdown}")
        for target in _MARKDOWN_LINK.findall(text):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "#")):
                continue
            if "\\" in target or PurePosixPath(target).is_absolute():
                raise CapabilityError(f"unsafe plugin link in {markdown}: {target}")
            resolved = (markdown.parent / target).resolve()
            try:
                resolved.relative_to(plugin_root.resolve())
            except ValueError as exc:
                raise CapabilityError(
                    f"plugin link escapes its root: {markdown}: {target}"
                ) from exc
            if not resolved.exists():
                raise CapabilityError(f"plugin link target is missing: {markdown}: {target}")
    return _tree_digest(plugin_root)


def _consumer_key(project_root: Path) -> str:
    return os.path.normcase(str(project_root.resolve()))


def _skill_names(checkout: Path, config: CapabilityConfig, plugins: Sequence[str]) -> set[str]:
    names: set[str] = set()
    for plugin in plugins:
        root = checkout / config.plugins[plugin] / "skills"
        names.update(path.parent.name for path in root.glob("*/SKILL.md"))
    return names


def _standalone_collisions(skill_names: set[str], project_root: Path, user_home: Path) -> list[str]:
    roots = (
        user_home / ".claude" / "skills",
        user_home / ".agents" / "skills",
        project_root / ".claude" / "skills",
        project_root / ".agents" / "skills",
    )
    collisions: list[str] = []
    for root in roots:
        for name in sorted(skill_names):
            candidate = root / name
            if candidate.exists() or candidate.is_symlink():
                collisions.append(str(candidate))
    return collisions


@contextmanager
def _apply_guard(capability_home: Path) -> Iterator[None]:
    capability_home.mkdir(parents=True, exist_ok=True)
    guard = capability_home / ".apply.lock"
    try:
        guard.mkdir()
    except FileExistsError as exc:
        raise CapabilityError(f"another capability apply is active: {guard}") from exc
    try:
        yield
    finally:
        guard.rmdir()


class CapabilityManager:
    """Status, check, sync, and update operations for a project consumer."""

    def __init__(
        self,
        project_root: Path,
        *,
        config_path: Path | None = None,
        capability_home: Path | None = None,
        user_home: Path | None = None,
        codex_home: Path | None = None,
        git: GitClient | None = None,
        command_runner: Run = _run_process,
        which: Which = shutil.which,
    ) -> None:
        self.project_root = project_root.resolve()
        self.config_path = config_path or self.project_root / "config" / "capability-sources.json"
        self.config = load_capability_config(self.config_path)
        self.user_home = (user_home or Path.home()).resolve()
        raw_codex_home = os.environ.get("CODEX_HOME")
        configured_codex_home = codex_home or (
            Path(raw_codex_home) if raw_codex_home else self.user_home / ".codex"
        )
        self.codex_home = configured_codex_home.expanduser().resolve()
        configured_capability_home = capability_home
        if configured_capability_home is None and "MIR_CAPABILITY_HOME" not in os.environ:
            configured_capability_home = _configured_provider_home(
                self.codex_home, self.config.source_url
            )
        self.capability_home = (
            configured_capability_home or default_capability_home()
        ).expanduser().resolve()
        self.git = git or GitClient()
        self.command_runner = command_runner
        self.which = which
        self.lock_path = self.project_root / ".mir" / "capability-lock.json"
        self.registry_path = self.capability_home / "consumers.json"
        self.active_path = self.capability_home / "active"
        self.active_receipt_path = self.capability_home / "active.json"

    def _load_lock(self) -> dict[str, object] | None:
        return _read_json(self.lock_path)

    def _load_registry(self) -> dict[str, object]:
        return _read_json(self.registry_path) or {
            "schema_version": 1,
            "active_commit": None,
            "consumers": {},
        }

    def _profile(self, requested: str | None, lock: dict[str, object] | None):
        value = requested or (lock.get("profile") if lock else None) or "default"
        if not isinstance(value, str):
            raise CapabilityError("capability lock profile is invalid")
        return self.config.resolve_profile(value)

    def _agent_status(
        self, lock: dict[str, object] | None, selected_agents: Sequence[str]
    ) -> dict[str, str]:
        locked_agents = lock.get("agents", {}) if lock else {}
        if not isinstance(locked_agents, dict):
            raise CapabilityError("capability lock agents field is invalid")
        result: dict[str, str] = {}
        for source_path in selected_agents:
            metadata = locked_agents.get(source_path)
            target = self.project_root / source_path
            if not isinstance(metadata, dict) or not isinstance(metadata.get("sha256"), str):
                result[source_path] = "unlocked"
            elif not target.is_file() or target.is_symlink():
                result[source_path] = "missing"
            elif _file_digest(target) != metadata["sha256"]:
                result[source_path] = "diverged"
            else:
                result[source_path] = "unchanged"
        return result

    def status(self, profile: str | None = None) -> dict[str, object]:
        lock = self._load_lock()
        resolved_profile, pack = self._profile(profile, lock)
        plugins = pack.plugins
        skill_names: set[str] = set()
        active_receipt = _read_json(self.active_receipt_path)
        if self.active_path.is_dir():
            skill_names = _skill_names(self.active_path, self.config, plugins)
        collisions = _standalone_collisions(
            skill_names or self._configured_skill_names(plugins),
            self.project_root,
            self.user_home,
        )
        registry = self._load_registry()
        consumer = None
        consumers = registry.get("consumers")
        if isinstance(consumers, dict):
            consumer = consumers.get(_consumer_key(self.project_root))
        lock_commit = None
        if lock and isinstance(lock.get("source"), dict):
            lock_commit = lock["source"].get("commit")
        active_commit = active_receipt.get("commit") if active_receipt else None
        active_integrity = self._active_integrity(lock, plugins)
        consumer_integrity = self._consumer_integrity(lock, consumer, plugins)
        agent_status = self._agent_status(lock, pack.agents)
        missing_project_paths = self._missing_project_paths()
        activation = self._activation_evidence(lock) if lock else {"status": "not-synced"}
        discovery = self._discovery_evidence(lock) if lock else {"status": "not-synced"}
        ready = bool(
            lock
            and _SHA.fullmatch(str(lock_commit))
            and active_commit == lock_commit
            and active_integrity
            and isinstance(consumer, dict)
            and consumer.get("commit") == lock_commit
            and consumer_integrity
            and not collisions
            and not missing_project_paths
            and all(value == "unchanged" for value in agent_status.values())
            and activation.get("status") == "active"
            and discovery.get("status") == "verified"
        )
        return {
            "operation": "status",
            "dry_run": True,
            "ready": ready,
            "profile": resolved_profile,
            "plugins": list(plugins),
            "required_commit": lock_commit,
            "active_commit": active_commit,
            "active_integrity": active_integrity,
            "consumer_integrity": consumer_integrity,
            "collisions": collisions,
            "missing_project_paths": missing_project_paths,
            "agent_status": agent_status,
            "runtime_support": self.config.runtime_support,
            "registration": lock.get("registration") if lock else None,
            "activation": activation,
            "discovery": discovery,
        }

    def _configured_skill_names(self, plugins: Sequence[str]) -> set[str]:
        return {skill for plugin in plugins for skill in self.config.plugin_skills[plugin]}

    def _missing_project_paths(self) -> list[str]:
        missing: list[str] = []
        for path in self.config.required_project_paths:
            target = self.project_root / path
            if not target.exists() or target.is_symlink():
                missing.append(path)
        return missing

    def _project_target(self, relative: str) -> Path:
        target = self.project_root / relative
        current = target.parent
        while current != self.project_root:
            if current.is_symlink():
                raise CapabilityError(f"project target parent is a symlink: {relative}")
            current = current.parent
        try:
            target.parent.resolve().relative_to(self.project_root)
        except ValueError as exc:
            raise CapabilityError(f"project target escapes repository: {relative}") from exc
        return target

    def _active_integrity(self, lock: dict[str, object] | None, plugins: Sequence[str]) -> bool:
        if lock is None:
            return False
        locked_plugins = lock.get("plugins")
        if not isinstance(locked_plugins, dict):
            return False
        for plugin in plugins:
            metadata = locked_plugins.get(plugin)
            if not isinstance(metadata, dict) or not isinstance(metadata.get("sha256"), str):
                return False
            try:
                actual = _tree_digest(self.active_path / self.config.plugins[plugin])
            except CapabilityError:
                return False
            if actual != metadata["sha256"]:
                return False
        return True

    def _consumer_integrity(
        self,
        lock: dict[str, object] | None,
        consumer: object,
        plugins: Sequence[str],
    ) -> bool:
        if lock is None or not isinstance(consumer, dict):
            return False
        locked_plugins = lock.get("plugins")
        required = consumer.get("plugins")
        if not isinstance(locked_plugins, dict) or not isinstance(required, dict):
            return False
        for plugin in plugins:
            metadata = locked_plugins.get(plugin)
            if not isinstance(metadata, dict) or required.get(plugin) != metadata.get("sha256"):
                return False
        return True

    def check(self, profile: str | None = None) -> dict[str, object]:
        return self._execute("check", profile=profile, apply=False)

    def sync(self, profile: str | None = None, *, apply: bool = False) -> dict[str, object]:
        return self._execute("sync", profile=profile, apply=apply)

    def update(self, profile: str | None = None, *, apply: bool = False) -> dict[str, object]:
        return self._execute("update", profile=profile, apply=apply)

    def _expected_runtime_skills(self, lock: dict[str, object]) -> set[str]:
        plugins = lock.get("plugins")
        if not isinstance(plugins, dict):
            raise CapabilityError("capability lock plugins field is invalid")
        return {
            f"{plugin}:{skill}"
            for plugin in plugins
            if plugin in self.config.plugin_skills
            for skill in self.config.plugin_skills[plugin]
        }

    def _current_session_id(self, runtime: str) -> str | None:
        for variable in _SESSION_ENV[runtime]:
            value = os.environ.get(variable)
            if value:
                return value
        return None

    def attest(
        self,
        runtime: str,
        observed_skills: Sequence[str],
        *,
        apply: bool = False,
    ) -> dict[str, object]:
        if runtime not in _RUNTIMES:
            raise CapabilityError(f"unsupported runtime attestation: {runtime}")
        lock = self._load_lock()
        if lock is None:
            raise CapabilityError("capabilities must be synced before runtime attestation")
        active_receipt = _read_json(self.active_receipt_path)
        source = lock.get("source")
        commit = source.get("commit") if isinstance(source, dict) else None
        if (
            active_receipt is None
            or not isinstance(commit, str)
            or active_receipt.get("commit") != commit
        ):
            raise CapabilityError("active provider receipt does not match the project lock")

        expected = self._expected_runtime_skills(lock)
        observed = {skill.strip() for skill in observed_skills if skill.strip()}
        missing = sorted(expected - observed)
        resolved_session = self._current_session_id(runtime)
        session_valid = bool(
            isinstance(resolved_session, str) and _SESSION_ID.fullmatch(resolved_session)
        )
        consumer_key = _consumer_key(self.project_root)
        installation_sessions = active_receipt.get("installation_sessions")
        installation_session = None
        if isinstance(installation_sessions, dict):
            consumer_sessions = installation_sessions.get(consumer_key)
            if isinstance(consumer_sessions, dict):
                installation_session = consumer_sessions.get(runtime)
        new_session = bool(
            session_valid
            and (
                not isinstance(installation_session, str)
                or resolved_session != installation_session
            )
        )

        activation = self._activation_evidence(lock, require_active_receipt=False)
        runtimes = activation.get("runtimes")
        runtime_evidence = runtimes.get(runtime) if isinstance(runtimes, dict) else None
        runtime_verified = bool(
            isinstance(runtime_evidence, dict) and runtime_evidence.get("verified") is True
        )
        result: dict[str, object] = {
            "operation": "attest",
            "dry_run": not apply,
            "runtime": runtime,
            "session_id": resolved_session,
            "missing_skills": missing,
            "runtime_verified": runtime_verified,
            "new_session": new_session,
            "attestation_kind": "operator-observed-runtime-catalog",
            "ready_to_attest": not missing and runtime_verified and new_session,
        }
        if not apply:
            return result
        if missing:
            raise CapabilityError(
                "runtime skill discovery is missing expected skills: " + ", ".join(missing)
            )
        if not session_valid:
            raise CapabilityError(
                "runtime attestation requires a valid session id exposed by the "
                "current runtime environment"
            )
        if not new_session:
            raise CapabilityError("runtime attestation requires a new runtime session")
        if not runtime_verified:
            raise CapabilityError("runtime plugin installation could not be verified")

        plugins = lock.get("plugins")
        assert isinstance(plugins, dict)  # validated by _expected_runtime_skills
        plugin_hashes = {
            name: metadata["sha256"]
            for name, metadata in plugins.items()
            if isinstance(metadata, dict) and isinstance(metadata.get("sha256"), str)
        }
        discovery = active_receipt.setdefault("discovery", {})
        if not isinstance(discovery, dict):
            raise CapabilityError("active provider discovery receipt is invalid")
        consumer_discovery = discovery.setdefault(consumer_key, {})
        if not isinstance(consumer_discovery, dict):
            raise CapabilityError("consumer discovery receipt is invalid")
        timestamp = datetime.now(UTC).isoformat()
        consumer_discovery[runtime] = {
            "commit": commit,
            "plugins": plugin_hashes,
            "session_id": resolved_session,
            "observed_skills": sorted(observed),
            "attestation_kind": "operator-observed-runtime-catalog",
            "attested_at": timestamp,
        }
        active_receipt["updated_at"] = timestamp
        _atomic_write_json(self.active_receipt_path, active_receipt)
        result.update({"dry_run": False, "status": "attested", "attested_at": timestamp})
        return result

    def _discovery_evidence(self, lock: dict[str, object]) -> dict[str, object]:
        active_receipt = _read_json(self.active_receipt_path)
        source = lock.get("source")
        plugins = lock.get("plugins")
        commit = source.get("commit") if isinstance(source, dict) else None
        expected_skills = self._expected_runtime_skills(lock)
        assert isinstance(plugins, dict)  # validated by _expected_runtime_skills
        expected_plugins = {
            name: metadata.get("sha256")
            for name, metadata in plugins.items()
            if isinstance(metadata, dict)
        }
        consumer_receipts = None
        if isinstance(active_receipt, dict):
            discovery = active_receipt.get("discovery")
            if isinstance(discovery, dict):
                candidate = discovery.get(_consumer_key(self.project_root))
                if isinstance(candidate, dict):
                    consumer_receipts = candidate

        evidence: dict[str, object] = {}
        required_runtimes = set(self.config.required_runtimes)
        verified = True
        for runtime in _RUNTIMES:
            required = runtime in required_runtimes
            receipt = (
                consumer_receipts.get(runtime) if isinstance(consumer_receipts, dict) else None
            )
            if not isinstance(receipt, dict):
                evidence[runtime] = {"status": "missing", "required": required}
                if required:
                    verified = False
                continue
            observed = receipt.get("observed_skills")
            observed_set = (
                {item for item in observed if isinstance(item, str)}
                if isinstance(observed, list)
                else set()
            )
            missing = sorted(expected_skills - observed_set)
            session_id = receipt.get("session_id")
            if receipt.get("commit") != commit or receipt.get("plugins") != expected_plugins:
                status = "provider-mismatch"
            elif not isinstance(session_id, str) or _SESSION_ID.fullmatch(session_id) is None:
                status = "session-invalid"
            elif missing:
                status = "skills-missing"
            else:
                status = "verified"
            evidence[runtime] = {
                "status": status,
                "missing_skills": missing,
                "required": required,
            }
            if required:
                verified = verified and status == "verified"
        return {
            "status": "verified" if verified else "incomplete",
            "required_runtimes": list(self.config.required_runtimes),
            "runtimes": evidence,
        }

    def finalize(self, *, apply: bool = False, after_restart: bool = False) -> dict[str, object]:
        lock = self._load_lock()
        if lock is None:
            raise CapabilityError("capabilities must be synced before activation can be finalized")
        evidence = self._activation_evidence(lock, require_active_receipt=False)
        discovery = self._discovery_evidence(lock)
        result: dict[str, object] = {
            "operation": "finalize",
            "dry_run": not apply,
            "after_restart": after_restart,
            "activation": evidence,
            "discovery": discovery,
        }
        if not apply:
            result["ready_to_finalize"] = (
                evidence.get("status") == "verified" and discovery.get("status") == "verified"
            )
            return result
        if not after_restart:
            raise CapabilityError("finalize --apply requires --after-restart attestation")
        if evidence.get("status") != "verified":
            raise CapabilityError("runtime plugin installation could not be verified")
        if discovery.get("status") != "verified":
            raise CapabilityError("required runtime skill discovery receipts are incomplete")
        registration = lock.get("registration")
        if not isinstance(registration, dict):
            raise CapabilityError("capability lock registration field is invalid")
        registration["status"] = "active"
        registration["finalized_at"] = datetime.now(UTC).isoformat()
        _atomic_write_json(self.lock_path, lock)
        active_receipt = _read_json(self.active_receipt_path) or {"schema_version": 1}
        active_receipt["activation"] = evidence.get("runtimes")
        active_receipt["finalized_at"] = registration["finalized_at"]
        _atomic_write_json(self.active_receipt_path, active_receipt)
        result["dry_run"] = False
        result["activation"] = {**evidence, "status": "active"}
        return result

    def _activation_evidence(
        self,
        lock: dict[str, object],
        *,
        require_active_receipt: bool = True,
    ) -> dict[str, object]:
        registration = lock.get("registration")
        plugins = lock.get("plugins")
        if not isinstance(registration, dict) or not isinstance(plugins, dict):
            return {"status": "invalid-lock", "runtimes": {}}
        runtime_results = {
            "claude-code": self._probe_runtime("claude", ["plugin", "list", "--json"], plugins),
            "codex-cli-desktop": self._probe_runtime(
                "codex", ["plugin", "list", "--json"], plugins
            ),
        }
        verified = all(
            runtime_results[runtime].get("verified") is True
            for runtime in self.config.required_runtimes
        )
        if not verified:
            status = "cli-evidence-missing"
        elif require_active_receipt and registration.get("status") != "active":
            status = "restart-required"
        else:
            status = "active" if registration.get("status") == "active" else "verified"
        return {
            "status": status,
            "required_runtimes": list(self.config.required_runtimes),
            "runtimes": runtime_results,
        }

    def _runtime_cwd(self, executable: str) -> Path:
        if executable == "codex" and self.codex_home.is_dir():
            return self.codex_home
        if executable == "claude" and self.user_home.is_dir():
            return self.user_home
        return self.project_root

    def _codex_config(self) -> dict[str, object] | None:
        config_path = self.codex_home / "config.toml"
        if not config_path.is_file():
            return None
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _codex_persistence_error(self, config: dict[str, object] | None, plugin: str) -> str | None:
        if config is None:
            return "codex-config-missing-or-invalid"
        marketplaces = config.get("marketplaces")
        marketplace = marketplaces.get("mir-yoke") if isinstance(marketplaces, dict) else None
        if not isinstance(marketplace, dict):
            return "codex-marketplace-missing"
        if marketplace.get("source_type") != "local":
            return "codex-marketplace-not-local"
        source = marketplace.get("source")
        if not isinstance(source, str):
            return "codex-marketplace-source-missing"
        try:
            source_path = Path(source).expanduser().resolve()
        except OSError:
            return "codex-marketplace-source-invalid"
        if source_path != self.active_path:
            return "codex-marketplace-source-mismatch"
        plugins = config.get("plugins")
        plugin_config = plugins.get(f"{plugin}@mir-yoke") if isinstance(plugins, dict) else None
        if not isinstance(plugin_config, dict) or plugin_config.get("enabled") is not True:
            return "codex-plugin-not-persistently-enabled"
        return None

    def _codex_cache_path(
        self, entry: dict[str, object], plugin: str
    ) -> tuple[Path | None, str | None]:
        version = entry.get("version")
        if not isinstance(version, str) or _PLUGIN_VERSION.fullmatch(version) is None:
            return None, "codex-plugin-version-invalid"
        return (
            self.codex_home / "plugins" / "cache" / "mir-yoke" / plugin / version,
            None,
        )

    def _probe_runtime(
        self,
        executable: str,
        args: Sequence[str],
        locked_plugins: dict[str, object],
    ) -> dict[str, object]:
        resolved = self.which(executable)
        if resolved is None:
            return {"verified": False, "reason": "cli-missing"}
        completed = self.command_runner(
            [resolved, *args],
            cwd=self._runtime_cwd(executable),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return {
                "verified": False,
                "reason": "list-failed",
                "detail": completed.stderr.strip(),
            }
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {"verified": False, "reason": "invalid-json"}
        entries = _plugin_entries(payload)
        codex_config = self._codex_config() if executable == "codex" else None
        evidence: dict[str, object] = {}
        verified = True
        for name, metadata in locked_plugins.items():
            expected = metadata.get("sha256") if isinstance(metadata, dict) else None
            matches = [entry for entry in entries if _plugin_name(entry) == name]
            if len(matches) != 1:
                evidence[name] = {"status": "missing-or-duplicate"}
                verified = False
                continue
            entry = matches[0]
            enabled = entry.get("enabled") is True or entry.get("status") == "enabled"
            if executable == "codex":
                persistence_error = self._codex_persistence_error(codex_config, name)
                installed_path, cache_error = self._codex_cache_path(entry, name)
                path_error = persistence_error or cache_error
            else:
                raw_path = _installed_path(entry)
                installed_path = Path(raw_path).expanduser() if raw_path is not None else None
                path_error = None if installed_path is not None else "installed-path-missing"
            if not enabled:
                evidence[name] = {"status": "disabled"}
                verified = False
            elif path_error is not None or installed_path is None:
                evidence[name] = {"status": path_error or "installed-path-missing"}
                verified = False
            else:
                try:
                    actual = _tree_digest(installed_path)
                except CapabilityError:
                    actual = None
                if actual != expected:
                    evidence[name] = {
                        "status": "digest-mismatch",
                        "installed_path": str(installed_path),
                    }
                    verified = False
                else:
                    evidence[name] = {
                        "status": "enabled",
                        "installed_path": str(installed_path),
                        "sha256": actual,
                    }
        return {"verified": verified, "plugins": evidence}

    def _execute(self, operation: str, *, profile: str | None, apply: bool) -> dict[str, object]:
        lock = self._load_lock()
        resolved_profile, pack = self._profile(profile, lock)
        selected_plugins = pack.plugins
        selected_agents = pack.agents
        remote_commit = self.git.resolve(self.config.source_url, self.config.source_ref)
        locked_commit = None
        if lock and isinstance(lock.get("source"), dict):
            locked_commit = lock["source"].get("commit")
        desired_commit = (
            locked_commit
            if operation == "sync"
            and isinstance(locked_commit, str)
            and _SHA.fullmatch(locked_commit)
            else remote_commit
        )
        if not isinstance(desired_commit, str) or _SHA.fullmatch(desired_commit) is None:
            raise CapabilityError("required capability commit is invalid")

        export_paths = [
            ".claude-plugin/marketplace.json",
            ".agents/plugins/marketplace.json",
            *self.config.plugins.values(),
            *self.config.agents,
        ]
        with tempfile.TemporaryDirectory(prefix="mir-capability-check-") as raw_temp:
            checkout = Path(raw_temp) / "checkout"
            self.git.export(
                self.config.source_url,
                self.config.source_ref,
                desired_commit,
                export_paths,
                checkout,
            )
            plugin_hashes = {
                name: _validate_plugin(checkout / path, name)
                for name, path in self.config.plugins.items()
            }
            for name, expected_skills in self.config.plugin_skills.items():
                actual_skills = {
                    path.parent.name
                    for path in (checkout / self.config.plugins[name] / "skills").glob("*/SKILL.md")
                }
                if actual_skills != set(expected_skills):
                    raise CapabilityError(f"remote plugin skill inventory drift: {name}")
            agent_hashes = {path: _file_digest(checkout / path) for path in self.config.agents}
            skill_names = _skill_names(checkout, self.config, selected_plugins)
            collisions = _standalone_collisions(skill_names, self.project_root, self.user_home)
            agent_changes = self._agent_changes(lock, agent_hashes, selected_agents)
            missing_project_paths = self._missing_project_paths()
            result: dict[str, object] = {
                "operation": operation,
                "dry_run": not apply,
                "profile": resolved_profile,
                "plugins": list(selected_plugins),
                "locked_commit": locked_commit,
                "remote_commit": remote_commit,
                "required_commit": desired_commit,
                "update_available": bool(locked_commit and locked_commit != remote_commit),
                "collisions": collisions,
                "missing_project_paths": missing_project_paths,
                "agent_changes": agent_changes,
                "runtime_support": self.config.runtime_support,
            }
            if operation == "check" or not apply:
                result["ready_to_apply"] = (
                    not collisions
                    and not missing_project_paths
                    and not any(value == "diverged" for value in agent_changes.values())
                )
                return result
            if collisions:
                joined = "\n- ".join(collisions)
                raise CapabilityError(
                    "standalone skill collision detected; move or disable it explicitly before "
                    f"applying (nothing was removed):\n- {joined}"
                )
            if missing_project_paths:
                joined = ", ".join(missing_project_paths)
                raise CapabilityError(f"required project harness paths are missing: {joined}")
            divergent_agents = [
                path for path, state in agent_changes.items() if state == "diverged"
            ]
            if divergent_agents:
                joined = ", ".join(divergent_agents)
                raise CapabilityError(
                    "project-local agents diverged from the trusted source or prior lock; "
                    f"refusing overwrite: {joined}"
                )
            registration = self._apply(
                checkout=checkout,
                commit=desired_commit,
                profile=resolved_profile,
                selected_plugins=selected_plugins,
                selected_agents=selected_agents,
                plugin_hashes=plugin_hashes,
                agent_hashes=agent_hashes,
                previous_lock=lock,
            )
            result["dry_run"] = False
            result["applied"] = True
            result["materialized_root"] = str(self.active_path)
            result["registration_status"] = registration["status"]
            if registration["status"] != "restart-required":
                raise CapabilityError(
                    "runtime plugin registration failed; inspect capability status evidence"
                )
            return result

    def _agent_changes(
        self,
        lock: dict[str, object] | None,
        desired: dict[str, str],
        selected_agents: Sequence[str],
    ) -> dict[str, str]:
        previous = lock.get("agents", {}) if lock else {}
        if not isinstance(previous, dict):
            raise CapabilityError("capability lock agents field is invalid")
        selected = set(selected_agents)
        changes: dict[str, str] = {}
        for path, digest in desired.items():
            old = previous.get(path)
            old_digest = old.get("sha256") if isinstance(old, dict) else None
            target = self._project_target(path)
            if path not in selected:
                if not target.exists() and not target.is_symlink():
                    changes[path] = "absent"
                elif (
                    target.is_file()
                    and not target.is_symlink()
                    and _file_digest(target)
                    in {
                        digest,
                        old_digest,
                    }
                ):
                    changes[path] = "remove"
                else:
                    changes[path] = "diverged"
                continue
            if old_digest is not None:
                if (
                    not target.is_file()
                    or target.is_symlink()
                    or _file_digest(target) != old_digest
                ):
                    changes[path] = "diverged"
                elif old_digest == digest:
                    changes[path] = "unchanged"
                else:
                    changes[path] = "update"
            elif target.is_file() and not target.is_symlink():
                changes[path] = "unchanged" if _file_digest(target) == digest else "diverged"
            else:
                changes[path] = "add"
        return changes

    def _assert_global_version(
        self, commit: str, selected_plugins: Sequence[str], plugin_hashes: dict[str, str]
    ) -> dict[str, object]:
        registry = self._load_registry()
        consumers = registry.get("consumers")
        if not isinstance(consumers, dict):
            raise CapabilityError("global consumer registry is invalid")
        current_key = _consumer_key(self.project_root)
        for root, metadata in consumers.items():
            if root == current_key:
                continue
            if not isinstance(metadata, dict) or metadata.get("commit") != commit:
                raise CapabilityError(
                    f"global capability update conflicts with another registered consumer: {root}"
                )
            required = metadata.get("plugins")
            if not isinstance(required, dict):
                raise CapabilityError(f"global consumer registry entry is invalid: {root}")
            for plugin in selected_plugins:
                if plugin in required and required[plugin] != plugin_hashes[plugin]:
                    raise CapabilityError(
                        "global plugin digest conflicts with another registered consumer: "
                        f"{root} -> {plugin}"
                    )
        return registry

    def _assert_agents_unchanged(self, lock: dict[str, object] | None) -> None:
        if lock is None:
            return
        previous = lock.get("agents")
        if not isinstance(previous, dict):
            raise CapabilityError("capability lock agents field is invalid")
        for source_path, metadata in previous.items():
            if not isinstance(source_path, str) or not isinstance(metadata, dict):
                raise CapabilityError("capability lock agent entry is invalid")
            digest = metadata.get("sha256")
            target = self._project_target(source_path)
            if (
                not isinstance(digest, str)
                or not target.is_file()
                or target.is_symlink()
                or _file_digest(target) != digest
            ):
                raise CapabilityError(
                    f"project-local agent diverged from its lock; refusing overwrite: {source_path}"
                )

    def _apply(
        self,
        *,
        checkout: Path,
        commit: str,
        profile: str,
        selected_plugins: Sequence[str],
        selected_agents: Sequence[str],
        plugin_hashes: dict[str, str],
        agent_hashes: dict[str, str],
        previous_lock: dict[str, object] | None,
    ) -> dict[str, object]:
        self._assert_agents_unchanged(previous_lock)
        registry = self._assert_global_version(commit, selected_plugins, plugin_hashes)
        agent_snapshots = {
            self._project_target(path): (
                self._project_target(path).read_bytes()
                if self._project_target(path).is_file()
                else None
            )
            for path in self.config.agents
        }
        state_paths = (self.lock_path, self.registry_path, self.active_receipt_path)
        state_snapshots = {
            path: path.read_bytes() if path.is_file() else None for path in state_paths
        }
        previous_active_receipt = _read_json(self.active_receipt_path)
        with _apply_guard(self.capability_home):
            stage_parent = self.capability_home / "tmp"
            stage_parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="apply-", dir=stage_parent) as raw_stage:
                staged_active = Path(raw_stage) / "active"
                staged_active.mkdir()
                for relative in (
                    ".claude-plugin/marketplace.json",
                    ".agents/plugins/marketplace.json",
                ):
                    source = checkout / relative
                    target = staged_active / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                for plugin_path in self.config.plugins.values():
                    source = checkout / plugin_path
                    target = staged_active / plugin_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source, target)

                backup = self.capability_home / ".active.previous"
                if self.active_path.is_symlink() or (
                    self.active_path.exists() and not self.active_path.is_dir()
                ):
                    raise CapabilityError("global active capability path is not a real directory")
                if backup.is_symlink() or (backup.exists() and not backup.is_dir()):
                    raise CapabilityError("global capability backup path is unsafe")
                if backup.exists():
                    raise CapabilityError(
                        "a prior capability backup exists; inspect it before applying"
                    )

                old_active_moved = False
                new_active_published = False
                registration_attempted = False
                derivatives_attempted = False
                try:
                    if self.active_path.exists():
                        os.replace(self.active_path, backup)
                        old_active_moved = True
                    os.replace(staged_active, self.active_path)
                    new_active_published = True

                    for source_path in selected_agents:
                        _atomic_write_bytes(
                            self._project_target(source_path),
                            (checkout / source_path).read_bytes(),
                        )
                    for source_path in set(self.config.agents) - set(selected_agents):
                        self._project_target(source_path).unlink(missing_ok=True)

                    selected_hashes = {plugin: plugin_hashes[plugin] for plugin in selected_plugins}
                    consumer_key = _consumer_key(self.project_root)
                    consumers = registry.setdefault("consumers", {})
                    if not isinstance(consumers, dict):
                        raise CapabilityError("global consumer registry is invalid")
                    consumers[consumer_key] = {
                        "commit": commit,
                        "plugins": selected_hashes,
                        "profile": profile,
                    }
                    registry["schema_version"] = 1
                    registry["active_commit"] = commit

                    registration_attempted = True
                    registration = self._install_and_verify(
                        self._registration_plan(selected_plugins),
                        {plugin: {"sha256": plugin_hashes[plugin]} for plugin in selected_plugins},
                    )
                    if registration["status"] != "restart-required":
                        raise CapabilityError("runtime plugin registration failed")
                    derivatives_attempted = True
                    self._regenerate_agent_derivatives()
                    timestamp = datetime.now(UTC).isoformat()
                    lock: dict[str, object] = {
                        "schema_version": 1,
                        "source": {
                            "url": self.config.source_url,
                            "ref": self.config.source_ref,
                            "commit": commit,
                        },
                        "profile": profile,
                        "plugins": {
                            plugin: {
                                "path": self.config.plugins[plugin],
                                "sha256": plugin_hashes[plugin],
                            }
                            for plugin in selected_plugins
                        },
                        "agents": {
                            path: {"sha256": agent_hashes[path], "project_path": path}
                            for path in selected_agents
                        },
                        "registration": {"status": registration["status"]},
                        "synced_at": timestamp,
                    }
                    preserved_discovery: dict[str, object] = {}
                    preserved_installation_sessions: dict[str, object] = {}
                    if (
                        isinstance(previous_active_receipt, dict)
                        and previous_active_receipt.get("commit") == commit
                    ):
                        prior_discovery = previous_active_receipt.get("discovery")
                        if isinstance(prior_discovery, dict):
                            preserved_discovery = dict(prior_discovery)
                        prior_sessions = previous_active_receipt.get("installation_sessions")
                        if isinstance(prior_sessions, dict):
                            preserved_installation_sessions = dict(prior_sessions)
                    preserved_discovery.pop(consumer_key, None)
                    preserved_installation_sessions[consumer_key] = {
                        runtime: value
                        for runtime in _RUNTIMES
                        if (value := self._current_session_id(runtime)) is not None
                    }
                    active_receipt: dict[str, object] = {
                        "schema_version": 1,
                        "commit": commit,
                        "source_url": self.config.source_url,
                        "plugins": selected_hashes,
                        "materialized_root": str(self.active_path),
                        "discovery": preserved_discovery,
                        "installation_sessions": preserved_installation_sessions,
                        "updated_at": timestamp,
                    }
                    _atomic_write_json(self.active_receipt_path, active_receipt)
                    _atomic_write_json(self.registry_path, registry)
                    _atomic_write_json(self.lock_path, lock)
                except Exception as exc:
                    if new_active_published and self.active_path.exists():
                        shutil.rmtree(self.active_path)
                    if old_active_moved and backup.exists():
                        os.replace(backup, self.active_path)
                    for path, body in agent_snapshots.items():
                        if body is None:
                            path.unlink(missing_ok=True)
                        else:
                            _atomic_write_bytes(path, body)
                    derivatives_rollback = True
                    if derivatives_attempted:
                        derivatives_rollback = self._regenerate_agent_derivatives(
                            raise_on_error=False
                        )
                    for path, body in state_snapshots.items():
                        if body is None:
                            path.unlink(missing_ok=True)
                        else:
                            _atomic_write_bytes(path, body)
                    runtime_rollback = True
                    if registration_attempted:
                        runtime_rollback = self._rollback_runtime_registration(
                            selected_plugins, previous_active_receipt
                        )
                    rollback_complete = runtime_rollback and derivatives_rollback
                    detail = "complete" if rollback_complete else "incomplete"
                    raise CapabilityError(
                        f"capability apply failed and local rollback was {detail}: {exc}"
                    ) from exc
                else:
                    if backup.exists():
                        shutil.rmtree(backup)
                    return registration

    def _regenerate_agent_derivatives(self, *, raise_on_error: bool = True) -> bool:
        script = self.project_root / "scripts" / "generate_codex_derivatives.sh"
        bash = self.which("bash")
        if bash is None or not script.is_file() or script.is_symlink():
            if raise_on_error:
                raise CapabilityError(
                    "agent pack activation requires Bash and scripts/generate_codex_derivatives.sh"
                )
            return False
        completed = self.command_runner(
            [bash, str(script)],
            cwd=self.project_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            if raise_on_error:
                detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
                raise CapabilityError(f"agent derivative regeneration failed: {detail}")
            return False
        return True

    def _rollback_runtime_registration(
        self,
        selected_plugins: Sequence[str],
        previous_active_receipt: dict[str, object] | None,
    ) -> bool:
        previous_plugins = (
            previous_active_receipt.get("plugins") if previous_active_receipt else None
        )
        if isinstance(previous_plugins, dict) and previous_plugins:
            expected = {
                name: {"sha256": digest}
                for name, digest in previous_plugins.items()
                if isinstance(name, str) and isinstance(digest, str)
            }
            if expected:
                restored = self._install_and_verify(
                    self._registration_plan(tuple(sorted(expected))), expected
                )
                return restored.get("status") == "restart-required"

        commands = {
            "claude": [
                *(
                    ["plugin", "uninstall", f"{plugin}@mir-yoke", "--scope", "user"]
                    for plugin in selected_plugins
                ),
                ["plugin", "marketplace", "remove", "mir-yoke", "--scope", "user"],
            ],
            "codex": [
                *(
                    ["plugin", "remove", f"{plugin}@mir-yoke", "--json"]
                    for plugin in selected_plugins
                ),
                ["plugin", "marketplace", "remove", "mir-yoke", "--json"],
            ],
        }
        success = True
        for executable, command_group in commands.items():
            resolved = self.which(executable)
            if resolved is None:
                continue
            for args in command_group:
                try:
                    completed = self.command_runner(
                        [resolved, *args],
                        cwd=self._runtime_cwd(executable),
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                except Exception:
                    success = False
                else:
                    success = success and completed.returncode == 0
        return success

    def _registration_plan(self, selected_plugins: Sequence[str]) -> dict[str, object]:
        claude_commands: list[list[str]] = [
            ["claude", "plugin", "marketplace", "add", str(self.active_path), "--scope", "user"]
        ]
        claude_commands.extend(
            ["claude", "plugin", "install", f"{plugin}@mir-yoke", "--scope", "user"]
            for plugin in selected_plugins
        )
        codex_commands: list[list[str]] = [
            ["codex", "plugin", "marketplace", "add", str(self.active_path), "--json"]
        ]
        codex_commands.extend(
            ["codex", "plugin", "add", f"{plugin}@mir-yoke", "--json"]
            for plugin in selected_plugins
        )
        return {
            "status": "pending",
            "automatic_execution": True,
            "claude_code": claude_commands,
            "codex_cli_desktop": codex_commands,
            "codex_ide_extension": "unsupported; project-local agents and instructions only",
            "after_agent_update": ["bash", "scripts/generate_codex_derivatives.sh"],
            "required_runtimes": list(self.config.required_runtimes),
            "next_step": (
                "start new sessions for every required runtime, attest each discovered skill "
                "catalog, then run capability finalize --apply --after-restart"
            ),
        }

    def _install_and_verify(
        self,
        registration: dict[str, object],
        locked_plugins: dict[str, object],
    ) -> dict[str, object]:
        command_groups = {
            "claude-code": registration["claude_code"],
            "codex-cli-desktop": registration["codex_cli_desktop"],
        }
        attempts: dict[str, object] = {}
        for runtime, raw_commands in command_groups.items():
            if not isinstance(raw_commands, list):
                attempts[runtime] = {"status": "invalid-plan"}
                continue
            executable = "claude" if runtime == "claude-code" else "codex"
            resolved = self.which(executable)
            if resolved is None:
                attempts[runtime] = {"status": "cli-missing"}
                continue
            if executable == "codex":
                if self.codex_home.is_symlink() or (
                    self.codex_home.exists() and not self.codex_home.is_dir()
                ):
                    attempts[runtime] = {"status": "codex-home-unsafe"}
                    continue
                self.codex_home.mkdir(parents=True, exist_ok=True)
            results: list[dict[str, object]] = []
            for raw_command in raw_commands:
                if not isinstance(raw_command, list) or not all(
                    isinstance(item, str) for item in raw_command
                ):
                    results.append({"status": "invalid-command"})
                    continue
                completed = self.command_runner(
                    [resolved, *raw_command[1:]],
                    cwd=self._runtime_cwd(executable),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                results.append(
                    {
                        "argv": raw_command,
                        "exit_code": completed.returncode,
                        "status": "ok" if completed.returncode == 0 else "failed",
                    }
                )
            attempts[runtime] = {"status": "attempted", "commands": results}

        evidence = {
            "claude-code": self._probe_runtime(
                "claude", ["plugin", "list", "--json"], locked_plugins
            ),
            "codex-cli-desktop": self._probe_runtime(
                "codex", ["plugin", "list", "--json"], locked_plugins
            ),
        }
        registration["install_attempts"] = attempts
        registration["evidence"] = evidence
        registration["required_runtimes"] = list(self.config.required_runtimes)
        registration["status"] = (
            "restart-required"
            if all(
                evidence[runtime].get("verified") is True
                for runtime in self.config.required_runtimes
            )
            else "registration-failed"
        )
        return registration


def _plugin_entries(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    if isinstance(payload, dict):
        installed = payload.get("installed")
        if isinstance(installed, list):
            return [entry for entry in installed if isinstance(entry, dict)]
        plugins = payload.get("plugins")
        if isinstance(plugins, list):
            return [entry for entry in plugins if isinstance(entry, dict)]
    return []


def _plugin_name(entry: dict[str, object]) -> str | None:
    value = entry.get("name")
    if isinstance(value, str) and value:
        return value
    for field in ("id", "pluginId"):
        identifier = entry.get(field)
        if isinstance(identifier, str) and identifier:
            return identifier.split("@", 1)[0]
    return None


def _installed_path(entry: dict[str, object]) -> str | None:
    for field in ("installedPath", "installPath", "installed_path", "path"):
        value = entry.get(field)
        if isinstance(value, str) and value:
            return value
    return None
