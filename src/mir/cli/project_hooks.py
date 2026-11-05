"""Explicit project-hook supply from metadata shipped in this provider package."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from importlib import resources
from pathlib import Path

from mir.core.capabilities import native

from ._adoption_native import install_project_hooks


def _provider_pin() -> tuple[str, dict]:
    # Never consult a checkout or target capability lock. Wheel bytes are the
    # exact provider resource; publication must populate immutable revision pins.
    metadata = json.loads(
        resources.files("mir").joinpath("resources/project-hooks-provider.json").read_bytes()
    )
    if not isinstance(metadata, dict) or type(metadata.get("schema_version")) is not int:
        raise ValueError("invalid provider metadata")
    if metadata["schema_version"] != 1:
        raise ValueError("unsupported provider metadata schema")
    records = native.validate_artifacts(metadata["native_artifacts"], metadata["plugins"])
    target = native.host_target()
    if target is None:
        raise ValueError("unsupported host")
    if os.environ.get("MIR_CAPABILITY_NATIVE_ARTIFACTS") == "0":
        raise ValueError("native artifacts disabled")
    record = records.get("project-hooks")
    if record is None or target not in record["targets"]:
        raise ValueError("no published host pin in provider package")
    if (
        record["plugin"] != "mir-lifecycle-hooks"
        or record["install_path"] != "bin/project-hooks"
        or not isinstance(metadata.get("provider_revision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", metadata["provider_revision"]) is None
    ):
        raise ValueError("invalid project-hooks provider identity")
    return target, record["targets"][target]


def _path(root: Path, relative: str) -> Path:
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("linked project-hook path")
    return current


def _check(root: Path, relative: str, pin: dict) -> None:
    binary = _path(root, relative)
    receipt = _path(root, ".mir/bin/project-hooks.json")
    expected = {"path": relative, "sha256": pin["sha256"]}
    if json.loads(receipt.read_bytes()) != expected:
        raise ValueError("project-hooks receipt mismatch")
    native._verify(binary, pin)
    if not os.access(binary, os.X_OK):
        raise ValueError("project-hooks is not executable")
    _probe_binary(binary, root)


def _probe_binary(binary: Path, root: Path) -> None:
    result = subprocess.run(
        [str(binary), "capabilities"], stdin=subprocess.DEVNULL,
        capture_output=True, timeout=2, check=False, cwd=root,
    )
    if result.returncode != 0 or not {
        b"mir-project-hooks-v1", b"mir-project-hooks-compact-v1",
    }.issubset(result.stdout.splitlines()):
        raise ValueError("project-hooks capability probe failed")


def _write_receipt(path: Path, pin: dict) -> None:
    data = (json.dumps(pin, indent=2, sort_keys=True) + "\n").encode()
    if path.is_file() and path.read_bytes() == data:
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".project-hooks-", delete=False,
        ) as out:
            temporary = Path(out.name)
            out.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mir project-hooks")
    parser.add_argument("operation", choices=["install", "check"])
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.absolute()
    try:
        if any(parent.is_symlink() for parent in (root, *root.parents)) or not root.is_dir():
            raise ValueError("project root must be an existing directory")
        target, artifact = _provider_pin()
        relative = ".mir/bin/project-hooks" + (".exe" if target.endswith("windows-msvc") else "")
        receipt = _path(root, ".mir/bin/project-hooks.json")
        if receipt.exists() and not receipt.is_file():
            raise ValueError("invalid project-hooks receipt path")
        if args.operation == "install":
            installed = install_project_hooks(root, artifact_pin=artifact)
            if installed is None:
                raise ValueError("verified project-hooks placement unavailable")
            _probe_binary(_path(root, relative), root)
            _write_receipt(receipt, installed)
        _check(root, relative, artifact)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"project-hooks: degraded: {exc}")
        return 1
    print("project-hooks: ready (verified binary, receipt and capability probe)")
    return 0
