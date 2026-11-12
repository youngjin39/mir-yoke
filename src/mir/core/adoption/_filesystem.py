"""Descriptor-relative mutations below an already canonicalized root."""

from __future__ import annotations

import errno
import os
import stat
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path


@contextmanager
def parent(root: Path, path: Path):
    """Pin every parent without following a substituted symlink."""
    relative = path.relative_to(root)
    if not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise ValueError("mutation path must be below its root")
    # Canonical roots can have mutable ancestors too. Traverse from the anchor.
    flags = getattr(os, "O_SEARCH", getattr(os, "O_PATH", os.O_RDONLY))
    flags |= os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root.anchor, flags)
    try:
        for part in (*root.parts[1:], *relative.parts[:-1]):
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, relative.name
    finally:
        os.close(descriptor)


def replace(root: Path, source: Path, destination: Path) -> None:
    with ExitStack() as stack:
        try:
            src_fd, src = stack.enter_context(parent(root, source))
            dst_fd, dst = stack.enter_context(parent(root, destination))
            # A rename needs parent permissions, not file read permission. lstat at
            # the pinned parent preserves unreadable regular files; rename never
            # follows the final source or destination symlink.
            if not stat.S_ISREG(os.stat(src, dir_fd=src_fd, follow_symlinks=False).st_mode):
                raise OSError("source is not a regular file")
        except OSError as exc:
            raise OSError(
                f"unsafe slim move: {source.relative_to(root).as_posix()} -> "
                f"{destination.relative_to(root).as_posix()}"
            ) from exc
        os.rename(src, dst, src_dir_fd=src_fd, dst_dir_fd=dst_fd)


def mkdir(root: Path, path: Path, mode: int = 0o777) -> None:
    try:
        with parent(root, path) as (descriptor, name):
            os.mkdir(name, mode, dir_fd=descriptor)
    except OSError as exc:
        exc.filename = str(path)
        raise


def unlink(root: Path, path: Path, *, missing_ok: bool = True) -> None:
    try:
        with parent(root, path) as (descriptor, name):
            os.unlink(name, dir_fd=descriptor)
    except FileNotFoundError as exc:
        if not missing_ok:
            exc.filename = str(path)
            raise
    except OSError as exc:
        exc.filename = str(path)
        raise


def temporary(directory: int, name: str, parent_path: Path) -> tuple[int, str]:
    # Reuse mkstemp's eight-character candidates and collision retry contract.
    candidates = tempfile._get_candidate_names()
    for _attempt in range(tempfile.TMP_MAX):
        temporary_name = f".{name}.{next(candidates)}"
        try:
            descriptor = os.open(
                temporary_name,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
        except FileExistsError:
            continue
        except OSError as exc:
            exc.filename = str(parent_path / temporary_name)
            raise
        return descriptor, temporary_name
    raise FileExistsError(errno.EEXIST, "No usable temporary file name found")
