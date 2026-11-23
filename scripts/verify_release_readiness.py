"""Verify release readiness from a clean candidate Git tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from mir.core.capabilities.native import host_target, validate_artifacts

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    (
        "focused-contracts",
        (
            "uv",
            "run",
            "pytest",
            "-q",
            "tests/test_project_agent_kit.py",
            "tests/test_project_agent_kit_release_evidence.py",
            "tests/test_minimal_starter.py",
            "tests/test_public_template_identity.py",
            "tests/test_template_asset_classification.py",
            "tests/test_decision_authority.py",
            "tests/test_public_template_surface.py",
            "tests/test_plugin_skill_packages.py",
            "tests/test_common_skill_contracts.py",
            "tests/test_capability_security.py",
        ),
    ),
    (
        "public-cli",
        (
            "uv",
            "run",
            "pytest",
            "-q",
            "tests/test_installed_cli.py",
            "tools/mir_executor/tests/test_policy.py",
        ),
    ),
    ("asset-classification", ("uv", "run", "python", "-m", "tools.template_assets", "--json")),
    ("derivatives", ("uv", "run", "python", "scripts/verify_codex_sync.py")),
    ("sanitization", ("uv", "run", "python", "tests/test_no_korean_in_user_facing.py")),
    ("links", ("uv", "run", "python", "tests/test_link_integrity.py")),
    ("schemas", ("uv", "run", "python", "tests/test_schema_validity.py")),
    ("full-tests", ("uv", "run", "pytest", "-q")),
    ("lint", ("uv", "run", "ruff", "check")),
)
EVIDENCE_CHECK = (
    "project-agent-kit-clean-room-evidence",
    ("uv", "run", "python", "scripts/verify_project_agent_kit_evidence.py"),
)
CAPABILITY_LOCK = Path(".mir/capability-lock.json")
CLI_PIN = Path("config/cli-native-artifacts.json")
CLI_SELECTOR = Path("config/cli-native-pin.jq")
PLUGIN_ROOTS = ("${CLAUDE_PLUGIN_ROOT}/", "${CODEX_PLUGIN_ROOT}/")


def _candidate_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(path for path in result.stdout.splitlines() if path and (root / path).is_file())


def _materialize_candidate(source: Path, target: Path) -> None:
    subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", str(source), str(target)],
        check=True,
    )
    desired = set(_candidate_paths(source))
    cloned = set(_candidate_paths(target))
    for relative in sorted(cloned - desired):
        target_path = target / relative
        if target_path.is_file() or target_path.is_symlink():
            target_path.unlink()
            parent = target_path.parent
            while parent != target:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
    for relative in sorted(desired):
        source_path = source / relative
        target_path = target / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            target_path.symlink_to(source_path.readlink())
        else:
            shutil.copy2(source_path, target_path)
    subprocess.run(["git", "add", "-A"], cwd=target, check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Mir Yoke Readiness",
        "GIT_AUTHOR_EMAIL": "readiness@invalid",
        "GIT_COMMITTER_NAME": "Mir Yoke Readiness",
        "GIT_COMMITTER_EMAIL": "readiness@invalid",
    }
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=target).returncode
    if changed:
        subprocess.run(
            ["git", "commit", "-q", "-m", "temporary release candidate"],
            cwd=target,
            check=True,
            env=env,
        )


def _asset_name(pin: dict) -> str:
    return Path(urlsplit(pin["url"]).path).name


def _install_artifact(assets: Path, destination: Path, pin: dict) -> str | None:
    name = _asset_name(pin)
    source = assets / name
    if name in {"", ".."} or source.is_symlink() or not source.is_file():
        return f"consumer-digest: missing regular pinned asset {source}"
    if destination.exists():
        return f"consumer-digest: pinned asset would overwrite {destination.name}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    mode = stat.S_IMODE(destination.stat().st_mode)
    if mode & ~0o755 or not mode & stat.S_IXUSR or not os.access(destination, os.X_OK):
        return f"consumer-mode: {name} has mode {mode:04o}, expected 0755 or stricter executable"
    with destination.open("rb") as binary:
        digest = hashlib.file_digest(binary, "sha256").hexdigest()
    if digest != pin["sha256"] or destination.stat().st_size != pin["size"]:
        return f"consumer-digest: {name} expected SHA-256 {pin['sha256']}, got {digest}"
    return None


def _hook_probe(plugin: Path, command: str) -> tuple[Path, bool]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)
    if not tokens:
        raise ValueError("empty hook command")
    executable = tokens[0]
    guarded = executable == "if"
    if guarded:
        launchers = [tokens[i + 1] for i, token in enumerate(tokens[:-1]) if token == "exec"]
        if len(launchers) != 1:
            raise ValueError("expected one exec in guarded hook command")
        executable = launchers[0]
        references = {token for token in tokens if token.startswith(PLUGIN_ROOTS)}
        if references != {executable} or not any(
            tokens[index:index + 3] == ["&&", executable, "--mir-warmup"]
            for index in range(len(tokens))
        ):
            raise ValueError("guarded hook paths or declared warmup do not match exec")

    if command.count(f'"{executable}"') != tokens.count(executable):
        raise ValueError("hook executable must be double-quoted for paths containing spaces")
    for prefix in PLUGIN_ROOTS:
        if executable.startswith(prefix):
            relative = executable.removeprefix(prefix)
            break
    else:
        raise ValueError(f"hook executable is not relative to its plugin root: {executable}")
    path = plugin / relative
    if (
        not path.resolve().is_relative_to(plugin)
        or not path.is_file()
        or not os.access(path, os.X_OK)
    ):
        raise ValueError(f"missing executable in install: {relative}")
    return path, guarded


def _run_manifest_hook(
    plugin: Path, command: str, event: str, install: Path, env: dict[str, str], timeout: int,
) -> None:
    path, guarded = _hook_probe(plugin, command)
    if not guarded:
        _run_probe([str(path), "--help"], install, env, timeout=timeout)
    hook_env = {**env, "CLAUDE_PLUGIN_ROOT": str(plugin), "CODEX_PLUGIN_ROOT": str(plugin)}
    with tempfile.TemporaryDirectory(prefix=".readiness-", dir=path.parent) as raw:
        executable, marker = Path(raw) / path.name, Path(raw) / "calls"
        event_input = Path(raw) / "event"
        path.rename(executable)
        try:
            # The wrapper observes the real executable's status, even when the
            # shipped command treats native unavailability as success. Record
            # exactly what reaches the event invocation's stdin and forward it.
            path.write_text(
                '#!/bin/sh\n'
                'kind=event\n'
                'if [ "${1:-}" = "--mir-warmup" ]; then\n'
                '  kind=--mir-warmup\n'
                'else\n'
                f'  cat > {shlex.quote(str(event_input))} || exit 1\n'
                f'  exec < {shlex.quote(str(event_input))}\n'
                'fi\n'
                f'{shlex.quote(str(executable))} "$@"\n'
                'result=$?\n'
                f'printf "%s %s\\n" "$kind" "$result" >> {shlex.quote(str(marker))}\n'
                'exit "$result"\n',
                encoding="utf-8",
            )
            path.chmod(0o700)
            payload = json.dumps({"hook_event_name": event, "cwd": str(install)}).encode()
            _run_probe(["/bin/sh", "-c", command], install, hook_env, timeout=timeout,
                       payload=payload)
            calls = marker.read_text(encoding="utf-8").splitlines() if marker.exists() else []
            for call in calls:
                _, status = call.rsplit(" ", 1)
                if status != "0":
                    raise ValueError(f"{path.name} exited {status}")
            expected = ["--mir-warmup 0", "event 0"] if guarded else ["event 0"]
            if calls != expected:
                raise ValueError(f"{path.name} did not receive the declared probe and event")
            if event_input.read_bytes() != payload:
                raise ValueError(f"{path.name} did not receive the synthetic event payload")
        finally:
            executable.replace(path)


def _probe_hooks(plugin: Path, required: bool, install: Path, env: dict[str, str]) -> list[str]:
    manifest = plugin / "hooks/hooks.json"
    if not required and not manifest.exists():
        return []
    errors = []
    try:
        events = json.loads(manifest.read_text(encoding="utf-8"))["hooks"]
        for event, groups in events.items():
            for group_index, group in enumerate(groups, start=1):
                for hook_index, hook in enumerate(group["hooks"], start=1):
                    if hook["type"] != "command":
                        continue
                    label = f"{plugin.name} {event} group {group_index} hook {hook_index}"
                    try:
                        # Both runtimes use this manifest on POSIX.
                        _run_manifest_hook(
                            plugin, hook["command"], event, install, env, hook.get("timeout", 10),
                        )
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        errors.append(f"consumer-hook: {label}: {exc}")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(f"consumer-hook: {plugin.name}/hooks/hooks.json: {exc}")
    return errors


def _run_probe(
    command: list[str], install: Path, env: dict[str, str], *,
    timeout: int, payload: bytes | None = None,
) -> None:
    result = subprocess.run(
        command, cwd=install, env=env, input=payload,
        stdin=subprocess.DEVNULL if payload is None else None, check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
    )
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} exited {result.returncode}")


def _candidate_assets(root: Path, lock: dict, target: str | None) -> list[tuple[Path, dict]]:
    commit = lock["source"]["commit"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
        raise ValueError("Mir CLI source commit is invalid")
    if target is None:
        raise ValueError("no native Mir CLI target for this host")
    selection = subprocess.run(
        ["jq", "-er", "--arg", "target", target, "--arg", "commit", commit,
         "-f", str(root / CLI_SELECTOR), str(root / CLI_PIN)],
        capture_output=True, text=True, check=False,
    )
    if selection.returncode:
        raise ValueError(f"no valid native Mir CLI pin for {target} at {commit} in {CLI_PIN}")
    url, digest, size = selection.stdout.rstrip("\n").split("\t")
    assets = [(Path("bin/mir"), {"url": url, "sha256": digest, "size": int(size)})]
    entries = lock["plugins"]
    binaries = validate_artifacts(lock["native_artifacts"], entries, portable=True)
    for artifact in binaries.values():
        if target in artifact["targets"]:
            path = Path(entries[artifact["plugin"]]["path"]) / artifact["install_path"]
            assets.append((path, artifact["targets"][target]))
    return assets


def _consumer_errors(root: Path, assets: Path, install: Path) -> list[str]:
    try:
        lock = json.loads((root / CAPABILITY_LOCK).read_text(encoding="utf-8"))
        entries = lock["plugins"]
        artifacts = _candidate_assets(root, lock, host_target())
        for relative in (CAPABILITY_LOCK, CLI_PIN, CLI_SELECTOR):
            (install / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, install / relative)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"consumer-digest: cannot load candidate pins: {exc}"]

    plugins = {}
    try:
        for name, entry in entries.items():
            relative = Path(entry["path"])
            if relative.parent != Path("plugins") or relative.name != name:
                raise ValueError(f"invalid plugin path: {relative}")
            source, destination = root / relative, install / relative
            if source.resolve() != source or any(path.is_symlink() for path in source.rglob("*")):
                raise ValueError(f"linked plugin path: {relative}")
            shutil.copytree(source, destination)
            plugins[name] = destination
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f"consumer-hook: cannot copy candidate plugin: {exc}"]

    errors = []
    for relative, pin in artifacts:
        destination = install / relative
        try:
            error = _install_artifact(assets, destination, pin)
            if error:
                errors.append(error)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"consumer-digest: cannot copy or verify {destination.name}: {exc}")
    if errors:
        return errors

    home = install.parent / "home"
    temp = install.parent / "tmp"
    home.mkdir()
    temp.mkdir()
    env = {
        "HOME": str(home),
        "TMPDIR": str(temp),
        "PATH": os.environ.get("PATH", os.defpath),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "UV_OFFLINE": "1",
    }
    for name, plugin in plugins.items():
        required = entries[name]["package_kind"] == "skills-hooks"
        errors.extend(_probe_hooks(plugin, required, install, env))
    if not errors and "MIR_RELEASE_CONSUMER_CHECK" in os.environ:
        try:
            runner = Path(os.environ["MIR_RELEASE_CONSUMER_CHECK"]).absolute()
            if not runner.is_file() or not os.access(runner, os.X_OK):
                raise ValueError(f"not an executable file: {runner}")
            _run_probe([str(runner), str(install)], install, env, timeout=300)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"consumer-contract: {exc}")
    return errors


def check_consumer_contract(root: Path, assets: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="mir-release-consumer-") as raw:
        errors = _consumer_errors(root.resolve(), assets.resolve(), Path(raw).resolve() / "install")
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


def run_checks(
    root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    *,
    require_evidence: bool = False,
    native_artifacts_dir: Path | None = None,
    repository_only: bool = False,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    if not repository_only:
        assets = native_artifacts_dir or root / "assets"
        status = check_consumer_contract(root, assets)
        results.append({"name": "consumer-contract", "exit_code": status})
        if status:
            return results
    checks = CHECKS + ((EVIDENCE_CHECK,) if require_evidence else ())
    for name, command in checks:
        completed = runner(command, cwd=root, check=False, text=True)
        results.append({"name": name, "command": list(command), "exit_code": completed.returncode})
        if completed.returncode != 0:
            break
    return results


def _verify_clean_tree(root: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise RuntimeError("release verification requires a clean candidate Git tree")


# @spec CR-006 FR-007 IR-001
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_release_readiness.py")
    parser.add_argument("--current-clean-tree", action="store_true")
    parser.add_argument("--require-project-agent-kit-evidence", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--native-artifacts-dir", type=Path, help="offline release assets")
    mode.add_argument("--repository-only", action="store_true", help="post-tag repository checks")
    args = parser.parse_args(argv)

    if not args.current_clean_tree:
        with tempfile.TemporaryDirectory(prefix="mir-yoke-release-") as raw:
            candidate = Path(raw) / "candidate"
            _materialize_candidate(ROOT, candidate)
            command = [
                "uv",
                "run",
                "--extra",
                "dev",
                "--extra",
                "vector",
                "python",
                "scripts/verify_release_readiness.py",
                "--current-clean-tree",
            ]
            if args.require_project_agent_kit_evidence:
                command.append("--require-project-agent-kit-evidence")
            if args.repository_only:
                command.append("--repository-only")
            else:
                assets = args.native_artifacts_dir or ROOT / "assets"
                command.extend(["--native-artifacts-dir", str(assets.resolve())])
            return subprocess.run(command, cwd=candidate, check=False).returncode

    try:
        _verify_clean_tree(ROOT)
        results = run_checks(
            ROOT,
            require_evidence=args.require_project_agent_kit_evidence,
            native_artifacts_dir=args.native_artifacts_dir,
            repository_only=args.repository_only,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"release readiness: ERROR: {exc}", file=sys.stderr)
        return 1
    expected_count = len(CHECKS) + args.require_project_agent_kit_evidence
    expected_count += not args.repository_only
    ready = len(results) == expected_count and all(row["exit_code"] == 0 for row in results)
    print(json.dumps({"ready": ready, "checks": results}, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
