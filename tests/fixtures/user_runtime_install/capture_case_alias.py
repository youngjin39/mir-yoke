"""Pinned macOS case-alias oracle; explicit scratch/output, isolated execution."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PIN = "0754c36a1bc5814d793984292aa9be6ae26d3001"
REPO = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert sys.flags.isolated
    source = subprocess.check_output(
        ["git", "show", f"{PIN}:scripts/install_user_runtime_agents.py"], cwd=REPO)
    with tempfile.TemporaryDirectory(dir=args.scratch) as temporary:
        root = Path(temporary).resolve()
        (root / "Probe").mkdir()
        assert (root / "probe").exists(), "requires case-insensitive filesystem"
        provider = root / "provider"
        (provider / "scripts").mkdir(parents=True)
        script = provider / "scripts/install_user_runtime_agents.py"
        script.write_bytes(source)
        (provider / "config").mkdir()
        (provider / "config/capability-sources.json").write_text(json.dumps({
            "agents": {"allowlist": []}, "commands": {"allowlist": {}},
            "profiles": {"packs": {"p": {"agents": [], "commands": []}}},
        }))
        fake = root / "bin"
        fake.mkdir()
        git = fake / "git"
        git.write_text('#!/bin/sh\nif [ "$3" = rev-parse ]; then '
                       'echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; fi\n')
        git.chmod(0o755)
        bootstrap = """
import argparse, hashlib, json, os, stat, subprocess, tempfile, dataclasses, typing, __future__
import importlib.util, pathlib, sys
script = pathlib.Path(sys.argv[1]).resolve()
sys.path[:] = [str(script.parent.parent)]
spec = importlib.util.spec_from_file_location('oracle', script)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
loaded = set(sys.modules)
spec.loader.exec_module(module)
assert pathlib.Path(module.__file__).resolve().is_relative_to(script.parent.parent)
assert all(pathlib.Path(sys.modules[n].__file__).resolve().is_relative_to(script.parent.parent)
           for n in set(sys.modules) - loaded)
if sys.argv[2] == 'helpers':
    root = script.parent.parent
    (root / 'a').mkdir()
    (root / 'b').mkdir()
    (root / 'b/child').write_text('foreign')
    (root / 'denied/home').mkdir(parents=True)
    (root / 'denied').chmod(0)
    results = {}
    for name, call in [('identity_parent', lambda: module.capture_home_identity(root / 'a/../b')),
                       ('cleanup_error', lambda: module.remove_created_directories((root / 'b',))),
                       ('cleanup_stat_error', lambda:
                        module.remove_created_directories((root / 'denied/home',)))]:
        try:
            call()
        except Exception as error:
            results[name] = str(error).replace(str(root), '{ROOT}')
    (root / 'denied').chmod(0o700)
    print(json.dumps(results))
    raise SystemExit(0)
sys.argv = sys.argv[1:]
raise SystemExit(module.main())
"""
        process = subprocess.run(
            [sys.executable, "-I", "-c", bootstrap, str(script), "--apply", "--claude-home",
             str(root / "CaseHome/a/claude"), "--codex-home", str(root / "casehome")],
            cwd=root, env=dict(os.environ, HOME=str(root), PATH=str(fake)),
            capture_output=True, text=True)
        record = {"status": process.returncode, "stdout": process.stdout,
                  "stderr": process.stderr, "residue": (root / "CaseHome").exists()}
        assert record == {"status": 2, "stdout": "", "residue": False,
                          "stderr": "error: --claude-home and --codex-home must not overlap\n"}
        helpers = subprocess.check_output(
            [sys.executable, "-I", "-c", bootstrap, str(script), "helpers"],
            cwd=root, env=dict(os.environ, HOME=str(root), PATH=str(fake)), text=True)
        helpers = json.loads(helpers)
        assert set(helpers) == {"identity_parent", "cleanup_error", "cleanup_stat_error"}
        args.output.write_text(json.dumps({"pin": PIN, "record": record,
                                          "helpers": helpers}, indent=2) + "\n")


if __name__ == "__main__":
    main()
