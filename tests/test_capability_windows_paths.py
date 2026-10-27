"""Windows path and file behaviours the capability manager must handle natively."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from mir.core.capabilities import manager


def test_should_remove_tree_with_read_only_files_like_windows(tmp_path: Path, monkeypatch) -> None:
    objects = tmp_path / "export" / ".git" / "objects" / "ab"
    objects.mkdir(parents=True)
    packed = objects / "cdef"
    packed.write_bytes(b"blob")
    packed.chmod(0o444)
    real_unlink = os.unlink

    def windows_unlink(path, *args, **kwargs):
        # Windows refuses to delete a read-only file; POSIX would delete it.
        if not os.stat(path, dir_fd=kwargs.get("dir_fd")).st_mode & stat.S_IWRITE:
            raise PermissionError(13, "Access is denied", str(path))
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", windows_unlink)
    manager._rmtree(tmp_path / "export" / ".git")

    assert not (tmp_path / "export" / ".git").exists()


def test_should_read_codex_marketplace_source_without_windows_verbatim_prefix() -> None:
    # Codex for Windows writes local marketplace sources as \\?\C:\... (observed 0.164).
    assert manager._strip_verbatim_prefix("\\\\?\\C:\\Users\\me\\active") == "C:\\Users\\me\\active"
    assert manager._strip_verbatim_prefix("\\\\?\\UNC\\host\\share\\active") == (
        "\\\\host\\share\\active"
    )
    posix = "/" + "srv/mir/active"
    assert manager._strip_verbatim_prefix(posix) == posix
