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
import typing  # noqa: F401 -- preload reference dependency on newer Python
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
        record("source-null", module.regular_source, base / "null\x00.md")
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
                         "agents", "file", "absent/new.md", ".", "agents/./new.md",
                         "agents//new.md", "agents/new.md/"):
            record(f"target-{relative}", module.safe_target, home, Path(relative))
        record("home-double-anchor", module.require_safe_home, Path("/" + str(home)))
        long_name = "x" * 256
        record("home-long-name", module.require_safe_home, home / long_name)
        record("target-long-name", module.safe_target, home, Path(long_name))
        record("target-long-ancestor", module.safe_target, home, Path(long_name) / "new.md")
        record("source-long-name", module.regular_source, base / long_name)
        blocked = base / "blocked"
        blocked.mkdir()
        blocked.chmod(0)
        try:
            record("home-permission", module.require_safe_home, blocked / "child")
            record("target-permission", module.safe_target, blocked, Path("child"))
            record("target-permission-ancestor", module.safe_target, blocked, Path("child/new.md"))
            record("source-permission", module.regular_source, blocked / "child")
        finally:
            blocked.chmod(0o700)
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
        for name, raw in [
            ("top-list", b"[]"), ("top-null", b"null"), ("invalid-utf8", b"\xff"),
            ("utf16", b"\xff\xfe{\x00}\x00"), ("nan", b"NaN"),
            ("pack-precedence", b'{"agents":{"allowlist":[]},"commands":{"allowlist":{}},'
             b'"profiles":{"packs":{"p":{"agents":[7]}}}}'),
            ("surrogate", b'{"agents":{"allowlist":[]},"commands":{"allowlist":{}},'
             b'"profiles":{"packs":{"p":{"agents":["\\ud800"],"commands":[]}}}}'),
        ]:
            module.CONFIG_PATH.write_bytes(raw)
            record(f"sources-{name}", module.load_sources)
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
        surrogate = ".claude/agents/\ud800.md"
        invalid = {**empty, "agents": {"allowlist": [surrogate]},
                   "profiles": {"packs": {"p": {"agents": [surrogate], "commands": []}}}}
        module.CONFIG_PATH.write_text(json.dumps(invalid))
        module.ROOT = Path("provider")
        record("sources-allowlisted-surrogate", module.load_sources)
        def wire_failure():
            try:
                module.load_sources()
            except Exception as error:
                return {"error": type(error).__name__, "message": str(error).encode(
                    "utf-8", "backslashreplace").decode()}
        surrogate = ".claude/agents/\udc80.md"
        invalid["agents"]["allowlist"] = [surrogate]
        invalid["profiles"]["packs"]["p"]["agents"] = [surrogate]
        module.CONFIG_PATH.write_text(json.dumps(invalid))
        record("sources-surrogateescape-stderr", wire_failure)
        invalid["agents"]["allowlist"] = [".claude/agents/\udcc3\udca9.md"]
        invalid["profiles"]["packs"]["p"]["agents"] = invalid["agents"]["allowlist"]
        module.CONFIG_PATH.write_text(json.dumps(invalid))
        record("sources-surrogateescape-pair-stderr", wire_failure)
        module.ROOT = base
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
        record("receipt-unsorted", module.make_receipt, "claude", "a" * 40, list(reversed(files)))
        record("receipt-ascii", module.make_receipt, "claude", "\x7f😀", [
            module.ManagedFile(".claude/agents/한😀.md", Path("agents/한😀.md"), b"", "0" * 64)])
        # Receipt decisions use explicit synthetic inputs, kept beside each frozen result.
        old = module.sha256_bytes(b"old")
        source = ".claude/agents/z.md"
        entry = {"source": source, "target": "agents/z.md", "sha256": old}
        receipt = {"managed_by": module.MANAGED_BY, "runtime": "claude",
                   "files": {source: entry}}
        cases = []
        def case(name, raw=None, disk=None, selected=True, runtime="claude", op="validate"):
            cases.append((name, {"raw": raw, "disk": disk, "selected": selected,
                                 "runtime": runtime, "op": op}))
        for name, raw in [("missing", None), ("json", "{"), ("list", "[]"),
                          ("null", "null"), ("number", "5"), ("bom", "\ufeff{}"),
                          ("utf8", {"hex": "ff"}), ("utf16", {"hex": "fffe7b007d00"})]:
            case(name, raw, op="load")
        for key, value in [("managed_by", "other"), ("runtime", "codex"),
                           ("files", []), ("files", None)]:
            case("wrong-" + key + str(value), json.dumps({**receipt, key: value}), op="load")
        case("load-valid", json.dumps({**receipt, "schema_version": 99,
                                       "extra": float("nan")}), op="load")
        for name, raw, disk in [("unmanaged", None, "old"), ("identical", None, "agent\r\n"),
                               ("absent", None, None), ("managed", json.dumps(receipt), "old"),
                               ("divergent", json.dumps(receipt), "foreign")]:
            case(name, raw, disk)
        for key, value in [("source", "other"), ("target", "agents/other.md"),
                           ("sha256", "0" * 64)]:
            changed = {**receipt, "files": {source: {**entry, key: value}}}
            case("update-" + key, json.dumps(changed), "old")
        case("update-nondict", json.dumps({**receipt, "files": {source: []}}), "old")
        for name, disk in [("valid", "old"), ("absent", None), ("divergent", "foreign")]:
            case("stale-" + name, json.dumps(receipt), disk, False)
        for key, value in [("source", "other"), ("target", 7), ("target", "../z.md"),
                           ("sha256", 7), ("sha256", "A" * 64), ("sha256", "0" * 63)]:
            changed = {**receipt, "files": {source: {**entry, key: value}}}
            case("stale-" + key + str(value), json.dumps(changed), selected=False)
        case("stale-nondict", json.dumps({**receipt, "files": {source: []}}), selected=False)
        for name in [".claude/agents/한😀.md", ".claude/commands/old.md",
                     ".codex/agents/old.toml", ".claude/agents/../z.md",
                     ".claude/agents/\ud800.md"]:
            target = Path(*Path(name).parts[1:]).as_posix()
            case("stale-name-" + name, json.dumps({**receipt, "files": {
                name: {"source": name, "target": target, "sha256": old}}}), selected=False)
        for depth in [9993, 9994, 9995, 9996, 9997, 9998]:
            case("depth-" + str(depth), json.dumps(receipt)[:-1] + ',"deep":' +
                 '[' * depth + '0' + ']' * depth + '}', op="load")
        for name, op, selected, kind in [("receipt-read-error", "load", True, "receipt"),
                                         ("target-read-error", "validate", True, "target"),
                                         ("stale-read-error", "validate", False, "target")]:
            case(name, json.dumps(receipt), "old", selected, op=op)
            cases[-1][1]["unreadable"] = kind
        case("huge-integer", json.dumps(receipt)[:-1] + ',"x":' + '1' * 4301 + '}', op="load")
        deep = '[' * 9993 + '0' + ']' * 9993
        for name, raw in [("deep-extra", deep + 'x'), ("deep-malformed", '[' + deep + ',]'),
                          ("deep-duplicate", json.dumps(receipt)[:-1] +
                           ',"x":' + deep + ',"x":0}')]:
            case(name, raw, op="load")
        for name, inputs in cases:
            test_home = base / "receipt-home"
            test_home.mkdir(exist_ok=True)
            path = test_home / module.RECEIPT_NAME
            target = test_home / "agents/z.md"
            target.parent.mkdir(exist_ok=True)
            for file in (path, target):
                file.unlink(missing_ok=True)
            if inputs["raw"] is not None:
                raw = inputs["raw"]
                path.write_bytes(bytes.fromhex(raw["hex"]) if isinstance(raw, dict)
                                 else raw.encode())
            if inputs["disk"] is not None:
                target.write_bytes(inputs["disk"].encode())
            def decision(inputs=inputs, test_home=test_home):
                if inputs["op"] == "load":
                    loaded_path, loaded_receipt = module.load_receipt(test_home, inputs["runtime"])
                    return [loaded_path, loaded_receipt is not None]
                return module.validate_targets(test_home, inputs["runtime"],
                                               files[:1] if inputs["selected"] else [])
            unreadable = path if inputs.get("unreadable") == "receipt" else target
            if "unreadable" in inputs:
                unreadable.chmod(0)
            key = "receipt-case-" + name.encode("utf-8", "backslashreplace").decode()
            record(key, decision)
            records[key]["input"] = inputs
            if "unreadable" in inputs:
                unreadable.chmod(0o600)
        identity_home = base / "identity"
        (identity_home / "nested").mkdir(parents=True)
        (base / "identity-other").mkdir()
        (base / "identity-link").symlink_to(identity_home)
        def capture(path):
            identity = module.capture_home_identity(path)
            details = path.lstat()
            return [identity.path, identity.canonical_path,
                    identity.device == details.st_dev, identity.inode == details.st_ino]
        for name in ("identity", "missing", "regular", "identity-link", "identity-link/nested",
                     "null\x00"):
            record("identity-capture-" + name.replace("\x00", "null"), capture, base / name)
        for name, path in [("double", Path("/" + str(identity_home))),
                           ("relative", Path("."))]:
            record("identity-capture-" + name, capture, path)
        def wire_identity(function, *args):
            try:
                return function(*args)
            except Exception as error:
                return {"error": type(error).__name__, "message": str(error).replace(
                    str(base), "{ROOT}").encode(
                    "utf-8", "backslashreplace").decode()}
        bad = base / "bad-\udcff"
        record("identity-bytes-missing", wire_identity, module.capture_home_identity, bad)
        bad_identity = module.HomeIdentity(bad, bad, 0, 0)
        record("identity-bytes-changed", wire_identity, module.verified_target,
               bad_identity, Path("new.md"))
        identity = module.capture_home_identity(identity_home)
        for name in ("identity", "identity/nested", "identity-other"):
            other = module.capture_home_identity(base / name)
            record("identity-overlap-" + name, module.runtime_homes_overlap, identity, other)
            record("identity-overlap-reverse-" + name, module.runtime_homes_overlap,
                   other, identity)
        for relative in ("agents/new.md", ".", "../regular"):
            record("identity-verified-" + relative, module.verified_target,
                   identity, Path(relative))
        identity_home.rename(base / "identity-moved")
        record("identity-verified-missing", module.verified_target, identity, Path("new.md"))
        identity_home.mkdir()
        record("identity-verified-replaced", module.verified_target, identity, Path("new.md"))
        identity_home.rmdir()
        identity_home.symlink_to(base / "identity-moved")
        record("identity-verified-symlink", module.verified_target, identity, Path("new.md"))
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
