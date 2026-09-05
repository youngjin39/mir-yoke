"""Transactional final-step slimming for a product adopter checkout."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import jsonschema

from .boundary import (
    BOUNDARY_PATH,
    BoundaryError,
    is_provider_owner,
    load_boundary,
    load_profile,
    payload_findings,
)

Verify = Callable[[Path, Path], tuple[bool, str]]
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_RELEASE_CONTROL_PATHS = (BOUNDARY_PATH, Path("config/adopter-payload.json"))
_CANONICAL_PROVIDER_TYPES = {"public_harness_template", "template_transitional"}
_JOURNAL_PATH = Path(".mir/slim-transaction.json")
_LOCK_PATH = Path(".mir/slim.lock")


class SlimError(RuntimeError):
    """Slimming could not complete without risking adopter-owned content."""


def _require_supported_platform() -> None:
    platform_name = platform.system()
    if platform_name == "Windows":
        raise SlimError(
            "Native Windows adopter slim is unsupported; run setup.sh inside WSL or "
            "use agent-guided existing-repository/reference adaptation"
        )
    if platform_name not in {"Darwin", "Linux"}:
        raise SlimError(
            "Adopter slim supports macOS, Linux, and WSL; use agent-guided "
            "existing-repository/reference adaptation on this platform"
        )


def _safe_relative(raw: object) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise SlimError(f"invalid adopter payload path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise SlimError(f"unsafe adopter payload path: {raw!r}")
    return path.as_posix()


def _load_payload(project_root: Path, boundary: dict[str, object]) -> dict[str, object]:
    raw_path = boundary.get("payload_manifest")
    relative = _safe_relative(raw_path)
    path = project_root / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SlimError(f"cannot read adopter payload manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SlimError("adopter payload manifest must be a schema_version=1 object")
    schema_ref = payload.get("$schema")
    if isinstance(schema_ref, str):
        try:
            schema = json.loads((path.parent / schema_ref).read_text(encoding="utf-8"))
            jsonschema.validate(payload, schema)
        except (OSError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            raise SlimError(f"invalid adopter payload manifest: {exc}") from exc
    files = payload.get("files")
    if not isinstance(files, list):
        raise SlimError("adopter payload manifest requires a files array")
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise SlimError("adopter payload file entries must be objects")
        relative = _safe_relative(item.get("path"))
        if relative in seen:
            raise SlimError(f"duplicate adopter payload path: {relative}")
        seen.add(relative)
        item["path"] = relative
        digest = item.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SlimError(f"invalid adopter payload digest: {relative}")
        if item.get("disposition") not in {"preserve", "remove"}:
            raise SlimError(f"invalid adopter payload disposition: {relative}")
    return payload


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_release_controls(project_root: Path, profile: dict[str, object]) -> None:
    repo = profile.get("repo")
    commit = repo.get("profile_base_commit") if isinstance(repo, dict) else None
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise SlimError("slim requires a Git-bound profile_base_commit from greenfield Phase 1")
    for relative in _RELEASE_CONTROL_PATHS:
        control_path = project_root / relative
        if not _is_safe_project_file(project_root, control_path):
            raise SlimError(f"release control is not a safe project file: {relative}")
        completed = subprocess.run(
            ["git", "show", f"{commit}:{relative.as_posix()}"],
            cwd=project_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SlimError(
                f"cannot read release control {relative} from profile base commit {commit}"
            )
        try:
            current = control_path.read_bytes()
        except OSError as exc:
            raise SlimError(f"cannot read release control {relative}: {exc}") from exc
        if current != completed.stdout:
            raise SlimError(
                f"release control changed after Phase 1; slim made no changes: {relative}"
            )


def _is_canonical_provider_profile(profile: dict[str, object]) -> bool:
    """Provide a non-destructive fallback for older Mir Yoke maintainer Profiles."""
    repo = profile.get("repo")
    return bool(
        isinstance(repo, dict)
        and repo.get("slug") == "mir-yoke"
        and repo.get("repository_type") in _CANONICAL_PROVIDER_TYPES
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_safe_project_file(project_root: Path, target: Path) -> bool:
    """Require every lexical path component and the final file to be non-symlinks."""
    try:
        relative = target.relative_to(project_root)
    except ValueError:
        return False
    current = project_root
    final_mode: int | None = None
    for part in relative.parts:
        current /= part
        try:
            final_mode = os.lstat(current).st_mode
        except OSError:
            return False
        if stat.S_ISLNK(final_mode):
            return False
    return bool(
        final_mode is not None
        and stat.S_ISREG(final_mode)
        and _is_within(target.resolve(strict=True), project_root)
    )


def _validated_mir_directory(root: Path) -> Path:
    mir_dir = root / ".mir"
    try:
        mode = os.lstat(mir_dir).st_mode
        resolved = mir_dir.resolve(strict=True)
    except OSError as exc:
        raise SlimError(f"slim requires a real .mir directory: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or not _is_within(resolved, root):
        raise SlimError("slim requires a real .mir directory inside the adopter repository")
    return mir_dir


def _validated_project_directory(root: Path, directory: Path, *, label: str) -> Path:
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise SlimError(f"{label} escapes the adopter repository") from exc
    current = root
    final_mode: int | None = None
    for part in relative.parts:
        current /= part
        try:
            final_mode = os.lstat(current).st_mode
        except OSError as exc:
            raise SlimError(f"{label} is unavailable: {exc}") from exc
        if stat.S_ISLNK(final_mode):
            raise SlimError(f"{label} contains a symlinked path component")
    if (
        final_mode is None
        or not stat.S_ISDIR(final_mode)
        or not _is_within(directory.resolve(strict=True), root)
    ):
        raise SlimError(f"{label} is not a real adopter directory")
    return directory


def _ensure_quarantine_root(root: Path) -> Path:
    quarantine_root = root / ".mir" / "slim-quarantine"
    if quarantine_root.exists() or quarantine_root.is_symlink():
        return _validated_project_directory(root, quarantine_root, label="slim quarantine root")
    try:
        os.mkdir(quarantine_root, 0o700)
    except OSError as exc:
        raise SlimError(f"cannot create slim quarantine root: {exc}") from exc
    return _validated_project_directory(root, quarantine_root, label="slim quarantine root")


def _validate_external_cli(project_root: Path, external_cli: Path) -> Path:
    lexical = Path(os.path.abspath(external_cli.expanduser()))
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise SlimError(f"external Mir CLI is unavailable: {exc}") from exc
    if not resolved.is_file() or _is_within(resolved, project_root):
        raise SlimError("slim requires a Mir CLI installed outside the adopter repository")
    clean_env = os.environ.copy()
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        clean_env.pop(name, None)
    completed = subprocess.run(
        [str(resolved), "bootstrap", "--help"],
        cwd=project_root,
        env=clean_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise SlimError(f"external Mir CLI preflight failed: {detail}")
    return lexical


def _default_verify(external_cli: Path, project_root: Path) -> tuple[bool, str]:
    clean_env = os.environ.copy()
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        clean_env.pop(name, None)
    completed = subprocess.run(
        [
            str(external_cli),
            "capability",
            "status",
            "--project-root",
            str(project_root),
            "--json",
        ],
        cwd=project_root,
        env=clean_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False, completed.stderr.strip() or f"exit {completed.returncode}"
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return False, "capability status did not return JSON"
    read_only_evidence = report.get("change_evidence") == {
        "status": "not-applicable",
        "reason": "read-only-operation",
    }
    ready = report.get("ready") is True and (
        report.get("changed_paths") == [] or read_only_evidence
    )
    return ready, "ready" if ready else "capability status is not ready and read-only"


def _marker_files(project_root: Path, relative: str) -> list[Path]:
    marker = project_root / relative
    if marker.is_symlink():
        return [marker]
    if marker.is_file():
        return [marker]
    if not marker.exists():
        return []
    return sorted(
        (path for path in marker.rglob("*") if path.is_file() or path.is_symlink()),
        key=lambda path: path.as_posix(),
    )


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _prune_empty_parents(path: Path, project_root: Path) -> None:
    current = path.parent
    while current != project_root and _is_within(current, project_root):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _atomic_fsync_json(path: Path, payload: dict[str, object]) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp_path.unlink(missing_ok=True)


def _load_journal(root: Path) -> dict[str, object] | None:
    path = root / _JOURNAL_PATH
    if path.is_symlink():
        raise SlimError("cannot recover unsafe slim journal symlink")
    if not path.exists():
        return None
    if not path.is_file():
        raise SlimError("cannot recover non-file slim journal")
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SlimError(f"cannot recover invalid slim journal: {exc}") from exc
    transaction_id = journal.get("transaction_id") if isinstance(journal, dict) else None
    paths = journal.get("paths") if isinstance(journal, dict) else None
    if (
        not isinstance(transaction_id, str)
        or not re.fullmatch(r"[0-9a-f]{32}", transaction_id)
        or not isinstance(paths, list)
    ):
        raise SlimError("cannot recover malformed slim journal")
    journal["paths"] = [_safe_relative(value) for value in paths]
    return journal


def _process_alive(raw_pid: object) -> bool:
    if not isinstance(raw_pid, int) or raw_pid <= 0:
        return False
    try:
        os.kill(raw_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _safe_parent_for_restore(root: Path, parent: Path) -> bool:
    try:
        relative = parent.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() or current.is_symlink():
            try:
                mode = os.lstat(current).st_mode
            except OSError:
                return False
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                return False
        else:
            current.mkdir()
    return True


def _rollback_journal(root: Path, journal: dict[str, object]) -> list[str]:
    _validated_mir_directory(root)
    transaction_id = str(journal["transaction_id"])
    quarantine = root / ".mir" / "slim-quarantine" / transaction_id
    errors: list[str] = []
    for relative in reversed(list(journal["paths"])):
        source = root / str(relative)
        destination = quarantine / str(relative)
        source_present = source.exists() or source.is_symlink()
        destination_present = destination.exists() or destination.is_symlink()
        if source_present and not destination_present:
            continue
        if source_present or not destination_present:
            errors.append(f"{relative}: ambiguous rollback state")
            continue
        if not _is_safe_project_file(root, destination):
            errors.append(f"{relative}: quarantine source is unsafe")
            continue
        if not _safe_parent_for_restore(root, source.parent):
            errors.append(f"{relative}: restore parent is unsafe")
            continue
        try:
            os.replace(destination, source)
        except OSError as exc:
            errors.append(f"{relative}: {exc}")
    if not errors:
        _prune_empty_parents(quarantine / "placeholder", root / ".mir")
        (root / _JOURNAL_PATH).unlink(missing_ok=True)
        (root / _LOCK_PATH).unlink(missing_ok=True)
    return errors


def recover_adopter_slim(project_root: Path) -> dict[str, object]:
    _require_supported_platform()
    root = project_root.expanduser().resolve(strict=True)
    _validated_mir_directory(root)
    journal = _load_journal(root)
    lock_path = root / _LOCK_PATH
    if lock_path.exists() or lock_path.is_symlink():
        if not _is_safe_project_file(root, lock_path):
            raise SlimError("cannot recover unsafe slim lock")
    if journal is None:
        if lock_path.is_file():
            try:
                pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pid = -1
            if _process_alive(pid):
                raise SlimError("another adopter slim transaction is active")
            lock_path.unlink(missing_ok=True)
        return {"status": "clean"}
    if _process_alive(journal.get("pid")):
        raise SlimError("another adopter slim transaction is active")
    receipt_path = root / ".mir/bootstrap-receipt.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        if not _is_safe_project_file(root, receipt_path):
            raise SlimError("cannot recover with an unsafe bootstrap receipt")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            receipt = {}
    else:
        receipt = {}
    if (
        receipt.get("status") == "ready"
        and isinstance(receipt.get("slim"), dict)
        and receipt["slim"].get("transaction_id") == journal["transaction_id"]
    ):
        (root / _JOURNAL_PATH).unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
        return {"status": "committed", "transaction_id": journal["transaction_id"]}
    errors = _rollback_journal(root, journal)
    if errors:
        raise SlimError("slim recovery incomplete: " + "; ".join(errors))
    return {"status": "rolled_back", "transaction_id": journal["transaction_id"]}


def commit_adopter_slim(project_root: Path, report: dict[str, object]) -> None:
    if report.get("status") != "applied":
        return
    _require_supported_platform()
    root = project_root.expanduser().resolve(strict=True)
    _validated_mir_directory(root)
    journal = _load_journal(root)
    if journal is None or journal["transaction_id"] != report.get("transaction_id"):
        raise SlimError("slim commit cannot match the durable transaction journal")
    if journal.get("status") != "verified":
        raise SlimError("slim transaction was not verified before commit")
    (root / _JOURNAL_PATH).unlink()
    (root / _LOCK_PATH).unlink()


def rollback_adopter_slim(project_root: Path, report: dict[str, object]) -> None:
    if report.get("status") != "applied":
        return
    _require_supported_platform()
    root = project_root.expanduser().resolve(strict=True)
    _validated_mir_directory(root)
    journal = _load_journal(root)
    if journal is None or journal["transaction_id"] != report.get("transaction_id"):
        raise SlimError("slim rollback cannot match the durable transaction journal")
    errors = _rollback_journal(root, journal)
    if errors:
        raise SlimError("slim rollback incomplete: " + "; ".join(errors))


# @spec FR-001 FR-004
def apply_adopter_slim(
    project_root: Path,
    *,
    external_cli: Path,
    verify: Verify = _default_verify,
    defer_commit: bool = False,
) -> dict[str, object]:
    _require_supported_platform()
    root = project_root.expanduser().resolve(strict=True)
    recover_adopter_slim(root)
    try:
        boundary = load_boundary(root)
        profile = load_profile(root)
    except BoundaryError as exc:
        raise SlimError(str(exc)) from exc
    try:
        _validate_release_controls(root, profile)
    except SlimError:
        if _is_canonical_provider_profile(profile):
            return {"status": "not_applicable", "removed": [], "preserved_modified": []}
        raise
    if is_provider_owner(profile, boundary):
        return {"status": "not_applicable", "removed": [], "preserved_modified": []}

    findings = payload_findings(root, boundary=boundary, profile=profile)
    text_findings = [item["path"] for item in findings if item["kind"] == "text"]
    path_findings = [item["path"] for item in findings if item["kind"] == "path"]
    if text_findings:
        raise SlimError(
            "product contract still contains provider identity markers: " + ", ".join(text_findings)
        )

    cli = _validate_external_cli(root, external_cli)
    payload = _load_payload(root, boundary)
    remove_entries = [
        item
        for item in payload["files"]
        if isinstance(item, dict) and item.get("disposition") == "remove"
    ]
    move_paths: list[Path] = []
    expected_hashes: dict[str, str] = {}
    preserved_modified: list[str] = []
    unsafe_remove: list[str] = []
    for item in remove_entries:
        relative = str(item["path"])
        target = root / relative
        if not target.exists() and not target.is_symlink():
            continue
        if not _is_safe_project_file(root, target):
            preserved_modified.append(relative)
            unsafe_remove.append(relative)
            continue
        if _digest(target) == item["sha256"]:
            move_paths.append(target)
            expected_hashes[relative] = str(item["sha256"])
        else:
            preserved_modified.append(relative)

    if not path_findings:
        if unsafe_remove:
            raise SlimError(
                "remove payload contains unsafe paths: " + ", ".join(sorted(unsafe_remove))
            )
        if move_paths:
            raise SlimError(
                "unchanged remove payload remains without a provider marker: "
                + ", ".join(sorted(path.relative_to(root).as_posix() for path in move_paths))
            )
        verified, detail = verify(cli, root)
        if not verified:
            raise SlimError(f"external CLI already-slim verification failed: {detail}")
        return {
            "status": "already_slim",
            "external_cli": str(cli),
            "removed": [],
            "preserved_modified": sorted(preserved_modified),
            "verification": "ready",
        }

    ephemeral_raw = boundary.get("ephemeral_globs", [])
    if not isinstance(ephemeral_raw, list):
        raise SlimError(f"{BOUNDARY_PATH} ephemeral_globs must be an array")
    ephemeral_globs = [_safe_relative(value) for value in ephemeral_raw]
    move_set = {path.resolve(strict=False) for path in move_paths}
    conflicts: list[str] = []
    for marker in path_findings:
        for path in _marker_files(root, marker):
            relative = path.relative_to(root).as_posix()
            if not _is_safe_project_file(root, path):
                conflicts.append(relative)
            elif path.resolve(strict=False) in move_set:
                continue
            elif _matches_any(relative, ephemeral_globs):
                move_paths.append(path)
                move_set.add(path.resolve(strict=False))
            else:
                conflicts.append(relative)
    if conflicts:
        raise SlimError(
            "provider marker contains preserved content; slim made no changes: "
            + ", ".join(sorted(set(conflicts)))
        )

    _validated_mir_directory(root)
    quarantine_root = _ensure_quarantine_root(root)
    lock_path = root / _LOCK_PATH
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SlimError("another adopter slim transaction is active") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as lock_handle:
        lock_handle.write(str(os.getpid()))
        lock_handle.flush()
        os.fsync(lock_handle.fileno())
    transaction_id = uuid.uuid4().hex
    quarantine = quarantine_root / transaction_id
    moved: list[tuple[Path, Path]] = []
    journal: dict[str, object] = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "pid": os.getpid(),
        "status": "moving",
        "paths": sorted({path.relative_to(root).as_posix() for path in move_paths}),
    }
    try:
        _atomic_fsync_json(root / _JOURNAL_PATH, journal)
        for source in sorted(set(move_paths), key=lambda path: path.as_posix()):
            if not _is_safe_project_file(root, source):
                raise SlimError(
                    "provider path became unsafe before move: "
                    f"{source.relative_to(root).as_posix()}"
                )
            relative = source.relative_to(root)
            expected_hash = expected_hashes.get(relative.as_posix())
            if expected_hash is not None and _digest(source) != expected_hash:
                raise SlimError("provider path changed before move: " + relative.as_posix())
            destination = quarantine / relative
            if destination.exists() or destination.is_symlink():
                raise SlimError(
                    "slim quarantine destination already exists: " + relative.as_posix()
                )
            if not _safe_parent_for_restore(root, destination.parent):
                raise SlimError(
                    "slim quarantine destination parent is unsafe: " + relative.as_posix()
                )
            os.replace(source, destination)
            moved.append((source, destination))
            _prune_empty_parents(source, root)
        remaining = payload_findings(root, boundary=boundary, profile=profile)
        if remaining:
            locations = ", ".join(item["path"] for item in remaining)
            raise SlimError(f"provider boundary remains after slim: {locations}")
        verified, detail = verify(cli, root)
        if not verified:
            raise SlimError(f"external CLI post-slim verification failed: {detail}")
        journal["status"] = "verified"
        _atomic_fsync_json(root / _JOURNAL_PATH, journal)
    except Exception as exc:
        rollback_errors = _rollback_journal(root, journal)
        detail = (
            "rollback complete"
            if not rollback_errors
            else ("rollback incomplete: " + "; ".join(rollback_errors))
        )
        raise SlimError(f"{exc}; {detail}") from exc

    report: dict[str, object] = {
        "status": "applied",
        "transaction_id": transaction_id,
        "external_cli": str(cli),
        "removed": sorted(source.relative_to(root).as_posix() for source, _ in moved),
        "preserved_modified": sorted(preserved_modified),
        "quarantine": quarantine.relative_to(root).as_posix(),
        "verification": "ready",
    }
    if not defer_commit:
        commit_adopter_slim(root, report)
    return report
