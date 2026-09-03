#!/usr/bin/env python3
"""Install Mir plugins in isolated homes and verify both CLI inventory schemas."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _plugin_inventory() -> dict[str, tuple[str, ...]]:
    payload = json.loads(
        (ROOT / "config" / "capability-sources.json").read_text(encoding="utf-8")
    )
    plugins = payload.get("plugins")
    if not isinstance(plugins, dict) or not plugins:
        raise RuntimeError("capability source has no plugin inventory")
    inventory: dict[str, tuple[str, ...]] = {}
    for name, metadata in plugins.items():
        if not isinstance(name, str) or not isinstance(metadata, dict):
            raise RuntimeError("capability source plugin inventory is invalid")
        skills = metadata.get("skills")
        if not isinstance(skills, list) or not all(
            isinstance(skill, str) for skill in skills
        ):
            raise RuntimeError(f"capability source skill inventory is invalid: {name}")
        inventory[name] = tuple(skills)
    return inventory


PLUGIN_SKILLS = _plugin_inventory()
PLUGIN_NAMES = tuple(sorted(PLUGIN_SKILLS))


def _run(argv: list[str], environment: dict[str, str], cwd: Path) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(f"plugin command failed ({argv[0]}): {detail}")
    return completed.stdout


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _entries(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("installed"), list):
        return [item for item in payload["installed"] if isinstance(item, dict)]
    raise RuntimeError("plugin list returned an unsupported JSON shape")


def _name(entry: dict[str, object]) -> str | None:
    for key in ("name", "id", "pluginId"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value.split("@", 1)[0]
    return None


def _path(entry: dict[str, object]) -> Path | None:
    for key in ("installPath", "installedPath", "installed_path", "path"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return Path(value)
    source = entry.get("source")
    if isinstance(source, dict) and isinstance(source.get("path"), str):
        return Path(source["path"])
    return None


def _validate_installed_path(installed: Path, allowed_root: Path) -> Path:
    if not installed.is_absolute():
        raise RuntimeError("plugin inventory returned a non-absolute installed path")
    if installed.is_symlink():
        raise RuntimeError("plugin inventory returned a symlinked installed path")
    try:
        resolved = installed.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("plugin inventory returned an unusable installed path") from exc
    allowed = allowed_root.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(allowed):
        raise RuntimeError("installed plugin is outside the isolated runtime home")
    if resolved.is_relative_to(ROOT.resolve()):
        raise RuntimeError("installed plugin resolves into the provider checkout")
    if any(path.is_symlink() for path in resolved.rglob("*")):
        raise RuntimeError("installed plugin contains a symlink or provider back-reference")
    return resolved


def main() -> int:
    claude = shutil.which("claude")
    codex = shutil.which("codex")
    git = shutil.which("git")
    if claude is None or codex is None or git is None:
        raise SystemExit("Claude Code, Codex CLI, and Git are required for activation verification")

    with tempfile.TemporaryDirectory(prefix="mir-plugin-activation-") as raw_temp:
        temp = Path(raw_temp)
        environment = os.environ.copy()
        environment["HOME"] = str(temp / "home")
        environment["CODEX_HOME"] = str(temp / "codex")
        (temp / "home").mkdir()
        (temp / "codex").mkdir()
        consumer_roots = (temp / "consumer-a", temp / "consumer-b")
        for consumer_root in consumer_roots:
            consumer_root.mkdir()
        install_cwd = consumer_roots[0]
        environment["PWD"] = str(install_cwd)
        provider = temp / "provider-copy"
        shutil.copytree(ROOT / ".claude-plugin", provider / ".claude-plugin")
        (provider / ".agents" / "plugins").mkdir(parents=True)
        shutil.copy2(
            ROOT / ".agents" / "plugins" / "marketplace.json",
            provider / ".agents" / "plugins" / "marketplace.json",
        )
        shutil.copytree(ROOT / "plugins", provider / "plugins")
        expected = {
            plugin: _tree_digest(provider / "plugins" / plugin)
            for plugin in PLUGIN_NAMES
        }
        environment.update(
            {
                "GIT_AUTHOR_NAME": "Mir Plugin Verification",
                "GIT_AUTHOR_EMAIL": "plugin-verification@invalid",
                "GIT_COMMITTER_NAME": "Mir Plugin Verification",
                "GIT_COMMITTER_EMAIL": "plugin-verification@invalid",
            }
        )
        _run([git, "init", "-q", "-b", "main"], environment, provider)
        _run([git, "add", "-A"], environment, provider)
        _run([git, "commit", "-q", "-m", "plugin verification fixture"], environment, provider)
        ssh_wrapper = temp / "git-ssh-wrapper.py"
        ssh_wrapper.write_text(
            """#!/usr/bin/env python3
import os
import sys

if any("git-upload-pack" in argument for argument in sys.argv[1:]):
    os.execvp(
        "git-upload-pack",
        ["git-upload-pack", os.environ["MIR_PLUGIN_PROVIDER_GIT_DIR"]],
    )
raise SystemExit(0)
""",
            encoding="utf-8",
        )
        ssh_wrapper.chmod(0o755)
        environment["GIT_SSH_COMMAND"] = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(ssh_wrapper))}"
        )
        environment["MIR_PLUGIN_PROVIDER_GIT_DIR"] = str(provider)
        marketplace_source = "ssh://mir-plugin-verification/marketplace"

        _run(
            [claude, "plugin", "marketplace", "add", str(provider), "--scope", "user"],
            environment,
            install_cwd,
        )
        _run(
            [codex, "plugin", "marketplace", "add", marketplace_source, "--json"],
            environment,
            install_cwd,
        )
        for plugin in PLUGIN_NAMES:
            _run(
                [claude, "plugin", "install", f"{plugin}@mir-yoke", "--scope", "user"],
                environment,
                install_cwd,
            )
            _run(
                [codex, "plugin", "add", f"{plugin}@mir-yoke", "--json"],
                environment,
                install_cwd,
            )

        provider.rename(temp / "provider-unavailable")
        runtime_homes = {"claude": temp / "home", "codex": temp / "codex"}
        verified: dict[str, dict[str, dict[str, str]]] = {}
        for consumer_root in consumer_roots:
            consumer_result: dict[str, dict[str, str]] = {}
            for runtime, executable in (("claude", claude), ("codex", codex)):
                entries = _entries(
                    json.loads(
                        _run(
                            [executable, "plugin", "list", "--json"],
                            environment,
                            consumer_root,
                        )
                    )
                )
                runtime_result: dict[str, str] = {}
                for plugin in PLUGIN_NAMES:
                    matches = [entry for entry in entries if _name(entry) == plugin]
                    if len(matches) != 1 or matches[0].get("enabled") is not True:
                        raise RuntimeError(
                            f"{runtime} did not report exactly one enabled {plugin}"
                        )
                    installed = _path(matches[0])
                    if installed is None:
                        raise RuntimeError(
                            f"{runtime} did not report a usable path for {plugin}"
                        )
                    installed = _validate_installed_path(
                        installed, runtime_homes[runtime]
                    )
                    actual = _tree_digest(installed)
                    if actual != expected[plugin]:
                        source = temp / "provider-unavailable" / "plugins" / plugin
                        source_files = {
                            path.relative_to(source).as_posix()
                            for path in source.rglob("*")
                            if path.is_file()
                        }
                        installed_files = {
                            path.relative_to(installed).as_posix()
                            for path in installed.rglob("*")
                            if path.is_file()
                        }
                        raise RuntimeError(
                            f"{runtime} installed digest mismatch for {plugin}; "
                            f"path={installed}; "
                            f"missing={sorted(source_files - installed_files)}; "
                            f"extra={sorted(installed_files - source_files)}"
                        )
                    actual_skills = {
                        path.parent.name
                        for path in (installed / "skills").glob("*/SKILL.md")
                    }
                    if actual_skills != set(PLUGIN_SKILLS[plugin]):
                        raise RuntimeError(
                            f"{runtime} installed skill inventory mismatch for {plugin}"
                        )
                    runtime_result[plugin] = actual
                consumer_result[runtime] = runtime_result
            verified[consumer_root.name] = consumer_result

    print(
        json.dumps(
            {"status": "ok", "consumer_count": len(consumer_roots), "verified": verified},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
