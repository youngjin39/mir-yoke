"""Optional lock-pinned native artifacts; absent files preserve the reference fallback."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote, urlsplit

import httpx


def host_target(system: str | None = None, machine: str | None = None) -> str | None:
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    arch = {"arm64": "aarch64", "aarch64": "aarch64", "amd64": "x86_64", "x86_64": "x86_64"}.get(
        machine
    )
    suffix = {
        "Darwin": "apple-darwin",
        "Linux": "unknown-linux-gnu",
        "Windows": "pc-windows-msvc",
    }.get(system)
    if not arch or not suffix or (system == "Windows" and arch != "x86_64"):
        return None
    return f"{arch}-{suffix}"


def validate_artifacts(records: object, plugins, *, portable: bool = False) -> dict:
    """Validate the optional section, with stricter source portability for published locks."""
    if not isinstance(records, dict):
        raise ValueError("native artifacts must be an object")
    paths = set()
    for name, record in records.items():
        if not isinstance(name, str) or not name or not isinstance(record, dict):
            raise ValueError("invalid native artifact entry")
        if set(record) != {"plugin", "install_path", "targets"}:
            raise ValueError("invalid native artifact fields")
        plugin, path = record["plugin"], record["install_path"]
        if not isinstance(plugin, str) or plugin not in plugins:
            raise ValueError("native artifact plugin is unknown")
        if (
            not isinstance(path, str)
            or not path
            or "\\" in path
            or PureWindowsPath(path).drive
            or PurePosixPath(path).is_absolute()
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or path.endswith(".exe")
        ):
            raise ValueError("unsafe native artifact install_path")
        key = (plugin, path)
        if any(
            p == plugin and (s == path or s.startswith(path + "/") or path.startswith(s + "/"))
            for p, s in paths
        ):
            raise ValueError("overlapping native artifact install paths")
        paths.add(key)
        if not isinstance(record["targets"], dict):
            raise ValueError("native artifact targets must be an object")
        for target, pin in record["targets"].items():
            if (
                not isinstance(target, str)
                or not isinstance(pin, dict)
                or set(pin) != {"url", "sha256", "size"}
                or not isinstance(pin["url"], str)
                or not pin["url"]
                or not isinstance(pin["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) is None
                or type(pin["size"]) is not int
                or pin["size"] < 1
            ):
                raise ValueError("invalid native artifact target pin")
            url = pin["url"]
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"", "file", "http", "https"}
                and not PureWindowsPath(url).drive
            ):
                raise ValueError("unsupported native artifact URL")
            if portable and (
                parsed.scheme == "file"
                or PurePosixPath(url).is_absolute()
                or PureWindowsPath(url).drive
                or "\\" in url
            ):
                raise ValueError("native artifact source is not portable")
    return records


def _entries(plugin, records, target):
    for name, record in records.items():
        if record["plugin"] == plugin:
            path = record["install_path"]
            if target and target.endswith("windows-msvc"):
                path += ".exe"
            yield name, path, record["targets"].get(target)


def _verify(path, pin):
    if (
        pin is None
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != pin["size"]
        or hashlib.sha256(path.read_bytes()).hexdigest() != pin["sha256"]
    ):
        raise ValueError(f"native artifact integrity mismatch: {path.name}")


def _read(url, size):
    parsed = urlsplit(url)
    if parsed.scheme in {"http", "https"}:
        with httpx.stream("GET", url, timeout=30, follow_redirects=True) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes(chunk_size=min(size + 1, 65536)):
                if len(data) + len(chunk) > size:
                    raise ValueError("native artifact exceeds recorded size")
                data.extend(chunk)
            return bytes(data)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            raise ValueError("native artifact file URL must be local")
        path = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
    else:
        path = url
    with open(path, "rb") as source:
        return source.read(size + 1)


def place_artifacts(root: Path, plugin: str, records: dict, *, target=None) -> None:
    if os.environ.get("MIR_CAPABILITY_NATIVE_ARTIFACTS") != "1":
        return
    target = target or host_target()
    if target is None:
        return
    for name, relative, pin in _entries(plugin, records, target):
        temporary = None
        created = []
        try:
            if pin is None:
                raise ValueError(f"no target {target}")
            destination = root / relative
            if destination.exists() or destination.is_symlink():
                raise ValueError("install path already exists")
            parent = root
            for part in PurePosixPath(relative).parts[:-1]:
                parent /= part
                if parent.is_symlink():
                    raise ValueError("linked native artifact parent")
                if not parent.exists():
                    parent.mkdir()
                    created.append(parent)
            data = _read(pin["url"], pin["size"])
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
            _verify(temporary, pin)
            temporary.chmod(0o755)
            os.replace(temporary, destination)
        except (OSError, ValueError, httpx.HTTPError, httpx.InvalidURL) as exc:
            print(
                f"Warning: native artifact {name} skipped: {exc}; using Python reference",
                file=sys.stderr,
            )
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            for parent in reversed(created):
                if not any(parent.iterdir()):
                    parent.rmdir()


@contextmanager
def source_tree(root: Path, plugin: str, records: dict, *, target=None):
    """Verify present artifacts, then expose the original strict source-tree view.

    Only declared files are removed. Ancestors are pruned only when empty, so every
    undeclared file/directory still participates in the original tree validation.
    """
    if root.is_symlink():
        raise ValueError("native artifact root is linked")
    target = target or host_target()
    present = []
    for _, relative, pin in _entries(plugin, records, target):
        path = root
        for part in PurePosixPath(relative).parts:
            path /= part
            if path.is_symlink():
                raise ValueError("native artifact path is linked")
        if path.exists():
            _verify(path, pin)
            present.append(relative)
    if not present:
        yield root
        return
    # Keep symlinks as links: the strict source validator must still reject them.
    with tempfile.TemporaryDirectory(prefix="native-check-") as temporary:
        view = Path(temporary) / "source"
        shutil.copytree(root, view, symlinks=True)
        for relative in present:
            path = view / relative
            path.unlink()
            parent = path.parent
            while parent != view and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        yield view
