"""Capture synthetic manifest records from the fixed Python reference, offline."""

import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PIN = "1324a3c"
SOURCE_REVISION = "4343aba88e811f14f6147a9a9b818b6fb346bec8"
META = [
    "--source-url",
    "https://example.invalid/provider.git",
    "--source-commit",
    "a" * 40,
    "--constraints-sha256",
    "b" * 64,
]
CASES = [
    "plain",
    "replace",
    "unicode",
    "symlink",
    "transient",
    "outside",
    "directory",
    "empty",
    "inside-link",
    "outside-link",
    "dangling-link",
    "nested",
    "normalize",
    "unwritable",
]


def setup(root, case):
    root.mkdir()
    if case != "empty":
        (root / "tool").write_bytes(bytes(range(256)))
        (root / "tool").chmod(0o751)
    manifest = root / "runtime-manifest.json"
    if case == "replace":
        manifest.write_bytes(b"OLD")
        manifest.chmod(0o777)
    if case == "unicode":
        (root / "\ud55c\U0001f600\x7f").write_bytes(b"unicode")
    if case == "symlink":
        (root / "link").symlink_to("absent")
        (root / "folder").mkdir()
        (root / "dirlink").symlink_to("folder")
    if case == "transient":
        (root / "__pycache__").mkdir()
        (root / "__pycache__/x.pyc").write_bytes(b"ignored")
        (root / "x.pyo").write_bytes(b"ignored")
    if case == "outside":
        manifest = root.parent / "outside.json"
    if case == "directory":
        manifest.mkdir()
    if case == "inside-link":
        manifest.symlink_to("actual.json")
    if case == "outside-link":
        (root.parent / "actual.json").write_text("outside")
        manifest.symlink_to("../actual.json")
    if case == "dangling-link":
        manifest.symlink_to("../absent.json")
    if case == "nested":
        manifest = root / "absent/manifest.json"
    if case == "normalize":
        manifest = root / "absent/../runtime-manifest.json"
    if case == "unwritable":
        root.chmod(0o500)
    return manifest


def record(command, root, manifest, env):
    p = subprocess.run(
        [*command, "create", "--runtime-root", str(root), "--manifest", str(manifest), *META],
        capture_output=True,
        env=env,
        timeout=20,
    )
    return {
        "stdout": p.stdout.decode(),
        "stderr": re.sub(
            r"\.runtime-manifest\.json\.[A-Za-z0-9_]{8}\b",
            ".runtime-manifest.json.{TEMP}",
            p.stderr.decode().replace(str(root.parent.resolve()), "{BASE}"),
        ),
        "code": p.returncode,
        "manifest": manifest.read_text() if manifest.is_file() else None,
        "mode": manifest.stat().st_mode & 0o7777 if manifest.is_file() else None,
        "leftovers": sorted(p.name for p in root.glob(".runtime-manifest.json.*")),
    }


def capture():
    with tempfile.TemporaryDirectory(prefix="e02a-capture-") as tmp:
        base = Path(tmp)
        archive = subprocess.check_output(["git", "archive", SOURCE_REVISION, "src/mir"], cwd=ROOT)
        import io

        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(base / "reference", filter="data")
        env = dict(
            os.environ,
            HOME=str(base),
            PYTHONPATH=str(base / "reference/src"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        command = [
            sys.executable,
            "-c",
            "import sys; from mir.cli.runtime_manifest import main; sys.exit(main(sys.argv[1:]))",
        ]
        records = {}
        for case in CASES:
            parent = base / case
            parent.mkdir()
            root = parent / "runtime"
            manifest = setup(root, case)
            records[case] = record(command, root, manifest, env)
        return {"pin": PIN, "records": records}


if __name__ == "__main__":
    Path(__file__).with_name("records.json").write_text(
        json.dumps(capture(), indent=2, ensure_ascii=True) + "\n"
    )
