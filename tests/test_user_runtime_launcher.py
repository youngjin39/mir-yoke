"""Checkout-bound launcher contracts; executables and homes are synthetic."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install_user_runtime_agents.py"
ERROR = (b"error: checkout-pinned user-runtime-install unavailable or incompatible; "
         b"build and pin it before syncing\n")
pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX launcher")


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "provider"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "scripts" / SCRIPT.name)
    return root


def pin(root, body):
    binary = root / ".mir/bin/user-runtime-install"
    binary.parent.mkdir(parents=True)
    binary.write_text(body)
    binary.chmod(0o755)
    receipt = binary.with_suffix(".json")
    receipt.write_text(json.dumps({"path": ".mir/bin/user-runtime-install",
                                  "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}))
    return binary, receipt


def run(root, *argv, input=b""):
    return subprocess.run([sys.executable, "-I", str(root / "scripts" / SCRIPT.name), *argv],
                          cwd=root, env=dict(os.environ, HOME=str(root)), input=input,
                          capture_output=True)


def test_argv_provider_streams_and_exit(provider):
    pin(provider, f"#!{Path(sys.executable).resolve()}\nimport json,sys\n"
        "print(json.dumps(sys.argv[1:]))\nsys.stdout.flush()\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
        "sys.stderr.buffer.write(b'child stderr\\x00\\n')\nsys.exit(29)\n")
    argv = ["--claude-home", "home with spaces", "--codex-home", "x", "", "--apply",
            "é", os.fsdecode(b"\xff")]
    result = run(provider, *argv, input=b"stdin\x00\xff\n")
    first, rest = result.stdout.split(b"\n", 1)
    assert json.loads(first) == [str(provider.resolve()), *argv]
    assert rest == b"stdin\x00\xff\n"
    assert result.stderr == b"child stderr\x00\n"
    assert result.returncode == 29


@pytest.mark.parametrize("case", ["missing", "no-pin", "digest", "path", "malformed",
                                  "linked", "not-executable", "bad-json", "deep-json",
                                  "pin-link", "ancestor-link", "directory", "exec-error"])
def test_unavailable_never_falls_back(provider, case):
    binary, receipt = pin(provider, "#!/bin/sh\necho SHOULD-NOT-RUN\nexit 0\n")
    if case == "missing":
        binary.unlink()
    elif case == "no-pin":
        receipt.unlink()
    elif case == "digest":
        binary.write_text("#!/bin/sh\necho changed\n")
    elif case == "path":
        receipt.write_text(json.dumps({"path": "/bin/sh", "sha256": "a" * 64}))
    elif case == "malformed":
        receipt.write_text("[]")
    elif case == "bad-json":
        receipt.write_text("{")
    elif case == "deep-json":
        receipt.write_text("[" * 2000 + "0" + "]" * 2000)
    elif case == "pin-link":
        receipt.rename(receipt.with_suffix(".other"))
        receipt.symlink_to(receipt.with_suffix(".other"))
    elif case == "ancestor-link":
        binary.parent.rename(binary.parent.with_name("other"))
        binary.parent.symlink_to(binary.parent.with_name("other"), target_is_directory=True)
    elif case == "directory":
        binary.unlink()
        binary.mkdir()
    elif case == "exec-error":
        binary.write_bytes(b"not an executable\n")
        receipt.write_text(json.dumps({"path": ".mir/bin/user-runtime-install",
                                      "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}))
    elif case == "linked":
        binary.rename(binary.with_suffix(".other"))
        binary.symlink_to(binary.with_suffix(".other"))
    else:
        binary.chmod(0o644)
    result = run(provider, "--help")
    assert (result.returncode, result.stdout, result.stderr) == (3, b"", ERROR)


def test_windows_platform_dispatch(provider):
    code = """
import runpy,sys,types
module = runpy.run_path(sys.argv[1], run_name='installer')
main = module['main']
main.__globals__['os'] = types.SimpleNamespace(name='nt')
def windows(argv):
    assert argv == ['--help', 'extra']
    return 17
main.__globals__['windows_main'] = windows
raise SystemExit(main(['--help', 'extra']))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(provider / "scripts" / SCRIPT.name)],
        cwd=provider, env=dict(os.environ, HOME=str(provider)), capture_output=True)
    assert (result.returncode, result.stdout, result.stderr) == (17, b"", b"")
