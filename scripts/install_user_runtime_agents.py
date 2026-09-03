#!/usr/bin/env python3
"""Install reviewed Yoke agents and Claude commands into explicit user homes.

This is deliberately separate from plugin activation.  It reads only the checked-in
capability allowlists, never infers a home directory, and writes only with --apply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "capability-sources.json"
RECEIPT_NAME = "mir-yoke-agent-command-receipt.json"
MANAGED_BY = "mir-yoke-user-runtime-agent-command-sync"
SOURCE_COMMIT_LENGTH = 40
SHADOWING = "project-local files take precedence over these user-level files."


class SyncError(RuntimeError):
    """Raised when an unsafe or divergent sync surface is encountered."""


@dataclass(frozen=True)
class ManagedFile:
    source_relative: str
    target_relative: Path
    content: bytes
    sha256: str


@dataclass(frozen=True)
class StaleFile:
    source_relative: str
    target_relative: Path
    sha256: str


@dataclass(frozen=True)
class HomeIdentity:
    path: Path
    canonical_path: Path
    device: int
    inode: int


@dataclass(frozen=True)
class Snapshot:
    relative: Path
    before: bytes | None
    after: bytes | None


@dataclass(frozen=True)
class RuntimePlan:
    identity: HomeIdentity
    files: tuple[ManagedFile, ...]
    stale: tuple[StaleFile, ...]
    receipt: bytes
    created_home: bool


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_safe_relative(path: str, *, prefix: str, suffix: str) -> bool:
    candidate = Path(path)
    return (
        path.startswith(prefix)
        and path.endswith(suffix)
        and candidate.as_posix() == path
        and not candidate.is_absolute()
        and ".." not in candidate.parts
        and len(candidate.parts) == 3
    )


def regular_source(path: Path) -> bytes:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise SyncError(f"missing source file: {path.relative_to(ROOT)}") from error
    if not stat.S_ISREG(mode):
        raise SyncError(f"source is not a regular file: {path.relative_to(ROOT)}")
    return path.read_bytes()


def load_sources() -> tuple[list[ManagedFile], list[ManagedFile]]:
    try:
        config = json.loads(regular_source(CONFIG_PATH))
        agent_allowlist = config["agents"]["allowlist"]
        command_allowlist = config["commands"]["allowlist"]
        packs = config["profiles"]["packs"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise SyncError("invalid capability source allowlists") from error
    if (
        not isinstance(agent_allowlist, list)
        or not isinstance(command_allowlist, dict)
        or not isinstance(packs, dict)
    ):
        raise SyncError("invalid capability source allowlists")

    selected_agents: set[str] = set()
    selected_commands: set[str] = set()
    for pack_name, pack in packs.items():
        if not isinstance(pack_name, str) or not isinstance(pack, dict):
            raise SyncError("invalid capability profile pack")
        agents = pack.get("agents")
        commands = pack.get("commands")
        if not isinstance(agents, list) or not isinstance(commands, list):
            raise SyncError(f"invalid capability profile pack: {pack_name}")
        for relative in agents:
            if not isinstance(relative, str) or relative not in agent_allowlist:
                raise SyncError(f"profile agent is not allowlisted: {relative!r}")
            selected_agents.add(relative)
        for relative in commands:
            if not isinstance(relative, str) or relative not in command_allowlist:
                raise SyncError(f"profile command is not allowlisted: {relative!r}")
            selected_commands.add(relative)

    claude: list[ManagedFile] = []
    codex: list[ManagedFile] = []
    for relative in sorted(selected_agents):
        if not is_safe_relative(
            relative, prefix=".claude/agents/", suffix=".md"
        ):
            raise SyncError(f"unsafe agent allowlist path: {relative!r}")
        source = ROOT / relative
        content = regular_source(source)
        claude.append(
            ManagedFile(
                relative,
                Path(*Path(relative).parts[1:]),
                content,
                sha256_bytes(content),
            )
        )
        codex_relative = relative.replace(".claude/agents/", ".codex/agents/")[:-3] + ".toml"
        codex_source = ROOT / codex_relative
        codex_content = regular_source(codex_source)
        codex.append(
            ManagedFile(
                codex_relative,
                Path(*Path(codex_relative).parts[1:]),
                codex_content,
                sha256_bytes(codex_content),
            )
        )
    for relative in sorted(selected_commands):
        if not is_safe_relative(
            relative, prefix=".claude/commands/", suffix=".md"
        ):
            raise SyncError(f"unsafe command allowlist path: {relative!r}")
        source = ROOT / relative
        content = regular_source(source)
        claude.append(
            ManagedFile(
                relative,
                Path(*Path(relative).parts[1:]),
                content,
                sha256_bytes(content),
            )
        )
    return claude, codex


def require_safe_home(path: Path) -> Path:
    if not path.is_absolute():
        raise SyncError("runtime homes must be explicit absolute non-root paths")
    normalized = Path(os.path.normpath(path))
    if normalized == Path(normalized.anchor):
        raise SyncError("runtime homes must be explicit absolute non-root paths")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise SyncError(f"symlinked target path is not allowed: {current}")
        if current.exists() and not current.is_dir():
            raise SyncError(f"target path component is not a directory: {current}")
    return normalized


def safe_target(home: Path, relative: Path) -> Path:
    target = home.joinpath(*relative.parts)
    current = home
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise SyncError(f"symlinked target path is not allowed: {current}")
        if current.exists() and not current.is_dir():
            raise SyncError(f"target path component is not a directory: {current}")
    if target.is_symlink():
        raise SyncError(f"symlinked target path is not allowed: {target}")
    if target.exists() and not target.is_file():
        raise SyncError(f"target is not a regular file: {target}")
    return target


def capture_home_identity(home: Path) -> HomeIdentity:
    try:
        details = home.lstat()
    except OSError as error:
        raise SyncError(f"cannot inspect runtime home: {home}") from error
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise SyncError(f"runtime home is not a real directory: {home}")
    canonical_path = home.resolve(strict=True)
    if canonical_path != home:
        raise SyncError(f"symlinked target path is not allowed: {home}")
    return HomeIdentity(home, canonical_path, details.st_dev, details.st_ino)


def verified_target(identity: HomeIdentity, relative: Path) -> Path:
    try:
        details = identity.path.lstat()
        canonical_path = identity.path.resolve(strict=True)
    except OSError as error:
        raise SyncError(f"runtime home changed during apply: {identity.path}") from error
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or canonical_path != identity.canonical_path
        or details.st_dev != identity.device
        or details.st_ino != identity.inode
    ):
        raise SyncError(f"runtime home changed during apply: {identity.path}")
    return safe_target(identity.path, relative)


def receipt_for(home: Path) -> Path:
    return safe_target(home, Path(RECEIPT_NAME))


def load_receipt(home: Path, runtime: str) -> tuple[Path, dict[str, Any] | None]:
    path = receipt_for(home)
    if not path.exists():
        return path, None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"unmanaged existing receipt: {path}") from error
    if (
        not isinstance(receipt, dict)
        or receipt.get("managed_by") != MANAGED_BY
        or receipt.get("runtime") != runtime
        or not isinstance(receipt.get("files"), dict)
    ):
        raise SyncError(f"unmanaged existing receipt: {path}")
    return path, receipt


def receipt_allows_update(receipt: dict[str, Any] | None, item: ManagedFile, target: Path) -> bool:
    if receipt is None:
        return False
    recorded = receipt["files"].get(item.source_relative)
    return (
        isinstance(recorded, dict)
        and recorded.get("source") == item.source_relative
        and recorded.get("target") == item.target_relative.as_posix()
        and recorded.get("sha256") == sha256_bytes(target.read_bytes())
    )


def receipt_path_is_safe(runtime: str, source_relative: str, target: str) -> Path:
    if runtime == "claude":
        valid = is_safe_relative(source_relative, prefix=".claude/agents/", suffix=".md") or (
            is_safe_relative(source_relative, prefix=".claude/commands/", suffix=".md")
        )
    else:
        valid = is_safe_relative(source_relative, prefix=".codex/agents/", suffix=".toml")
    expected = Path(*Path(source_relative).parts[1:])
    if not valid or target != expected.as_posix():
        raise SyncError(f"invalid managed receipt entry: {source_relative!r}")
    return expected


def stale_files(
    home: Path, runtime: str, receipt: dict[str, Any] | None, files: list[ManagedFile]
) -> list[StaleFile]:
    if receipt is None:
        return []
    current_sources = {item.source_relative for item in files}
    stale: list[StaleFile] = []
    for source_relative, recorded in sorted(receipt["files"].items()):
        if source_relative in current_sources:
            continue
        if not isinstance(source_relative, str) or not isinstance(recorded, dict):
            raise SyncError("invalid managed receipt entry")
        target_value = recorded.get("target")
        digest = recorded.get("sha256")
        if (
            recorded.get("source") != source_relative
            or not isinstance(target_value, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise SyncError(f"invalid managed receipt entry: {source_relative!r}")
        target_relative = receipt_path_is_safe(runtime, source_relative, target_value)
        target = safe_target(home, target_relative)
        if target.exists() and sha256_bytes(target.read_bytes()) != digest:
            raise SyncError(f"diverged stale managed file; refusing removal: {target}")
        if target.exists():
            stale.append(StaleFile(source_relative, target_relative, digest))
    return stale


def validate_targets(
    home: Path, runtime: str, files: list[ManagedFile]
) -> tuple[Path, list[StaleFile]]:
    receipt_path, receipt = load_receipt(home, runtime)
    for item in files:
        target = safe_target(home, item.target_relative)
        if target.exists() and sha256_bytes(target.read_bytes()) != item.sha256:
            if receipt_allows_update(receipt, item, target):
                continue
            if receipt is None:
                raise SyncError(f"unmanaged existing file; refusing overwrite: {target}")
            raise SyncError(f"diverged managed file; refusing overwrite: {target}")
    return receipt_path, stale_files(home, runtime, receipt, files)


def atomic_write(identity: HomeIdentity, relative: Path, content: bytes) -> None:
    path = verified_target(identity, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = verified_target(identity, relative)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def target_bytes(identity: HomeIdentity, relative: Path) -> bytes | None:
    target = verified_target(identity, relative)
    return target.read_bytes() if target.exists() else None


def snapshot_plan(plan: RuntimePlan) -> tuple[Snapshot, ...]:
    desired: dict[Path, bytes | None] = {
        item.target_relative: item.content for item in plan.files
    }
    desired.update({item.target_relative: None for item in plan.stale})
    desired[Path(RECEIPT_NAME)] = plan.receipt
    return tuple(
        Snapshot(relative, target_bytes(plan.identity, relative), after)
        for relative, after in sorted(desired.items())
    )


def remove_stale_file(identity: HomeIdentity, item: StaleFile) -> None:
    target = verified_target(identity, item.target_relative)
    if not target.exists():
        return
    if sha256_bytes(target.read_bytes()) != item.sha256:
        raise SyncError(f"diverged stale managed file; refusing removal: {target}")
    target.unlink()


def apply_plan(plan: RuntimePlan) -> None:
    for item in plan.files:
        atomic_write(plan.identity, item.target_relative, item.content)
    for item in plan.stale:
        remove_stale_file(plan.identity, item)
    atomic_write(plan.identity, Path(RECEIPT_NAME), plan.receipt)


def restore_snapshot(identity: HomeIdentity, snapshot: Snapshot) -> None:
    current = target_bytes(identity, snapshot.relative)
    if snapshot.before is None:
        if current is None:
            return
        if current != snapshot.after:
            raise SyncError(f"rollback found unexpected file: {identity.path / snapshot.relative}")
        verified_target(identity, snapshot.relative).unlink()
        return
    if current == snapshot.before:
        return
    if current is not None and current != snapshot.after:
        raise SyncError(f"rollback found unexpected file: {identity.path / snapshot.relative}")
    atomic_write(identity, snapshot.relative, snapshot.before)


def remove_created_home(plan: RuntimePlan, snapshots: tuple[Snapshot, ...]) -> None:
    if not plan.created_home:
        return
    verified_target(plan.identity, Path(RECEIPT_NAME))
    directories = {
        plan.identity.path / snapshot.relative.parent
        for snapshot in snapshots
        if snapshot.relative.parent != Path(".")
    }
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        if directory.exists():
            if directory.is_symlink() or not directory.is_dir():
                raise SyncError(f"rollback found unsafe directory: {directory}")
            directory.rmdir()
    verified_target(plan.identity, Path(RECEIPT_NAME))
    plan.identity.path.rmdir()


def apply_transaction(plans: tuple[RuntimePlan, ...]) -> None:
    snapshots = {plan.identity.path: snapshot_plan(plan) for plan in plans}
    try:
        for plan in plans:
            apply_plan(plan)
    except Exception as error:
        rollback_errors: list[str] = []
        for plan in reversed(plans):
            try:
                for snapshot in reversed(snapshots[plan.identity.path]):
                    restore_snapshot(plan.identity, snapshot)
                remove_created_home(plan, snapshots[plan.identity.path])
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise SyncError(
                f"apply failed; rollback incomplete: {error}; {'; '.join(rollback_errors)}"
            ) from error
        raise SyncError(f"apply failed; rollback complete: {error}") from error


def make_receipt(runtime: str, source_commit: str, files: list[ManagedFile]) -> bytes:
    receipt = {
        "schema_version": 1,
        "managed_by": MANAGED_BY,
        "runtime": runtime,
        "source_commit": source_commit,
        "files": {
            item.source_relative: {
                "source": item.source_relative,
                "target": item.target_relative.as_posix(),
                "sha256": item.sha256,
            }
            for item in files
        },
    }
    return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()


def source_commit() -> str:
    status = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        capture_output=True,
        check=False,
        text=True,
    )
    if status.returncode != 0:
        raise SyncError("cannot establish clean Yoke source")
    if status.stdout:
        raise SyncError("Yoke source is dirty; commit or clean it before syncing")
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    commit = head.stdout.strip()
    if (
        head.returncode != 0
        or len(commit) != SOURCE_COMMIT_LENGTH
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise SyncError("cannot resolve Yoke source Git commit")
    return commit


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-home", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="perform the otherwise dry-run sync")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        claude_home = require_safe_home(arguments.claude_home)
        codex_home = require_safe_home(arguments.codex_home)
        if claude_home == codex_home:
            raise SyncError("--claude-home and --codex-home must be different paths")
        commit = source_commit()
        claude_files, codex_files = load_sources()
        claude_receipt, stale_claude = validate_targets(claude_home, "claude", claude_files)
        codex_receipt, stale_codex = validate_targets(codex_home, "codex", codex_files)
        report = {
            "status": "applied" if arguments.apply else "dry_run",
            "source_commit": commit,
            "shadowing": SHADOWING,
            "planned": {
                "claude": [item.source_relative for item in claude_files],
                "codex": [item.source_relative for item in codex_files],
            },
            "planned_removals": {
                "claude": [item.source_relative for item in stale_claude],
                "codex": [item.source_relative for item in stale_codex],
            },
            "receipts": {
                "claude": str(claude_receipt),
                "codex": str(codex_receipt),
            },
        }
        if arguments.apply:
            claude_exists = claude_home.exists()
            codex_exists = codex_home.exists()
            try:
                claude_home.mkdir(parents=True, exist_ok=True)
                codex_home.mkdir(parents=True, exist_ok=True)
                claude_identity = capture_home_identity(claude_home)
                codex_identity = capture_home_identity(codex_home)
                plans = (
                    RuntimePlan(
                        claude_identity,
                        tuple(claude_files),
                        tuple(stale_claude),
                        make_receipt("claude", commit, claude_files),
                        not claude_exists,
                    ),
                    RuntimePlan(
                        codex_identity,
                        tuple(codex_files),
                        tuple(stale_codex),
                        make_receipt("codex", commit, codex_files),
                        not codex_exists,
                    ),
                )
                apply_transaction(plans)
            except Exception as error:
                if isinstance(error, SyncError):
                    raise
                raise SyncError(f"apply failed before transaction: {error}") from error
        print(json.dumps(report, sort_keys=True))
        return 0
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"error: unexpected installer failure: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
