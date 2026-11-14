"""Offline acquisition only: run with python -I and an explicit disposable scratch."""

import __future__  # noqa: F401 -- preload the reference language feature module

import argparse
import contextlib
import dataclasses  # Preload the standalone reference's standard-library dependencies.
import hashlib  # noqa: F401 -- preload oracle dependencies before restricting sys.path
import importlib.util
import io
import json
import os
import stat  # noqa: F401 -- preload oracle dependencies before restricting sys.path
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PIN = "0754c36a1bc5814d793984292aa9be6ae26d3001"
SOURCE = "scripts/install_user_runtime_agents.py"
REPO = Path(__file__).resolve().parents[3]
MUTANTS = {
    "parent-path": ('and ".." not in candidate.parts', "and True"),
    "symlink-ancestor": ("if current.is_symlink():", "if False:"),
    "nonregular-source": ("if not stat.S_ISREG(mode):", "if False:"),
    "receipt-sorting": ("sort_keys=True", "sort_keys=False"),
    "receipt-newline": ('+ "\\n").encode()', '+ "").encode()'),
    "claude-required": ('"--claude-home", required=True', '"--claude-home", required=False'),
    "codex-required": ('"--codex-home", required=True', '"--codex-home", required=False'),
}


def acquire(scratch, mutant=None):
    assert sys.flags.isolated, "oracle must run with python -I"
    scratch = scratch.resolve(strict=True)
    source = subprocess.check_output(["git", "show", f"{PIN}:{SOURCE}"], cwd=REPO).decode()
    if mutant:
        before, after = MUTANTS[mutant]
        assert before in source
        source = source.replace(before, after)
    with tempfile.TemporaryDirectory(prefix="oracle-", dir=scratch) as tmp:
        base = Path(tmp).resolve()
        script = base / SOURCE
        script.parent.mkdir()
        script.write_text(source)
        os.chdir(base)
        os.environ["HOME"] = str(base / "home")
        os.environ["TMPDIR"] = str(base)
        sys.path[:] = [str(base)]
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("installer_oracle", script)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        # Standalone script: no package ancestors or repository imports are needed.
        assert Path(module.__file__).resolve().is_relative_to(base)
        loaded = set(sys.modules)
        spec.loader.exec_module(module)
        for name in (set(sys.modules) - loaded) | {spec.name}:
            location = getattr(sys.modules[name], "__file__", None)
            assert location and Path(location).resolve().is_relative_to(base), name
        module.ROOT = base
        module.CONFIG_PATH = base / "config/capability-sources.json"

        def forbidden(*args, **kwargs):
            raise AssertionError("acquisition must never execute delivery or Git source checks")

        for name in ("main", "apply_plan", "apply_transaction", "source_commit"):
            setattr(module, name, forbidden)
        records = {}

        def normalize(value):
            if isinstance(value, bytes):
                return {"hex": value.hex()}
            if isinstance(value, Path):
                return str(value).replace(str(base), "{ROOT}")
            if dataclasses.is_dataclass(value):
                return normalize(dataclasses.asdict(value))
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return [normalize(item) for item in value]
            return value

        def record(name, function, *args, **kwargs):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    value = function(*args, **kwargs)
                    result = {"value": normalize(vars(value) if isinstance(
                        value, argparse.Namespace) else value)}
                except (Exception, SystemExit) as error:
                    result = {"error": type(error).__name__, "message": str(error).replace(
                        str(base), "{ROOT}")}
            result.update(stdout=out.getvalue(), stderr=err.getvalue().replace(
                str(base), "{ROOT}"))
            records[name] = result

        for index, value in enumerate([
            ".claude/agents/a.md", ".claude/agents/../a.md", ".claude/agents/..",
            ".claude/agents//a.md", ".claude/agents/./a.md", "./.claude/agents/a.md",
            "/.claude/agents/a.md", ".claude/agents/nested/a.md", ".claude/agents/a.md/",
            ".claude/agents/한.md", ".claude/agents/.md", ".claude/agents/a.MD", "",
            ".claude/agents/../x.md", ".claude/agents/..md",
        ]):
            # The three-part '..' case uses suffix='' to isolate the traversal guard.
            record(f"relative-{index}", module.is_safe_relative, value,
                   prefix=".claude/agents/", suffix="" if value.endswith("/..") else ".md")
        regular = base / "regular"
        regular.write_bytes(b"source\x00\xff\r\n")
        (base / "directory").mkdir()
        (base / "link").symlink_to(regular)
        (base / "dangling").symlink_to(base / "missing")
        os.mkfifo(base / "fifo")
        for name in ("regular", "missing", "directory", "link", "dangling", "fifo"):
            if mutant == "nonregular-source" and name == "fifo":
                # Avoid a blocking FIFO read while preserving the admission difference.
                with patch.object(Path, "read_bytes", side_effect=OSError("read denied")):
                    record(f"source-{name}", module.regular_source, base / name)
            else:
                record(f"source-{name}", module.regular_source, base / name)
        with patch.object(Path, "read_bytes", side_effect=PermissionError("read denied")):
            record("source-read-error", module.regular_source, regular)
        with patch.object(Path, "lstat", side_effect=PermissionError("stat denied")):
            record("source-stat-error", module.regular_source, regular)
        home = base / "home"
        home.mkdir()
        (home / "agents").mkdir()
        (home / "link").symlink_to(home / "agents")
        (home / "file").write_bytes(b"old")
        (home / "agents/link").symlink_to(home / "file")
        for index, path in enumerate([
            Path("relative"), Path("/"), Path("//"), base / "absent", home,
            home / "agents/../normalized", home / "link/nested", home / "file/nested",
            home / "..",
        ]):
            record(f"home-{index}", module.require_safe_home, path)
        for relative in ("agents/new.md", "link/new.md", "file/new.md", "agents/link",
                         "agents", "file", "absent/new.md"):
            record(f"target-{relative}", module.safe_target, home, Path(relative))
        module.CONFIG_PATH.parent.mkdir()
        empty = {"agents": {"allowlist": []}, "commands": {"allowlist": {}},
                 "profiles": {"packs": {}}}
        module.CONFIG_PATH.write_text(json.dumps(empty))
        record("sources-empty", module.load_sources)
        assert records["sources-empty"]["value"] == [[], []]
        for name, config in [("json", "{"), ("keys", "{}"), ("types", json.dumps({
            **empty, "agents": {"allowlist": {}}})), ("pack", json.dumps({
                **empty, "profiles": {"packs": {"bad": {}}}}))]:
            module.CONFIG_PATH.write_text(config)
            record(f"sources-invalid-{name}", module.load_sources)
        agent, command = ".claude/agents/z.md", ".claude/commands/a.md"
        for relative, content in [(agent, b"agent\r\n"), (command, b"command\n"),
                                  (".codex/agents/z.toml", b"codex\n")]:
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        config = {"agents": {"allowlist": [agent]}, "commands": {"allowlist": {command: {}}},
                  "profiles": {"packs": {"p": {"agents": [agent, agent],
                                               "commands": [command]}}}}
        module.CONFIG_PATH.write_text(json.dumps(config))
        record("sources-valid", module.load_sources)
        for name, pack in [
            ("pack-type", []), ("agent-type", {"agents": [7], "commands": []}),
            ("agent-unlisted", {"agents": ["unlisted"], "commands": []}),
            ("command-type", {"agents": [], "commands": [7]}),
            ("command-unlisted", {"agents": [], "commands": ["unlisted"]}),
        ]:
            invalid = {**config, "profiles": {"packs": {"p": pack}}}
            module.CONFIG_PATH.write_text(json.dumps(invalid))
            record(f"sources-{name}", module.load_sources)
        for kind, path in [("agents", ".claude/agents/../bad.md"),
                           ("commands", ".claude/commands/../bad.md")]:
            invalid = {"agents": {"allowlist": [path] if kind == "agents" else []},
                       "commands": {"allowlist": {path: {}} if kind == "commands" else {}},
                       "profiles": {"packs": {"p": {
                           "agents": [path] if kind == "agents" else [],
                           "commands": [path] if kind == "commands" else []}}}}
            module.CONFIG_PATH.write_text(json.dumps(invalid))
            record(f"sources-unsafe-{kind}", module.load_sources)
        module.CONFIG_PATH.write_text(json.dumps(config))
        (base / ".codex/agents/z.toml").unlink()
        record("sources-missing-codex", module.load_sources)
        module.CONFIG_PATH.unlink()
        record("sources-missing-config", module.load_sources)
        files = [module.ManagedFile(relative, Path(*Path(relative).parts[1:]), content,
                                    module.sha256_bytes(content))
                 for relative, content in [(agent, b"agent\r\n"), (command, b"command\n")]]
        record("hash-empty", module.sha256_bytes, b"")
        record("hash-binary", module.sha256_bytes, bytes(range(256)))
        for runtime, selected in [("claude", files), ("codex", []), ("unicode", [
            module.ManagedFile(".claude/agents/한.md", Path("agents/한.md"), b"", "0" * 64)])]:
            record(f"receipt-{runtime}", module.make_receipt, runtime, "a" * 40, selected)
        valid = ["--claude-home", str(home), "--codex-home", str(base / "codex")]
        # argparse derives its program name from the reference invocation's argv[0].
        sys.argv[0] = str(script)
        for name, argv in [("valid", valid), ("apply", [*valid, "--apply"]), ("empty", []),
                           ("missing-claude", valid[2:]), ("missing-codex", valid[:2]),
                           ("unknown", [*valid, "--wat"]), ("value", ["--claude-home"]),
                           ("normalized", ["--claude-home", "a//./b/", "--codex-home", "/"]),
                           ("abbreviated", ["--claude-h", str(home), "--codex-h", str(home)])]:
            record(f"cli-{name}", module.parse_args, argv)
        return {"pin": PIN, "source": SOURCE, "records": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mutant", choices=MUTANTS)
    args = parser.parse_args()
    output = args.output.resolve()
    result = acquire(args.scratch, args.mutant)
    # One compact record per line keeps the corpus reviewable within the slice budget.
    output.write_text('{"pin": ' + json.dumps(result["pin"]) + ', "source": ' +
                      json.dumps(SOURCE) + ', "records": {\n' + ',\n'.join(
                          json.dumps(key) + ': ' + json.dumps(value, sort_keys=True)
                          for key, value in result["records"].items()) + '\n}}\n')
