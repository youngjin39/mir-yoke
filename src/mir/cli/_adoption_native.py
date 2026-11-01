"""Optional lock-verified evaluator placement for an explicitly targeted adoption."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from mir.core.capabilities import native


def install_evaluator(
    root: Path, *, source_root: Path, local_source: Path | None = None,
) -> dict[str, str] | None:
    """Place verified bytes atomically, or preserve shell readiness without a pin.

    Published bytes use the provider's capability-lock verification contract. An
    explicit local build replaces that provenance with an owner-selected file;
    both routes pin the exact installed bytes in the adoption receipt.
    """
    return _install(root, source_root=source_root, local_source=local_source, name="bootstrap-gate")


def install_runtime_verifier(root: Path, *, source_root: Path) -> dict[str, str] | None:
    """Pin the optional project-local runtime verifier from the provider lock."""
    return _install(root, source_root=source_root, name="runtime-verify")


def install_executor_query(root: Path, *, source_root: Path) -> dict[str, str] | None:
    """Pin the optional project-local executor query reader from the provider lock."""
    return _install(root, source_root=source_root, name="executor-query")


def _install(
    root: Path, *, source_root: Path, name: str, local_source: Path | None = None,
) -> dict[str, str] | None:
    target = native.host_target()
    windows = bool(target and target.endswith("windows-msvc"))
    relative = f".mir/bin/{name}" + (".exe" if windows else "")
    if (
        target is None
        or (windows and name == "bootstrap-gate")
        or os.environ.get("MIR_CAPABILITY_NATIVE_ARTIFACTS") == "0"
    ):
        return None
    temporary = None
    created = []
    try:
        if local_source is not None:
            source = local_source.expanduser()
            if source.is_symlink() or not source.is_file():
                return None
            data = source.read_bytes()
            pin = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if not data:
                return None
        else:
            lock_path = source_root / ".mir/capability-lock.json"
            if lock_path.parent.is_symlink() or lock_path.is_symlink():
                return None
            lock = json.loads(lock_path.read_bytes())
            if not isinstance(lock, dict):
                return None
            records = native.validate_artifacts(lock.get("native_artifacts", {}), lock["plugins"])
            record = records.get(name)
            if not record:
                return None
            pin = record["targets"].get(target)
            if pin is None:
                return None
            parsed = urlsplit(pin["url"])
            if parsed.scheme in {"", "file"}:
                source = Path(unquote(parsed.path) if parsed.scheme == "file" else pin["url"])
                if source.is_symlink() or not source.is_file():
                    return None
            data = native._read(pin["url"], pin["size"])

        destination = root / relative
        parent = root
        for part in Path(relative).parts[:-1]:
            parent /= part
            if parent.is_symlink():
                return None
            if not parent.exists():
                parent.mkdir()
                created.append(parent)
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            return None
        with tempfile.NamedTemporaryFile(
            prefix=f".{name}.", dir=parent, delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(data)
        native._verify(temporary, pin)
        temporary.chmod(0o755)
        os.replace(temporary, destination)
        return {"path": relative, "sha256": pin["sha256"]}
    except (OSError, ValueError, KeyError, TypeError, httpx.HTTPError, httpx.InvalidURL):
        return None
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        for parent in reversed(created):
            with suppress(OSError):
                if parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
