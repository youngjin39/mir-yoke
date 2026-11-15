"""Offline WT-CORE-C capture. Prepare on Mac; run with Python -I -S -X utf8.

Sources are Git blobs, not checkout imports. The unused pydantic config import
in memory.py is omitted by AST; every executed function remains unchanged.
PyYAML's pure Python package is bundled with its own file hashes (no install).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

B15 = "98ad7423f84fe7e4ec0e38b63375216faa7966b7"
# First historical generator/fixture revision containing all 53 B15 routes.
B15_SCENARIOS = "aa4fdbdbaa1c9641d5b7594e6c73174a0e0e4315"
B18 = "63efe8cddc6e9c718ec460b9f014523595bd433d"
CASES = tuple(f"parity.fnmatch_{i}" for i in range(23))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(repo, bundle, yaml_root):
    bundle.mkdir(parents=True, exist_ok=False)
    for pin, test, fixture in (
        (B15, "test_w2_b15_render_frozen.py", "b15-render.json"),
        (B18, "test_w2_b18_archive_helpers_frozen.py", "b18-archive-helpers.json"),
    ):
        paths = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", pin, "src/mir"], cwd=repo,
        ).decode().splitlines()
        paths += [f"tests/{test}",
                  f"native/handoff-packet/tests/fixtures/w2/{fixture}"]
        for name in paths:
            target = bundle / pin / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(["git", "show", f"{pin}:{name}"], cwd=repo))
    for name in ("tests/test_w2_b15_render_frozen.py",
                 "native/handoff-packet/tests/fixtures/w2/b15-render.json"):
        target = bundle / B15_SCENARIOS / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(
            ["git", "show", f"{B15_SCENARIOS}:{name}"], cwd=repo))
    for source in yaml_root.glob("*.py"):
        target = bundle / "deps/yaml" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    manifest = {p.relative_to(bundle).as_posix(): digest(p.read_bytes())
                for p in sorted(bundle.rglob("*")) if p.is_file()}
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")


def isolated_module(path, name, generator=False):
    """Load source from bundle, omitting only unreachable dependency imports."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    body = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "mir.core.config.loader":
            continue
        if generator:
            if isinstance(node, ast.Import) and any(a.name == "pytest" for a in node.names):
                continue
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                continue
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in {"RECORDS", "FIXTURE"} for t in node.targets
            ):
                continue
        body.append(node)
    tree.body = body
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def check_modules(bundle):
    for name, module in list(sys.modules.items()):
        if name == "mir" or name.startswith(("mir.", "yaml", "oracle_")):
            assert Path(module.__file__).resolve().is_relative_to(bundle), name


def activate(bundle, pin):
    for name in list(sys.modules):
        if name == "mir" or name.startswith(("mir.", "oracle_")):
            del sys.modules[name]
    sys.path[:] = [str(bundle / pin / "src"), str(bundle / "deps"),
                   *[p for p in sys.path if not Path(p).is_relative_to(bundle)]]


def capture(bundle, scratch, output, check_unix):
    bundle = bundle.resolve()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="ascii"))
    for name, sha in manifest.items():
        assert digest((bundle / name).read_bytes()) == sha, name
    scratch.mkdir(parents=True, exist_ok=False)
    scratch = scratch.resolve()
    home = scratch / "home"
    home.mkdir()
    os.environ.update(HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True
    os.chdir(scratch)

    def audit(event, args):
        if event == "sqlite3.connect":
            assert Path(args[0]).resolve().is_relative_to(scratch), "non-synthetic database"
        if event in {"socket.connect", "socket.bind", "subprocess.Popen"}:
            raise RuntimeError("capture forbids network/process execution")
    sys.addaudithook(audit)
    activate(bundle, B15)
    # Config is unreachable on the B15 render/helper routes. Do not fake it.
    isolated_module(bundle / B15 / "src/mir/cli/memory.py", "mir.cli.memory")
    g15 = isolated_module(
        bundle / B15_SCENARIOS / "tests/test_w2_b15_render_frozen.py", "oracle_b15", True)
    check_modules(bundle)
    fixture_dir = "native/handoff-packet/tests/fixtures/w2"
    expected = json.loads((bundle / B15_SCENARIOS / fixture_dir / "b15-render.json").read_text())
    assert len(g15.CASES) == 53 and g15.CASES.keys() == expected.keys()
    b15 = {}
    for name, case in g15.CASES.items():
        root = scratch / "b15" / name
        root.mkdir(parents=True)
        # Only the observer compaction is suppressed. The pinned scenario still
        # owns setup, ingest, exceptions, CLI calls and teardown for every route.
        with mock.patch.object(g15, "_compact", side_effect=lambda v: v):
            raw = g15.observe(case, root)
        check_modules(bundle)
        if check_unix:
            assert os.name == "posix"
            assert g15._compact(raw) == expected[name], name

        def clean(v, root=root):
            if isinstance(v, str):
                v = v.replace(str(root), "{ROOT}").replace("<tmp>", "{ROOT}")
                return v.replace(root.drive, "{DRIVE}") if root.drive else v
            if isinstance(v, list):
                return [clean(x) for x in v]
            if isinstance(v, dict):
                return {k: clean(x) for k, x in v.items()}
            return v

        # No projection is produced by helpers/early failures; null distinguishes
        # absence from an empty file. Bytes and hashes are never normalized.
        projection = root / ("out/real.md" if name == "cli.in_place"
                             else "out/nested/projection.md")
        file_bytes = projection.read_bytes() if projection.is_file() else None
        b15[name] = {
            "observation": clean(raw),
            "file_hex": file_bytes.hex() if file_bytes is not None else None,
            "byte_length": len(file_bytes) if file_bytes is not None else None,
            "sha256": digest(file_bytes) if file_bytes is not None else None,
            "character_length": (len(file_bytes.decode("utf-8"))
                                 if file_bytes is not None else None),
        }
    assert b15["cli.None.True.True"]["observation"]["value"]["results"] == [{"value": 0}]
    assert b15["cli.None.False.False"]["observation"]["value"]["stderr"] == ""
    assert b15["helpers.empty"]["observation"]["value"]["ingests"] == []
    activate(bundle, B18)
    g18 = isolated_module(
        bundle / B18 / "tests/test_w2_b18_archive_helpers_frozen.py", "oracle_b18", True)
    check_modules(bundle)
    b18 = {name: g18.observe(g18.CASES[name], scratch) for name in CASES}
    check_modules(bundle)
    if check_unix:
        expected = json.loads((bundle / B18 / fixture_dir / "b18-archive-helpers.json").read_text())
        assert all(b18[n] == expected[n] for n in CASES)
    result = {"platform": sys.platform, "python": sys.version.split()[0],
              "pins": {"b15": B15, "b15_scenarios": B15_SCENARIOS, "b18": B18},
              "source_manifest_sha256": digest((bundle / "manifest.json").read_bytes()),
              "b15": b15, "b18": b18,
              "unix_frozen_verified": check_unix}
    text = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    for private in (str(scratch), os.environ.get("USERNAME", "")):
        if private:
            assert private.casefold() not in text.casefold(), "private path/name in capture"
    output.write_text(text, encoding="ascii", newline="\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--repo", type=Path)
    p.add_argument("--yaml-root", type=Path)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--scratch", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--check-unix", action="store_true")
    args = p.parse_args()
    if args.prepare:
        prepare(args.repo, args.bundle, args.yaml_root)
    else:
        capture(args.bundle, args.scratch, args.output.resolve(), args.check_unix)


if __name__ == "__main__":
    main()
