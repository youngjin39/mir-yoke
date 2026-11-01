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

_RELATIVE = ".mir/bin/bootstrap-gate"


def install_evaluator(
    root: Path, *, source_root: Path, local_source: Path | None = None,
) -> dict[str, str] | None:
    """Place verified bytes atomically, or preserve shell readiness without a pin.

    Published bytes use the provider's capability-lock verification contract. An
    explicit local build replaces that provenance with an owner-selected file;
    both routes pin the exact installed bytes in the adoption receipt.
    """
    target = native.host_target()
    if (
        target is None
        or target.endswith("windows-msvc")
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
            record = records.get("bootstrap-gate")
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

        destination = root / _RELATIVE
        parent = root
        for part in Path(_RELATIVE).parts[:-1]:
            parent /= part
            if parent.is_symlink():
                return None
            if not parent.exists():
                parent.mkdir()
                created.append(parent)
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            return None
        with tempfile.NamedTemporaryFile(
            prefix=".bootstrap-gate.", dir=parent, delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(data)
        native._verify(temporary, pin)
        temporary.chmod(0o755)
        os.replace(temporary, destination)
        return {"path": _RELATIVE, "sha256": pin["sha256"]}
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
