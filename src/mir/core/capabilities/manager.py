"""Pinned, fail-closed capability synchronization for shared Mir plugins."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .config import CapabilityConfig, CapabilityConfigError, CapabilityPack, load_capability_config

_SHA = re.compile(r"^[0-9a-f]{40}$")
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_SKILL_PLUGIN_ROOT_ENTRIES = {".claude-plugin", ".codex-plugin", "skills"}
_HOOK_PLUGIN_ROOT_ENTRIES = {
    ".claude-plugin",
    ".codex-plugin",
    "hooks",
    "skills",
}
_CLAUDE_SKILL_MANIFEST_KEYS = {
    "$schema",
    "author",
    "description",
    "homepage",
    "keywords",
    "license",
    "name",
    "repository",
    "version",
}
_CODEX_SKILL_MANIFEST_KEYS = {
    "author",
    "description",
    "homepage",
    "interface",
    "keywords",
    "license",
    "name",
    "repository",
    "skills",
    "version",
}
_CLAUDE_HOOK_MANIFEST_KEYS = _CLAUDE_SKILL_MANIFEST_KEYS
_CODEX_HOOK_MANIFEST_KEYS = _CODEX_SKILL_MANIFEST_KEYS
_HOOKS_SCHEMA = {
    "hooks": {
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/runtime_continuity.py"',
                        "timeout": 2,
                    }
                ]
            }
        ]
    }
}
_HOOK_HANDLER_SOURCE = '''"""Render bounded, target-independent lifecycle continuity context."""

MESSAGE = (
    "Mir lifecycle continuity: preserve the active task intent and verify state before continuing."
)


def main() -> None:
    print(MESSAGE)


if __name__ == "__main__":
    main()
'''
_ACTIVE_PACKAGE_CREDENTIAL_PATTERNS = (
    re.compile(rb"https?://[^\s/@]+@", re.IGNORECASE),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bBearer\s+[A-Za-z0-9._~+/-]{20,}\b", re.IGNORECASE),
)
_MARKETPLACE_PATHS = (
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
)
_CLAUDE_MARKETPLACE_KEYS = {"$schema", "name", "description", "owner", "plugins"}
_CLAUDE_MARKETPLACE_PLUGIN_KEYS = {
    "name",
    "source",
    "description",
    "version",
    "author",
    "category",
}
_CODEX_MARKETPLACE_KEYS = {"name", "interface", "plugins"}
_CODEX_MARKETPLACE_PLUGIN_KEYS = {"name", "source", "policy", "category"}
_PLUGIN_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_CONSUMER_BINDING = re.compile(r"^[0-9a-f]{64}$")
_RUNTIMES = ("claude-code", "codex-cli-desktop")
_DERIVATIVE_STATIC_PATHS = (
    "AGENTS.md",
    ".agents/skills",
    ".claude/hooks/lib",
    ".claude/settings.json",
    ".codex/agents",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/hooks/lib",
    ".codex/README.md",
    ".codex-sync/manifest.json",
    ".codex-sync/staging/.agents/skills",
)
_DERIVATIVE_SOURCE_ROOTS = ("scripts", "src", "starter", "tests", "tools")
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


def _reject_active_package_credentials(plugin_root: Path) -> None:
    for path in plugin_root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        payload = path.read_bytes()
        if any(pattern.search(payload) for pattern in _ACTIVE_PACKAGE_CREDENTIAL_PATTERNS):
            raise CapabilityError(
                f"credential-bearing content rejected in active package: {path.name}"
            )


def _directory_identity(path: Path) -> tuple[int, int] | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return None
    return metadata.st_dev, metadata.st_ino


def _validate_plugin(plugin_root: Path, expected_name: str, *, package_kind: str) -> str:
    if package_kind == "skills":
        expected_entries = _SKILL_PLUGIN_ROOT_ENTRIES
        manifest_keys = {
            "claude": _CLAUDE_SKILL_MANIFEST_KEYS,
            "codex": _CODEX_SKILL_MANIFEST_KEYS,
        }
    elif package_kind == "skills-hooks":
        expected_entries = _HOOK_PLUGIN_ROOT_ENTRIES
        manifest_keys = {
            "claude": _CLAUDE_HOOK_MANIFEST_KEYS,
            "codex": _CODEX_HOOK_MANIFEST_KEYS,
        }
    else:
        raise CapabilityError(f"unsupported plugin package_kind: {package_kind}")
    entries = {path.name for path in plugin_root.iterdir()}
    if entries != expected_entries:
        extra = ", ".join(sorted(entries - expected_entries)) or "none"
        raise CapabilityError(f"plugin root content rejected in {expected_name}: {extra}")
    if package_kind == "skills-hooks":
        for runtime in ("claude", "codex"):
            manifest_entries = {
                path.name for path in (plugin_root / f".{runtime}-plugin").iterdir()
            }
            if manifest_entries != {"plugin.json"}:
                raise CapabilityError(
                    f"shared hook manifest content rejected in {expected_name}.{runtime}"
                )
    manifests: list[dict[str, object]] = []
    for runtime in ("claude", "codex"):
        manifest_path = plugin_root / f".{runtime}-plugin" / "plugin.json"
        payload = _read_json(manifest_path)
        if payload is None or payload.get("name") != expected_name:
            raise CapabilityError(f"invalid {runtime} manifest for {expected_name}")
        unexpected = set(payload) - manifest_keys[runtime]
        if unexpected:
            joined = ", ".join(sorted(unexpected))
            raise CapabilityError(
                f"remote plugin manifest keys rejected: {expected_name}.{runtime}: {joined}"
            )
        manifests.append(payload)
    if manifests[0].get("version") != manifests[1].get("version"):
        raise CapabilityError(f"dual-runtime manifest version drift for {expected_name}")
    version = manifests[0].get("version")
    if not isinstance(version, str) or _PLUGIN_VERSION.fullmatch(version) is None:
        raise CapabilityError(f"unsafe plugin version for {expected_name}")
    if manifests[1].get("skills") != "./skills/":
        raise CapabilityError(f"Codex skills path drift for {expected_name}")
    if package_kind == "skills-hooks":
        hook_entries = {path.name for path in (plugin_root / "hooks").iterdir()}
        if hook_entries != {"hooks.json", "runtime_continuity.py"}:
            raise CapabilityError(f"shared hook content rejected in {expected_name}")
        if any("hooks" in manifest for manifest in manifests):
            raise CapabilityError(f"shared hook path drift for {expected_name}")
        hooks = _read_json(plugin_root / "hooks" / "hooks.json")
        if hooks != _HOOKS_SCHEMA:
            raise CapabilityError(f"shared hook schema drift for {expected_name}")
        handler = plugin_root / "hooks" / "runtime_continuity.py"
        if handler.is_symlink() or not handler.is_file():
            raise CapabilityError(f"shared hook handler is missing or linked: {expected_name}")
        if handler.read_text(encoding="utf-8") != _HOOK_HANDLER_SOURCE:
            raise CapabilityError("shared hook handler is not the reviewed read-only handler")
        if len(handler.read_bytes()) > 512:
            raise CapabilityError("shared hook handler exceeds bounded output contract")
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
    if package_kind == "skills-hooks":
        _reject_active_package_credentials(plugin_root)
    return _tree_digest(plugin_root)


def _marketplace_entries(
    payload: dict[str, object], path: str
) -> dict[str, dict[str, object]]:
    raw_entries = payload.get("plugins")
    if not isinstance(raw_entries, list):
        raise CapabilityError(f"marketplace plugins must be an array: {path}")
    entries: dict[str, dict[str, object]] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or not isinstance(raw_entry.get("name"), str):
            raise CapabilityError(f"invalid marketplace plugin entry: {path}")
        name = raw_entry["name"]
        if name in entries:
            raise CapabilityError(f"duplicate marketplace plugin entry: {path}: {name}")
        entries[name] = raw_entry
    return entries


def _validate_marketplaces(root: Path, config: CapabilityConfig) -> dict[str, str]:
    claude_path, codex_path = _MARKETPLACE_PATHS
    claude = _read_json(root / claude_path)
    codex = _read_json(root / codex_path)
    if claude is None or codex is None:
        raise CapabilityError("capability marketplaces are missing")
    if claude.get("name") != "mir-yoke" or codex.get("name") != "mir-yoke":
        raise CapabilityError("capability marketplace name drift")
    if set(claude) - _CLAUDE_MARKETPLACE_KEYS:
        raise CapabilityError("Claude marketplace contains unsupported fields")
    if set(codex) - _CODEX_MARKETPLACE_KEYS:
        raise CapabilityError("Codex marketplace contains unsupported fields")
    claude_entries = _marketplace_entries(claude, claude_path)
    codex_entries = _marketplace_entries(codex, codex_path)
    expected_names = set(config.plugins)
    inventory_matches = (
        set(claude_entries) == expected_names and set(codex_entries) == expected_names
        if config.source_schema_version >= 3
        else expected_names <= set(claude_entries) and expected_names <= set(codex_entries)
    )
    if not inventory_matches:
        raise CapabilityError("capability marketplace inventory drift")
    for name, plugin_path in config.plugins.items():
        expected_path = f"./{plugin_path}"
        claude_entry = claude_entries[name]
        codex_entry = codex_entries[name]
        if set(claude_entry) - _CLAUDE_MARKETPLACE_PLUGIN_KEYS:
            raise CapabilityError(f"Claude marketplace plugin fields drift: {name}")
        if set(codex_entry) - _CODEX_MARKETPLACE_PLUGIN_KEYS:
            raise CapabilityError(f"Codex marketplace plugin fields drift: {name}")
        if claude_entry.get("source") != expected_path:
            raise CapabilityError(f"Claude marketplace source drift: {name}")
        if codex_entry.get("source") != {"source": "local", "path": expected_path}:
            raise CapabilityError(f"Codex marketplace source drift: {name}")
        if codex_entry.get("policy") != {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        }:
            raise CapabilityError(f"Codex marketplace policy drift: {name}")
        manifest = _read_json(root / plugin_path / ".claude-plugin" / "plugin.json")
        if manifest is None or claude_entry.get("version") != manifest.get("version"):
            raise CapabilityError(f"Claude marketplace version drift: {name}")
    return {path: _file_digest(root / path) for path in _MARKETPLACE_PATHS}


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
        self._project_root_identity = _directory_identity(self.project_root)
        if self._project_root_identity is None:
            raise CapabilityError("project root is not a real directory")
        self.config_path = config_path or self.project_root / "config" / "capability-sources.json"
        self.config = load_capability_config(self.config_path)
        self.user_home = (user_home or Path.home()).resolve()
        raw_codex_home = os.environ.get("CODEX_HOME")
        configured_codex_home = codex_home or (
            Path(raw_codex_home) if raw_codex_home else self.user_home / ".codex"
        )
        self.codex_home = configured_codex_home.expanduser().resolve()
        self._codex_home_anchor = self.codex_home
        self._codex_home_identity = _directory_identity(self._codex_home_anchor)
        configured_capability_home = capability_home
        if configured_capability_home is None and "MIR_CAPABILITY_HOME" not in os.environ:
            configured_capability_home = _configured_provider_home(
                self.codex_home, self.config.source_url
            )
        self.capability_home = (
            configured_capability_home or default_capability_home()
        ).expanduser().resolve()
        self._capability_home_anchor = self.capability_home
        self._capability_home_identity = _directory_identity(
            self._capability_home_anchor
        )
        self.git = git or GitClient()
        self.command_runner = command_runner
        self.which = which
        self.lock_path = self.project_root / ".mir" / "capability-lock.json"
        self.registry_path = self.capability_home / "consumers.json"
        self.consumer_bindings_path = self.capability_home / "consumer-bindings.json"
        self.active_path = self.capability_home / "active"
        self.active_receipt_path = self.capability_home / "active.json"
        if self._capability_home_anchor.exists() or self._capability_home_anchor.is_symlink():
            self._assert_capability_home_safe(allow_missing=False, adopt=True)

    def _assert_project_root_identity(self) -> None:
        if _directory_identity(self.project_root) != self._project_root_identity:
            raise CapabilityError("project root identity changed")

    def _codex_home_identity_current(self, *, adopt: bool = False) -> bool:
        identity = _directory_identity(self._codex_home_anchor)
        if identity is None:
            return False
        if self._codex_home_identity is None:
            if adopt:
                self._codex_home_identity = identity
            return adopt
        return identity == self._codex_home_identity

    def _assert_capability_home_safe(
        self,
        *,
        create: bool = False,
        allow_missing: bool = True,
        adopt: bool = False,
    ) -> None:
        """Keep capability state anchored to its initialization-time directory."""
        anchor = self._capability_home_anchor
        current = Path(anchor.anchor)
        for component in anchor.parts[1:]:
            current /= component
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                if not create:
                    if allow_missing:
                        return
                    raise CapabilityError("capability home is missing") from None
                anchor.mkdir(parents=True, exist_ok=True)
                return self._assert_capability_home_safe(
                    allow_missing=False, adopt=True
                )
            except OSError as exc:
                raise CapabilityError("capability home is unsafe") from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise CapabilityError("capability home is unsafe")
        identity = _directory_identity(anchor)
        if identity is None:
            raise CapabilityError("capability home is unsafe")
        if self._capability_home_identity is None:
            if adopt:
                self._capability_home_identity = identity
            else:
                raise CapabilityError("capability home identity is not established")
        elif identity != self._capability_home_identity:
            raise CapabilityError("capability home identity changed")

    @contextmanager
    def _capability_apply_guard(self) -> Iterator[None]:
        self._assert_capability_home_safe(create=True, allow_missing=False, adopt=True)
        guard = self.capability_home / ".apply.lock"
        try:
            guard.mkdir()
        except FileExistsError as exc:
            raise CapabilityError(f"another capability apply is active: {guard}") from exc
        try:
            self._assert_capability_home_safe(allow_missing=False)
            yield
        finally:
            try:
                self._assert_capability_home_safe(allow_missing=False)
            except CapabilityError:
                pass
            else:
                guard.rmdir()

    def _load_lock(self) -> dict[str, object] | None:
        self._assert_project_lock_path_safe()
        return _read_json(self.lock_path)

    def _assert_project_lock_path_safe(self) -> None:
        """Ensure managed lock state cannot be redirected outside the project."""
        self._assert_project_root_identity()
        lock_parent = self.lock_path.parent
        if lock_parent.is_symlink() or (
            lock_parent.exists() and not lock_parent.is_dir()
        ):
            raise CapabilityError("project .mir capability state path is unsafe")
        if self.lock_path.is_symlink():
            raise CapabilityError("project capability lock path is a symlink")
        try:
            lock_parent.resolve().relative_to(self.project_root)
        except ValueError as exc:
            raise CapabilityError("project capability lock path escapes repository") from exc

    def _load_registry(self) -> dict[str, object]:
        self._assert_capability_home_safe(allow_missing=True)
        return _read_json(self.registry_path) or {
            "schema_version": 1,
            "active_commit": None,
            "consumers": {},
        }

    def _load_consumer_bindings(self) -> dict[str, str]:
        self._assert_capability_home_safe(allow_missing=True)
        try:
            metadata = self.consumer_bindings_path.lstat()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise CapabilityError("consumer binding ledger is invalid") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise CapabilityError("consumer binding ledger is invalid")
        payload = _read_json(self.consumer_bindings_path)
        entries = payload.get("consumers")
        if payload.get("schema_version") != 1 or not isinstance(entries, dict):
            raise CapabilityError("consumer binding ledger is invalid")
        bindings: dict[str, str] = {}
        for root, binding in entries.items():
            if (
                not isinstance(root, str)
                or not isinstance(binding, str)
                or _CONSUMER_BINDING.fullmatch(binding) is None
            ):
                raise CapabilityError("consumer binding ledger is invalid")
            bindings[root] = binding
        return bindings

    def _current_binding_for_apply(
        self,
        lock: dict[str, object] | None,
        registry: dict[str, object],
        bindings: dict[str, str],
        current_key: str,
    ) -> str | None:
        if self.config.source_schema_version < 3:
            return None
        consumers = registry.get("consumers")
        entry = consumers.get(current_key) if isinstance(consumers, dict) else None
        ledger_binding = bindings.get(current_key)
        if lock is None and entry is None and ledger_binding is None:
            return secrets.token_hex(32)
        if (
            registry.get("schema_version") in {1, 2}
            and isinstance(entry, dict)
            and ledger_binding is None
            and "binding" not in entry
            and self._is_genuine_legacy_consumer_entry(current_key, entry)
        ):
            return secrets.token_hex(32)
        lock_binding = lock.get("consumer_binding") if isinstance(lock, dict) else None
        if (
            not isinstance(entry, dict)
            or not isinstance(lock_binding, str)
            or not isinstance(ledger_binding, str)
            or _CONSUMER_BINDING.fullmatch(lock_binding) is None
            or lock_binding != ledger_binding
            or entry.get("binding") != lock_binding
        ):
            raise CapabilityError("current consumer enrollment is invalid")
        entry_commit = entry.get("commit")
        root = self._registry_consumer_root(current_key)
        if (
            not isinstance(entry_commit, str)
            or _SHA.fullmatch(entry_commit) is None
            or root is None
            or not self._consumer_lock_matches(root, entry, entry_commit, lock_binding)
        ):
            raise CapabilityError("current consumer enrollment is invalid")
        return lock_binding

    def _is_genuine_legacy_consumer_entry(
        self,
        raw_root: str,
        entry: dict[str, object],
    ) -> bool:
        """Accept an unbound consumer only when its historical schema-1 lock is intact."""
        root = self._registry_consumer_root(raw_root)
        commit = entry.get("commit")
        required = entry.get("plugins")
        if (
            root is None
            or set(entry) != {"commit", "plugins", "profile"}
            or not isinstance(commit, str)
            or _SHA.fullmatch(commit) is None
            or not isinstance(required, dict)
        ):
            return False
        legacy_mir = root / ".mir"
        legacy_lock_path = legacy_mir / "capability-lock.json"
        try:
            mir_mode = legacy_mir.lstat().st_mode
            lock_mode = legacy_lock_path.lstat().st_mode
        except OSError:
            return False
        if (
            stat.S_ISLNK(mir_mode)
            or not stat.S_ISDIR(mir_mode)
            or stat.S_ISLNK(lock_mode)
            or not stat.S_ISREG(lock_mode)
        ):
            return False
        lock = _read_json(legacy_lock_path)
        if lock is None:
            return False
        source = lock.get("source")
        locked_plugins = lock.get("plugins")
        locked_agents = lock.get("agents")
        registration = lock.get("registration")
        profile = lock.get("profile")
        if not isinstance(profile, str):
            return False
        try:
            _, pack = self.config.resolve_profile(profile)
        except CapabilityConfigError:
            return False
        if (
            lock.get("schema_version") != 1
            or set(lock)
            != {
                "schema_version",
                "source",
                "profile",
                "plugins",
                "agents",
                "registration",
                "synced_at",
            }
            or "consumer_binding" in lock
            or not isinstance(source, dict)
            or source != {
                "url": self.config.source_url,
                "ref": self.config.source_ref,
                "commit": commit,
            }
            or not isinstance(locked_plugins, dict)
            or set(locked_plugins) != set(required)
            or entry.get("profile") != lock.get("profile")
            or not isinstance(locked_agents, dict)
            or set(locked_agents) != set(pack.agents)
            or not isinstance(registration, dict)
            or registration.get("status") not in {"restart-required", "active"}
            or not isinstance(lock.get("synced_at"), str)
        ):
            return False
        for path, metadata in locked_agents.items():
            if (
                not isinstance(metadata, dict)
                or metadata.get("project_path") != path
                or not isinstance(metadata.get("sha256"), str)
                or _CONSUMER_BINDING.fullmatch(metadata["sha256"]) is None
            ):
                return False
        return all(
            isinstance(digest, str)
            and _CONSUMER_BINDING.fullmatch(digest) is not None
            and metadata
            == {"path": self.config.plugins.get(plugin), "sha256": digest}
            for plugin, digest in required.items()
            for metadata in (locked_plugins.get(plugin),)
        )

    def _profile(self, requested: str | None, lock: dict[str, object] | None):
        value = requested or (lock.get("profile") if lock else None) or "default"
        if not isinstance(value, str):
            raise CapabilityError("capability lock profile is invalid")
        return self.config.resolve_profile(value)

    def _managed_file_status(
        self,
        lock: dict[str, object] | None,
        selected_paths: Sequence[str],
        *,
        lock_key: str,
    ) -> dict[str, str]:
        locked_files = lock.get(lock_key, {}) if lock else {}
        if not isinstance(locked_files, dict):
            raise CapabilityError(f"capability lock {lock_key} field is invalid")
        result: dict[str, str] = {}
        for source_path in selected_paths:
            metadata = locked_files.get(source_path)
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

    def _agent_status(
        self, lock: dict[str, object] | None, selected_agents: Sequence[str]
    ) -> dict[str, str]:
        return self._managed_file_status(lock, selected_agents, lock_key="agents")

    def _command_status(
        self, lock: dict[str, object] | None, selected_commands: Sequence[str]
    ) -> dict[str, str]:
        result = self._managed_file_status(lock, selected_commands, lock_key="commands")
        locked_commands = lock.get("commands", {}) if lock else {}
        if not isinstance(locked_commands, dict):
            raise CapabilityError("capability lock commands field is invalid")
        for source_path in selected_commands:
            metadata = locked_commands.get(source_path)
            if (
                result[source_path] == "unchanged"
                and isinstance(metadata, dict)
                and metadata.get("codex_skill") != self.config.commands[source_path]
            ):
                result[source_path] = "mapping-mismatch"
        return result

    def status(self, profile: str | None = None) -> dict[str, object]:
        self._assert_capability_home_safe(allow_missing=True)
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
        command_status = self._command_status(lock, pack.commands)
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
            and all(value == "unchanged" for value in command_status.values())
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
            "command_status": command_status,
            "command_skill_map": {
                path: self.config.commands[path] for path in pack.commands
            },
            "managed_surfaces": self._managed_surfaces(pack),
            "runtime_support": self.config.runtime_support,
            "registration": lock.get("registration") if lock else None,
            "activation": activation,
            "discovery": discovery,
        }

    def _configured_skill_names(self, plugins: Sequence[str]) -> set[str]:
        return {skill for plugin in plugins for skill in self.config.plugin_skills[plugin]}

    def _assert_active_digest_acknowledgements(
        self, plugin_hashes: dict[str, str]
    ) -> None:
        for plugin, expected in self.config.active_digest_acknowledgements.items():
            actual = plugin_hashes.get(plugin)
            if actual != expected:
                raise CapabilityError(
                    f"active package digest acknowledgement is stale: {plugin}"
                )

    def _managed_surfaces(self, pack: CapabilityPack) -> dict[str, object]:
        surfaces: dict[str, object] = {
            "skills": {
                "delivery": "host-plugin",
                "plugins": list(pack.plugins),
                "inventory": {
                    plugin: list(self.config.plugin_skills[plugin])
                    for plugin in pack.plugins
                },
            },
            "agents": {
                "delivery": "claude-project-file-codex-generated-agent",
                "sources": list(pack.agents),
            },
            "commands": {
                "delivery": "claude-project-file-codex-plugin-skill",
                "mappings": {
                    path: self.config.commands[path] for path in pack.commands
                },
            },
        }
        plugin_hooks = {
            plugin: list(self.config.plugin_hooks[plugin])
            for plugin in pack.plugins
            if plugin in self.config.plugin_hooks
        }
        project_hooks = self.config.project_integrations.get("hooks")
        if plugin_hooks or project_hooks is not None:
            surfaces["hooks"] = {
                "delivery": "host-plugin-and-target-local-generated",
                "global_plugins": plugin_hooks,
                "repository_coupled": project_hooks,
            }
        surfaces.update(
            {
                name: metadata
                for name, metadata in self.config.project_integrations.items()
                if name != "hooks"
            }
        )
        return surfaces

    def _missing_project_paths(self) -> list[str]:
        missing: list[str] = []
        for path in self.config.required_project_paths:
            try:
                target = self._project_target(path)
            except CapabilityError:
                missing.append(path)
                continue
            if not target.exists() or target.is_symlink():
                missing.append(path)
        return missing

    def _assert_derivative_paths_safe(self) -> None:
        paths = set((*self.config.required_project_paths, *_DERIVATIVE_STATIC_PATHS))
        for source_root in _DERIVATIVE_SOURCE_ROOTS:
            root = self._project_target(source_root)
            if root.is_symlink():
                raise CapabilityError(f"project derivative path is a symlink: {source_root}")
            if not root.is_dir():
                continue
            for source in root.rglob("CLAUDE.md"):
                if source.is_file() and not source.is_symlink():
                    paths.add(str(source.relative_to(self.project_root).with_name("AGENTS.md")))
        for relative in sorted(paths):
            target = self._project_target(relative)
            if target.is_symlink():
                raise CapabilityError(f"project derivative path is a symlink: {relative}")

    def _project_target(self, relative: str) -> Path:
        self._assert_project_root_identity()
        lexical = PurePosixPath(relative)
        if (
            not relative
            or "\\" in relative
            or lexical.is_absolute()
            or "." in lexical.parts
            or ".." in lexical.parts
            or lexical.as_posix() != relative
        ):
            raise CapabilityError(f"project target path is unsafe: {relative!r}")
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
        self._assert_capability_home_safe(allow_missing=True)
        if lock is None:
            return False
        locked_plugins = lock.get("plugins")
        if not isinstance(locked_plugins, dict):
            return False
        lock_schema = lock.get("schema_version")
        if lock_schema not in {1, 2}:
            return False
        if any(plugin not in self.config.plugins for plugin in plugins):
            return False
        active_receipt = _read_json(self.active_receipt_path)
        receipt_schema = active_receipt.get("schema_version") if active_receipt else None
        if receipt_schema not in {None, 1, 2}:
            return False
        if self.config.source_schema_version >= 3 and (
            lock_schema != 2 or receipt_schema != 2
        ):
            return False
        materialized_plugins = (
            active_receipt.get("materialized_plugins") if active_receipt else None
        )
        try:
            marketplace_hashes = _validate_marketplaces(self.active_path, self.config)
            actual_plugin_hashes = {
                plugin: _validate_plugin(
                    self.active_path / self.config.plugins[plugin],
                    plugin,
                    package_kind=self.config.plugin_kinds[plugin],
                )
                for plugin in self.config.plugins
            }
        except (CapabilityError, OSError):
            return False
        for plugin in plugins:
            metadata = locked_plugins.get(plugin)
            if not isinstance(metadata, dict) or not isinstance(metadata.get("sha256"), str):
                return False
            if actual_plugin_hashes[plugin] != metadata["sha256"]:
                return False
        lock_marketplaces = lock.get("marketplaces")
        receipt_marketplaces = active_receipt.get("marketplaces") if active_receipt else None
        if lock_schema == 1 and lock_marketplaces is not None:
            return False
        if receipt_schema == 1 and (
            receipt_marketplaces is not None or materialized_plugins is not None
        ):
            return False
        if lock_schema == 2 and (
            lock_marketplaces is None
            or receipt_schema != 2
            or receipt_marketplaces is None
            or materialized_plugins is None
        ):
            return False
        if receipt_schema == 2 and (
            receipt_marketplaces is None or materialized_plugins != actual_plugin_hashes
        ):
            return False
        if receipt_schema == 2:
            registry = _read_json(self.registry_path)
            if self._schema2_active_union(registry, active_receipt, actual_plugin_hashes) is None:
                return False
        for evidence in (lock_marketplaces, receipt_marketplaces):
            if evidence is None:
                continue
            if not isinstance(evidence, dict):
                return False
            expected = {
                path: {"sha256": digest} for path, digest in marketplace_hashes.items()
            }
            if evidence != expected:
                return False
        return True

    def _schema2_active_union(
        self,
        registry: dict[str, object] | None,
        receipt: dict[str, object] | None,
        actual_plugin_hashes: dict[str, str],
    ) -> dict[str, str] | None:
        if (
            registry is None
            or receipt is None
            or registry.get("schema_version") != 2
            or receipt.get("schema_version") != 2
        ):
            return None
        receipt_commit = receipt.get("commit")
        receipt_plugins = receipt.get("plugins")
        active_commit = registry.get("active_commit")
        active_plugins = registry.get("active_plugins")
        consumers = registry.get("consumers")
        if not (
            isinstance(receipt_commit, str)
            and _SHA.fullmatch(receipt_commit)
            and active_commit == receipt_commit
            and isinstance(receipt_plugins, dict)
            and receipt_plugins
            and isinstance(active_plugins, dict)
            and active_plugins == receipt_plugins
            and isinstance(consumers, dict)
        ):
            return None
        for plugin, digest in receipt_plugins.items():
            if (
                not isinstance(plugin, str)
                or plugin not in actual_plugin_hashes
                or not isinstance(digest, str)
                or actual_plugin_hashes[plugin] != digest
            ):
                return None
        try:
            bindings = self._load_consumer_bindings()
        except CapabilityError:
            return None
        consumer_union = self._consumer_union(
            consumers,
            receipt_commit,
            actual_plugin_hashes,
            bindings=bindings,
        )
        return consumer_union if consumer_union == active_plugins else None

    def _registry_consumer_root(self, raw_root: object) -> Path | None:
        if not isinstance(raw_root, str):
            return None
        root = Path(raw_root)
        if not root.is_absolute() or str(root) != raw_root:
            return None
        current = Path(root.anchor)
        for component in root.parts[1:]:
            current /= component
            try:
                mode = current.lstat().st_mode
            except OSError:
                return None
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                return None
        try:
            canonical = os.path.normcase(str(root.resolve()))
        except OSError:
            return None
        return root if canonical == raw_root else None

    def _consumer_lock_matches(
        self,
        root: Path,
        entry: dict[str, object],
        commit: str,
        binding: str | None,
    ) -> bool:
        lock_path = root / ".mir" / "capability-lock.json"
        try:
            mir_mode = (root / ".mir").lstat().st_mode
            lock_mode = lock_path.lstat().st_mode
        except OSError:
            return False
        if (
            stat.S_ISLNK(mir_mode)
            or not stat.S_ISDIR(mir_mode)
            or stat.S_ISLNK(lock_mode)
            or not stat.S_ISREG(lock_mode)
        ):
            return False
        try:
            lock = _read_json(lock_path)
        except CapabilityError:
            return False
        source = lock.get("source") if lock else None
        locked_plugins = lock.get("plugins") if lock else None
        required = entry.get("plugins")
        if (
            not isinstance(source, dict)
            or source.get("commit") != commit
            or not isinstance(locked_plugins, dict)
            or not isinstance(required, dict)
            or set(locked_plugins) != set(required)
        ):
            return False
        if self.config.source_schema_version >= 3:
            if lock.get("schema_version") != 2 or source != {
                "url": self.config.source_url,
                "ref": self.config.source_ref,
                "commit": commit,
            } or lock.get("consumer_binding") != binding:
                return False
        return all(
            (
                metadata
                == {
                    "path": self.config.plugins[plugin],
                    "package_kind": self.config.plugin_kinds[plugin],
                    "sha256": digest,
                }
                if self.config.source_schema_version >= 3
                else isinstance(metadata, dict) and metadata.get("sha256") == digest
            )
            for plugin, digest in required.items()
            for metadata in (locked_plugins.get(plugin),)
        )

    def _consumer_union(
        self,
        consumers: object,
        commit: str,
        actual_plugin_hashes: dict[str, str],
        *,
        pending_key: str | None = None,
        bindings: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        if not isinstance(consumers, dict) or not consumers:
            return None
        if self.config.source_schema_version >= 3 and (
            bindings is None or not set(bindings).issubset(consumers)
        ):
            return None
        consumer_union: dict[str, str] = {}
        for raw_root, entry in consumers.items():
            root = self._registry_consumer_root(raw_root)
            if root is None or not isinstance(entry, dict) or entry.get("commit") != commit:
                return None
            required = entry.get("plugins")
            if not isinstance(required, dict) or not required:
                return None
            binding = bindings.get(raw_root) if bindings is not None else None
            if self.config.source_schema_version >= 3:
                if binding is None:
                    if "binding" in entry or not self._is_genuine_legacy_consumer_entry(
                        raw_root, entry
                    ):
                        return None
                elif (
                    not isinstance(binding, str)
                    or _CONSUMER_BINDING.fullmatch(binding) is None
                    or entry.get("binding") != binding
                ):
                    return None
            for plugin, digest in required.items():
                if (
                    not isinstance(plugin, str)
                    or plugin not in actual_plugin_hashes
                    or not isinstance(digest, str)
                    or actual_plugin_hashes[plugin] != digest
                ):
                    return None
                consumer_union[plugin] = digest
            if (
                raw_root != pending_key
                and binding is not None
                and not self._consumer_lock_matches(
                    root, entry, commit, binding
                )
            ):
                return None
        return consumer_union

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
        source = lock.get("source")
        if (
            not isinstance(locked_plugins, dict)
            or not isinstance(required, dict)
            or not isinstance(source, dict)
            or consumer.get("commit") != source.get("commit")
            or not required
            or set(plugins) != set(locked_plugins)
            or set(required) != set(locked_plugins)
        ):
            return False
        for plugin in locked_plugins:
            metadata = locked_plugins.get(plugin)
            if (
                not isinstance(plugin, str)
                or plugin not in self.config.plugins
                or not isinstance(metadata, dict)
                or not isinstance(metadata.get("sha256"), str)
                or required.get(plugin) != metadata["sha256"]
            ):
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

    def _expected_runtime_hooks(self, lock: dict[str, object]) -> set[str]:
        plugins = lock.get("plugins")
        if not isinstance(plugins, dict):
            raise CapabilityError("capability lock plugins field is invalid")
        return {
            f"{plugin}:{hook}"
            for plugin in plugins
            if plugin in self.config.plugin_hooks
            for hook in self.config.plugin_hooks[plugin]
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
        observed_hooks: Sequence[str] = (),
        *,
        apply: bool = False,
    ) -> dict[str, object]:
        if runtime not in _RUNTIMES:
            raise CapabilityError(f"unsupported runtime attestation: {runtime}")
        if apply:
            with self._capability_apply_guard():
                return self._attest(runtime, observed_skills, observed_hooks, apply=True)
        return self._attest(runtime, observed_skills, observed_hooks, apply=False)

    def _attest(
        self,
        runtime: str,
        observed_skills: Sequence[str],
        observed_hooks: Sequence[str],
        *,
        apply: bool,
    ) -> dict[str, object]:
        self._assert_capability_home_safe(allow_missing=True)
        if apply:
            self._assert_project_lock_path_safe()
        lock = self._load_lock()
        if lock is None:
            raise CapabilityError("capabilities must be synced before runtime attestation")
        locked_plugins = lock.get("plugins")
        if not isinstance(locked_plugins, dict) or not self._active_integrity(
            lock, tuple(locked_plugins)
        ):
            raise CapabilityError("active capability provider failed current validation")
        active_receipt = _read_json(self.active_receipt_path)
        source = lock.get("source")
        commit = source.get("commit") if isinstance(source, dict) else None
        if (
            active_receipt is None
            or not isinstance(commit, str)
            or active_receipt.get("commit") != commit
        ):
            raise CapabilityError("active provider receipt does not match the project lock")

        expected_skills = self._expected_runtime_skills(lock)
        expected_hooks = self._expected_runtime_hooks(lock)
        observed = {skill.strip() for skill in observed_skills if skill.strip()}
        observed_hook_set = {hook.strip() for hook in observed_hooks if hook.strip()}
        missing = sorted(expected_skills - observed)
        missing_hooks = sorted(expected_hooks - observed_hook_set)
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
            "missing_hooks": missing_hooks,
            "runtime_verified": runtime_verified,
            "new_session": new_session,
            "attestation_kind": "operator-observed-runtime-catalog-and-hooks",
            "ready_to_attest": (
                not missing and not missing_hooks and runtime_verified and new_session
            ),
        }
        if not apply:
            return result
        if missing:
            raise CapabilityError(
                "runtime skill discovery is missing expected skills: " + ", ".join(missing)
            )
        if missing_hooks:
            raise CapabilityError(
                "runtime hook discovery is missing expected hooks: "
                + ", ".join(missing_hooks)
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
            "observed_hooks": sorted(observed_hook_set),
            "attestation_kind": "operator-observed-runtime-catalog-and-hooks",
            "attested_at": timestamp,
        }
        active_receipt["updated_at"] = timestamp
        _atomic_write_json(self.active_receipt_path, active_receipt)
        result.update({"dry_run": False, "status": "attested", "attested_at": timestamp})
        return result

    def _discovery_evidence(self, lock: dict[str, object]) -> dict[str, object]:
        self._assert_capability_home_safe(allow_missing=True)
        active_receipt = _read_json(self.active_receipt_path)
        source = lock.get("source")
        plugins = lock.get("plugins")
        commit = source.get("commit") if isinstance(source, dict) else None
        expected_skills = self._expected_runtime_skills(lock)
        expected_hooks = self._expected_runtime_hooks(lock)
        assert isinstance(plugins, dict)  # validated by _expected_runtime_skills
        expected_plugins = {
            name: metadata.get("sha256")
            for name, metadata in plugins.items()
            if isinstance(metadata, dict)
        }
        installation_sessions = (
            active_receipt.get("installation_sessions")
            if isinstance(active_receipt, dict)
            else None
        )
        consumer_sessions = (
            installation_sessions.get(_consumer_key(self.project_root))
            if isinstance(installation_sessions, dict)
            else None
        )
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
            observed_hooks = receipt.get("observed_hooks")
            observed_hook_set = (
                {item for item in observed_hooks if isinstance(item, str)}
                if isinstance(observed_hooks, list)
                else set()
            )
            missing_hooks = sorted(expected_hooks - observed_hook_set)
            session_id = receipt.get("session_id")
            installation_session = (
                consumer_sessions.get(runtime)
                if isinstance(consumer_sessions, dict)
                else None
            )
            if receipt.get("commit") != commit or receipt.get("plugins") != expected_plugins:
                status = "provider-mismatch"
            elif not isinstance(session_id, str) or _SESSION_ID.fullmatch(session_id) is None:
                status = "session-invalid"
            elif isinstance(installation_session, str) and session_id == installation_session:
                status = "session-stale"
            elif missing:
                status = "skills-missing"
            elif missing_hooks:
                status = "hooks-missing"
            elif (
                expected_hooks
                and receipt.get("attestation_kind")
                != "operator-observed-runtime-catalog-and-hooks"
            ):
                status = "hook-attestation-invalid"
            else:
                status = "verified"
            evidence[runtime] = {
                "status": status,
                "missing_skills": missing,
                "missing_hooks": missing_hooks,
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
        if apply:
            with self._capability_apply_guard():
                return self._finalize(apply=True, after_restart=after_restart)
        return self._finalize(apply=False, after_restart=after_restart)

    def _finalize(self, *, apply: bool, after_restart: bool) -> dict[str, object]:
        self._assert_capability_home_safe(allow_missing=True)
        if apply:
            self._assert_project_lock_path_safe()
        lock = self._load_lock()
        if lock is None:
            raise CapabilityError("capabilities must be synced before activation can be finalized")
        locked_plugins = lock.get("plugins")
        if not isinstance(locked_plugins, dict) or not self._active_integrity(
            lock, tuple(locked_plugins)
        ):
            raise CapabilityError("active capability provider failed current validation")
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
        runtime_plugins = plugins
        active_receipt = _read_json(self.active_receipt_path)
        if isinstance(active_receipt, dict) and isinstance(
            active_receipt.get("plugins"), dict
        ):
            runtime_plugins = {
                name: {"sha256": digest}
                for name, digest in active_receipt["plugins"].items()
                if isinstance(name, str) and isinstance(digest, str)
            }
        runtime_results = {
            "claude-code": self._probe_runtime(
                "claude", ["plugin", "list", "--json"], runtime_plugins
            ),
            "codex-cli-desktop": self._probe_runtime(
                "codex", ["plugin", "list", "--json"], runtime_plugins
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

    def _codex_enabled_plugins(
        self, config: dict[str, object] | None
    ) -> set[str] | None:
        if config is None:
            return None
        plugins = config.get("plugins")
        if not isinstance(plugins, dict):
            return set()
        return {
            name.removesuffix("@mir-yoke")
            for name, metadata in plugins.items()
            if isinstance(name, str)
            and name.endswith("@mir-yoke")
            and isinstance(metadata, dict)
            and metadata.get("enabled") is True
        }

    def _codex_path_safe(self, candidate: Path) -> bool:
        if self._codex_home_identity is not None and not self._codex_home_identity_current():
            return False
        if self._codex_home_identity is None and (
            self._codex_home_anchor.exists() or self._codex_home_anchor.is_symlink()
        ):
            return False
        try:
            relative = candidate.relative_to(self._codex_home_anchor)
        except ValueError:
            return False
        current = Path(self._codex_home_anchor.anchor)
        for component in (*self._codex_home_anchor.parts[1:], *relative.parts):
            current /= component
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                break
            except OSError:
                return False
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                return False
        try:
            candidate.resolve().relative_to(self._codex_home_anchor)
        except (OSError, ValueError):
            return False
        return True

    def _codex_cache_path(
        self, entry: dict[str, object], plugin: str
    ) -> tuple[Path | None, str | None]:
        version = entry.get("version")
        if not isinstance(version, str) or _PLUGIN_VERSION.fullmatch(version) is None:
            return None, "codex-plugin-version-invalid"
        cache_path = self._codex_home_anchor / "plugins" / "cache" / "mir-yoke" / plugin / version
        if not self._codex_path_safe(cache_path):
            return None, "codex-plugin-cache-path-unsafe"
        return cache_path, None

    def _probe_runtime(
        self,
        executable: str,
        args: Sequence[str],
        locked_plugins: dict[str, object],
    ) -> dict[str, object]:
        try:
            self._assert_capability_home_safe(allow_missing=True)
        except CapabilityError:
            return {"verified": False, "reason": "capability-home-unsafe"}
        resolved = self.which(executable)
        if resolved is None:
            return {"verified": False, "reason": "cli-missing"}
        if executable == "codex" and (
            self._codex_home_identity is None
            or not self._codex_path_safe(self._codex_home_anchor / "plugins" / "cache")
        ):
            return {"verified": False, "reason": "codex-home-unsafe"}
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
        expected_names = set(locked_plugins)
        if executable == "codex":
            configured = self._codex_enabled_plugins(codex_config)
            if configured != expected_names:
                evidence["persistent-config"] = {
                    "status": "enabled-set-mismatch",
                    "expected": sorted(expected_names),
                    "configured": sorted(configured) if configured is not None else None,
                }
                verified = False
        unexpected = sorted(
            {
                name
                for entry in entries
                if (name := _plugin_name(entry)) in self.config.plugins
                and name not in expected_names
                and (entry.get("enabled") is True or entry.get("status") == "enabled")
            }
        )
        for name in unexpected:
            evidence[name] = {"status": "unexpected-enabled"}
            verified = False
        for name, metadata in locked_plugins.items():
            expected = metadata.get("sha256") if isinstance(metadata, dict) else None
            matches = [entry for entry in entries if _plugin_name(entry) == name]
            if len(matches) != 1:
                evidence[name] = {"status": "missing-or-duplicate"}
                verified = False
                continue
            entry = matches[0]
            enabled = entry.get("enabled") is True or entry.get("status") == "enabled"
            claude_scope_mismatch = (
                executable == "claude" and entry.get("scope") != "user"
            )
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
            elif claude_scope_mismatch:
                evidence[name] = {
                    "status": "scope-mismatch",
                    "actual_scope": entry.get("scope"),
                    "expected_scope": "user",
                }
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
        selected_commands = pack.commands
        remote_commit = self.git.resolve(self.config.source_url, self.config.source_ref)
        locked_commit = None
        if lock and isinstance(lock.get("source"), dict):
            locked_commit = lock["source"].get("commit")
        if (
            operation == "sync"
            and self.config.source_schema_version == 4
            and isinstance(locked_commit, str)
            and _SHA.fullmatch(locked_commit)
            and locked_commit != remote_commit
        ):
            locked_plugins = lock.get("plugins") if lock else None
            if not isinstance(locked_plugins, dict):
                raise CapabilityError("capability lock plugins field is invalid")
            missing_selected = sorted(set(selected_plugins) - set(locked_plugins))
            if missing_selected:
                raise CapabilityError(
                    "capability source update required before sync: the current lock lacks "
                    "newly selected plugins ("
                    + ", ".join(missing_selected)
                    + "); run 'mir capability update --apply'"
                )
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
            *self.config.commands,
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
                name: _validate_plugin(
                    checkout / path,
                    name,
                    package_kind=self.config.plugin_kinds[name],
                )
                for name, path in self.config.plugins.items()
            }
            self._assert_active_digest_acknowledgements(plugin_hashes)
            marketplace_hashes = _validate_marketplaces(checkout, self.config)
            for name, expected_skills in self.config.plugin_skills.items():
                actual_skills = {
                    path.parent.name
                    for path in (checkout / self.config.plugins[name] / "skills").glob("*/SKILL.md")
                }
                if actual_skills != set(expected_skills):
                    raise CapabilityError(f"remote plugin skill inventory drift: {name}")
            agent_hashes = {path: _file_digest(checkout / path) for path in self.config.agents}
            command_hashes = {
                path: _file_digest(checkout / path) for path in self.config.commands
            }
            skill_names = _skill_names(checkout, self.config, selected_plugins)
            collisions = _standalone_collisions(skill_names, self.project_root, self.user_home)
            agent_changes = self._agent_changes(lock, agent_hashes, selected_agents)
            command_changes = self._command_changes(
                lock, command_hashes, selected_commands
            )
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
                "command_changes": command_changes,
                "command_skill_map": {
                    path: self.config.commands[path] for path in selected_commands
                },
                "managed_surfaces": self._managed_surfaces(pack),
                "runtime_support": self.config.runtime_support,
            }
            if operation == "check" or not apply:
                result["ready_to_apply"] = (
                    not collisions
                    and not missing_project_paths
                    and not any(value == "diverged" for value in agent_changes.values())
                    and not any(value == "diverged" for value in command_changes.values())
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
            divergent_commands = [
                path for path, state in command_changes.items() if state == "diverged"
            ]
            if divergent_commands:
                joined = ", ".join(divergent_commands)
                raise CapabilityError(
                    "project-local command diverged from the trusted source or prior lock; "
                    f"refusing overwrite: {joined}"
                )
            registration = self._apply(
                checkout=checkout,
                commit=desired_commit,
                profile=resolved_profile,
                selected_plugins=selected_plugins,
                selected_agents=selected_agents,
                selected_commands=selected_commands,
                plugin_hashes=plugin_hashes,
                marketplace_hashes=marketplace_hashes,
                agent_hashes=agent_hashes,
                command_hashes=command_hashes,
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
                if path in self.config.provider_local_agents:
                    if not target.exists() and not target.is_symlink():
                        changes[path] = "absent"
                    elif (
                        target.is_file()
                        and not target.is_symlink()
                        and _file_digest(target) == digest
                    ):
                        changes[path] = "provider-local"
                    else:
                        changes[path] = "provider-local-diverged"
                    continue
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
            elif target.exists() or target.is_symlink():
                changes[path] = "diverged"
            else:
                changes[path] = "add"
        return changes

    def _command_changes(
        self,
        lock: dict[str, object] | None,
        desired: dict[str, str],
        selected_commands: Sequence[str],
    ) -> dict[str, str]:
        previous = lock.get("commands", {}) if lock else {}
        if not isinstance(previous, dict):
            raise CapabilityError("capability lock commands field is invalid")
        selected = set(selected_commands)
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
                    and _file_digest(target) in {digest, old_digest}
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
                changes[path] = (
                    "unchanged" if _file_digest(target) == digest else "diverged"
                )
            elif target.exists() or target.is_symlink():
                changes[path] = "diverged"
            else:
                changes[path] = "add"
        return changes

    def _assert_global_version(
        self,
        commit: str,
        selected_plugins: Sequence[str],
        plugin_hashes: dict[str, str],
        bindings: dict[str, str],
        pending_binding: str | None,
    ) -> dict[str, object]:
        registry = self._load_registry()
        consumers = registry.get("consumers")
        if registry.get("schema_version") not in {1, 2} or not isinstance(consumers, dict):
            raise CapabilityError("global consumer registry is invalid")
        current_key = _consumer_key(self.project_root)
        for root, metadata in consumers.items():
            if (
                root != current_key
                and isinstance(metadata, dict)
                and metadata.get("commit") != commit
            ):
                raise CapabilityError(
                    f"global capability update conflicts with another registered consumer: {root}"
                )
        pending_consumers = dict(consumers)
        pending_consumers[current_key] = {
            "commit": commit,
            "plugins": {plugin: plugin_hashes[plugin] for plugin in selected_plugins},
            **({"binding": pending_binding} if pending_binding is not None else {}),
        }
        pending_bindings = dict(bindings)
        if pending_binding is not None:
            pending_bindings[current_key] = pending_binding
        if (
            self._consumer_union(
                pending_consumers,
                commit,
                plugin_hashes,
                pending_key=current_key,
                bindings=pending_bindings,
            )
            is None
        ):
            raise CapabilityError("global consumer registry is invalid")
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

    def _assert_commands_unchanged(self, lock: dict[str, object] | None) -> None:
        if lock is None or "commands" not in lock:
            return
        previous = lock.get("commands")
        if not isinstance(previous, dict):
            raise CapabilityError("capability lock commands field is invalid")
        for source_path, metadata in previous.items():
            if not isinstance(source_path, str) or not isinstance(metadata, dict):
                raise CapabilityError("capability lock command entry is invalid")
            digest = metadata.get("sha256")
            codex_skill = metadata.get("codex_skill")
            target = self._project_target(source_path)
            if (
                not isinstance(digest, str)
                or codex_skill != self.config.commands.get(source_path)
                or not target.is_file()
                or target.is_symlink()
                or _file_digest(target) != digest
            ):
                raise CapabilityError(
                    "project-local command or Codex skill mapping diverged from its lock; "
                    "refusing overwrite: "
                    f"{source_path}"
                )

    def _apply(
        self,
        *,
        checkout: Path,
        commit: str,
        profile: str,
        selected_plugins: Sequence[str],
        selected_agents: Sequence[str],
        selected_commands: Sequence[str],
        plugin_hashes: dict[str, str],
        marketplace_hashes: dict[str, str],
        agent_hashes: dict[str, str],
        command_hashes: dict[str, str],
    ) -> dict[str, object]:
        with self._capability_apply_guard():
            self._assert_project_lock_path_safe()
            previous_lock = self._load_lock()
            self._assert_agents_unchanged(previous_lock)
            self._assert_commands_unchanged(previous_lock)
            bindings = self._load_consumer_bindings()
            consumer_key = _consumer_key(self.project_root)
            pending_binding = self._current_binding_for_apply(
                previous_lock,
                self._load_registry(),
                bindings,
                consumer_key,
            )
            registry = self._assert_global_version(
                commit,
                selected_plugins,
                plugin_hashes,
                bindings,
                pending_binding,
            )
            managed_file_snapshots = {
                self._project_target(path): (
                    self._project_target(path).read_bytes()
                    if self._project_target(path).is_file()
                    else None
                )
                for path in (*self.config.agents, *self.config.commands)
            }
            state_paths = (
                self.lock_path,
                self.registry_path,
                self.consumer_bindings_path,
                self.active_receipt_path,
            )
            state_snapshots = {
                path: path.read_bytes() if path.is_file() else None for path in state_paths
            }
            previous_active_receipt = _read_json(self.active_receipt_path)
            self._assert_capability_home_safe(allow_missing=False)
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
                candidate_active_plugins = tuple(selected_plugins)
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
                    for source_path in (
                        set(self.config.agents)
                        - set(selected_agents)
                        - set(self.config.provider_local_agents)
                    ):
                        self._project_target(source_path).unlink(missing_ok=True)
                    for source_path in selected_commands:
                        _atomic_write_bytes(
                            self._project_target(source_path),
                            (checkout / source_path).read_bytes(),
                        )
                    for source_path in set(self.config.commands) - set(selected_commands):
                        self._project_target(source_path).unlink(missing_ok=True)

                    selected_hashes = {plugin: plugin_hashes[plugin] for plugin in selected_plugins}
                    consumers = registry.setdefault("consumers", {})
                    if not isinstance(consumers, dict):
                        raise CapabilityError("global consumer registry is invalid")
                    consumers[consumer_key] = {
                        "commit": commit,
                        "plugins": selected_hashes,
                        "profile": profile,
                        **({"binding": pending_binding} if pending_binding is not None else {}),
                    }
                    pending_bindings = dict(bindings)
                    if pending_binding is not None:
                        pending_bindings[consumer_key] = pending_binding
                    active_hashes = self._consumer_union(
                        consumers,
                        commit,
                        plugin_hashes,
                        pending_key=consumer_key,
                        bindings=pending_bindings,
                    )
                    if active_hashes is None:
                        raise CapabilityError("global consumer registry entry is invalid")
                    candidate_active_plugins = tuple(sorted(active_hashes))
                    registry["schema_version"] = 2
                    registry["active_commit"] = commit
                    registry["active_plugins"] = active_hashes

                    registration_attempted = True
                    registration = self._install_and_verify(
                        self._registration_plan(
                            candidate_active_plugins,
                            remove_plugins=tuple(
                                sorted(set(self.config.plugins) - set(active_hashes))
                            ),
                        ),
                        {
                            plugin: {"sha256": digest}
                            for plugin, digest in active_hashes.items()
                        },
                    )
                    if registration["status"] != "restart-required":
                        raise CapabilityError("runtime plugin registration failed")
                    derivatives_attempted = True
                    self._regenerate_agent_derivatives()
                    timestamp = datetime.now(UTC).isoformat()
                    lock: dict[str, object] = {
                        "schema_version": 2,
                        "source": {
                            "url": self.config.source_url,
                            "ref": self.config.source_ref,
                            "commit": commit,
                        },
                        "profile": profile,
                        "plugins": {
                            plugin: {
                                "path": self.config.plugins[plugin],
                                "package_kind": self.config.plugin_kinds[plugin],
                                "sha256": plugin_hashes[plugin],
                            }
                            for plugin in selected_plugins
                        },
                        "marketplaces": {
                            path: {"sha256": digest}
                            for path, digest in marketplace_hashes.items()
                        },
                        "agents": {
                            path: {"sha256": agent_hashes[path], "project_path": path}
                            for path in selected_agents
                        },
                        "commands": {
                            path: {
                                "sha256": command_hashes[path],
                                "project_path": path,
                                "codex_skill": self.config.commands[path],
                            }
                            for path in selected_commands
                        },
                        "registration": {"status": registration["status"]},
                        **(
                            {"consumer_binding": pending_binding}
                            if pending_binding is not None
                            else {}
                        ),
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
                        "schema_version": 2,
                        "commit": commit,
                        "source_url": self.config.source_url,
                        "plugins": active_hashes,
                        "materialized_plugins": plugin_hashes,
                        "marketplaces": {
                            path: {"sha256": digest}
                            for path, digest in marketplace_hashes.items()
                        },
                        "materialized_root": str(self.active_path),
                        "discovery": preserved_discovery,
                        "installation_sessions": preserved_installation_sessions,
                        "updated_at": timestamp,
                    }
                    self._assert_capability_home_safe(allow_missing=False)
                    _atomic_write_json(self.active_receipt_path, active_receipt)
                    _atomic_write_json(self.registry_path, registry)
                    _atomic_write_json(
                        self.consumer_bindings_path,
                        {"schema_version": 1, "consumers": pending_bindings},
                    )
                    self._assert_project_root_identity()
                    _atomic_write_json(self.lock_path, lock)
                except BaseException as exc:
                    try:
                        self._assert_capability_home_safe(allow_missing=False)
                    except CapabilityError:
                        capability_rollback_safe = False
                    else:
                        capability_rollback_safe = True
                    if capability_rollback_safe:
                        if new_active_published and self.active_path.exists():
                            shutil.rmtree(self.active_path)
                        if old_active_moved and backup.exists():
                            os.replace(backup, self.active_path)
                    try:
                        self._assert_project_root_identity()
                    except CapabilityError:
                        project_rollback_safe = False
                    else:
                        project_rollback_safe = True
                    if project_rollback_safe:
                        for path, body in managed_file_snapshots.items():
                            if body is None:
                                path.unlink(missing_ok=True)
                            else:
                                _atomic_write_bytes(path, body)
                    derivatives_rollback = True
                    if derivatives_attempted and project_rollback_safe:
                        derivatives_rollback = self._regenerate_agent_derivatives(
                            raise_on_error=False
                        )
                    elif not project_rollback_safe:
                        derivatives_rollback = False
                    if capability_rollback_safe:
                        for path, body in state_snapshots.items():
                            if path == self.lock_path and not project_rollback_safe:
                                continue
                            if body is None:
                                path.unlink(missing_ok=True)
                            else:
                                _atomic_write_bytes(path, body)
                    runtime_rollback = True
                    if registration_attempted and capability_rollback_safe:
                        runtime_rollback = self._rollback_runtime_registration(
                            candidate_active_plugins, previous_active_receipt
                        )
                    rollback_complete = (
                        capability_rollback_safe
                        and runtime_rollback
                        and derivatives_rollback
                    )
                    detail = "complete" if rollback_complete else "incomplete"
                    if not isinstance(exc, Exception) and rollback_complete:
                        raise
                    raise CapabilityError(
                        f"capability apply failed and local rollback was {detail}: {exc}"
                    ) from exc
                else:
                    self._assert_capability_home_safe(allow_missing=False)
                    if backup.exists():
                        shutil.rmtree(backup)
                    return registration

    def _regenerate_agent_derivatives(self, *, raise_on_error: bool = True) -> bool:
        try:
            self._assert_project_root_identity()
            self._assert_derivative_paths_safe()
        except CapabilityError:
            if raise_on_error:
                raise
            return False
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
        try:
            self._assert_capability_home_safe(allow_missing=False)
        except CapabilityError:
            return False
        previous_plugins = (
            previous_active_receipt.get("plugins") if previous_active_receipt else None
        )
        if self.active_path.exists() and (
            not isinstance(previous_active_receipt, dict)
            or not isinstance(previous_plugins, dict)
            or not previous_plugins
        ):
            return False
        if isinstance(previous_plugins, dict) and previous_plugins:
            receipt_schema = previous_active_receipt.get("schema_version")
            if receipt_schema not in {1, 2}:
                return False
            restored_lock = self._load_lock()
            lock_schema = restored_lock.get("schema_version") if restored_lock else None
            registry = self._load_registry()
            registry_schema = registry.get("schema_version")
            if lock_schema not in {None, 1, 2} or registry_schema not in {1, 2}:
                return False
            if (lock_schema == 2 or registry_schema == 2) and receipt_schema != 2:
                return False
            try:
                marketplace_hashes = _validate_marketplaces(self.active_path, self.config)
                actual_materialized = {
                    name: _validate_plugin(
                        self.active_path / path,
                        name,
                        package_kind=self.config.plugin_kinds[name],
                    )
                    for name, path in self.config.plugins.items()
                }
            except (CapabilityError, OSError):
                return False
            if receipt_schema == 2:
                materialized = previous_active_receipt.get("materialized_plugins")
                expected_marketplaces = {
                    path: {"sha256": digest}
                    for path, digest in marketplace_hashes.items()
                }
                if (
                    registry.get("schema_version") != 2
                    or registry.get("active_plugins") != previous_plugins
                    or previous_active_receipt.get("marketplaces")
                    != expected_marketplaces
                    or materialized != actual_materialized
                ):
                    return False
                if (
                    self._schema2_active_union(
                        registry,
                        previous_active_receipt,
                        actual_materialized,
                    )
                    is None
                ):
                    return False
            expected = {
                name: {"sha256": digest}
                for name, digest in previous_plugins.items()
                if (
                    isinstance(name, str)
                    and name in self.config.plugins
                    and isinstance(digest, str)
                    and (
                        receipt_schema != 2
                        or materialized.get(name) == digest
                    )
                )
            }
            if len(expected) != len(previous_plugins):
                return False
            if expected:
                if any(
                    actual_materialized[name] != metadata["sha256"]
                    for name, metadata in expected.items()
                ):
                    return False
                restored = self._install_and_verify(
                    self._registration_plan(
                        tuple(sorted(expected)),
                        remove_plugins=tuple(
                            sorted(set(self.config.plugins) - set(expected))
                        ),
                    ),
                    expected,
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
            try:
                self._assert_capability_home_safe(allow_missing=False)
            except CapabilityError:
                return False
            resolved = self.which(executable)
            if resolved is None:
                continue
            for args in command_group:
                try:
                    self._assert_capability_home_safe(allow_missing=False)
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

    def _registration_plan(
        self,
        selected_plugins: Sequence[str],
        *,
        remove_plugins: Sequence[str] = (),
    ) -> dict[str, object]:
        claude_commands: list[list[str]] = [
            ["claude", "plugin", "marketplace", "add", str(self.active_path), "--scope", "user"]
        ]
        claude_commands.extend(
            ["claude", "plugin", "uninstall", f"{plugin}@mir-yoke", "--scope", "user"]
            for plugin in remove_plugins
        )
        claude_commands.extend(
            ["claude", "plugin", "install", f"{plugin}@mir-yoke", "--scope", "user"]
            for plugin in selected_plugins
        )
        codex_commands: list[list[str]] = [
            ["codex", "plugin", "marketplace", "add", str(self.active_path), "--json"]
        ]
        codex_commands.extend(
            ["codex", "plugin", "remove", f"{plugin}@mir-yoke", "--json"]
            for plugin in remove_plugins
        )
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
                "start new sessions for every required runtime, review and trust the exact "
                "installed hook digest, attest each discovered skill catalog and observed "
                "hook, then run capability finalize --apply --after-restart"
            ),
        }

    def _install_and_verify(
        self,
        registration: dict[str, object],
        locked_plugins: dict[str, object],
    ) -> dict[str, object]:
        try:
            self._assert_capability_home_safe(allow_missing=False)
        except CapabilityError:
            return {
                "claude-code": {"status": "capability-home-unsafe"},
                "codex-cli-desktop": {"status": "capability-home-unsafe"},
                "status": "failed",
            }
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
                if self._codex_home_identity is None and self._codex_home_anchor.exists():
                    if not self._codex_home_identity_current(adopt=True):
                        attempts[runtime] = {"status": "codex-home-unsafe"}
                        continue
                if not self._codex_path_safe(self._codex_home_anchor / "plugins" / "cache"):
                    attempts[runtime] = {"status": "codex-home-unsafe"}
                    continue
                self.codex_home.mkdir(parents=True, exist_ok=True)
                if not self._codex_home_identity_current(adopt=True):
                    attempts[runtime] = {"status": "codex-home-unsafe"}
                    continue
            results: list[dict[str, object]] = []
            for raw_command in raw_commands:
                if not isinstance(raw_command, list) or not all(
                    isinstance(item, str) for item in raw_command
                ):
                    results.append({"status": "invalid-command"})
                    continue
                if executable == "codex" and not self._codex_path_safe(
                    self._codex_home_anchor / "plugins" / "cache"
                ):
                    results.append({"status": "codex-home-unsafe"})
                    continue
                try:
                    self._assert_capability_home_safe(allow_missing=False)
                except CapabilityError:
                    results.append({"status": "capability-home-unsafe"})
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
