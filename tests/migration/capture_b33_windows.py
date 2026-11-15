"""Offline B33 Windows capture; run with Python 3.12.13 -I -B -S -X utf8.

Prepare with --prepare --repo REPO --bundle NEW; capture with --bundle BUNDLE
--scratch NEW --output FILE. Only synthetic files and pinned sources are read.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

REFERENCE = "33feb31a64082b472ee908b2c7f72d74c946cecc"
GENERATOR = "3c48c47421b3a5487f304e5af220f850d30c3f53"
HARNESS = "tests/test_w2_b33_ontology_check_frozen.py"
COPIES = {"core": "plugins/mir-core/skills/ontology/scripts/ontology_check.py",
          "mcp": "plugins/mir-mcp/ontology/scripts/ontology_check.py"}
PRIVATE = [v for v in (os.environ.get("USERNAME"), Path.home().name) if v]


def prepare(repo, bundle):
    bundle.mkdir(parents=True, exist_ok=False)
    wanted = {(REFERENCE, p) for p in COPIES.values()} | {(GENERATOR, HARNESS)}
    for pin, name in list(wanted):
        for parent in Path(name).parents:
            init = (parent / "__init__.py").as_posix()
            probe = subprocess.run(["git", "show", f"{pin}:{init}"], cwd=repo,
                                   capture_output=True, check=False)
            if probe.returncode == 0:
                wanted.add((pin, init))
    manifest = []
    for pin, name in sorted(wanted):
        raw = subprocess.check_output(["git", "show", f"{pin}:{name}"], cwd=repo)
        target = bundle / pin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        manifest.append(dict(pin=pin, path=name, sha256=hashlib.sha256(raw).hexdigest()))
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="ascii")


def tokenize(value, roots):
    if isinstance(value, (list, tuple)):
        return [tokenize(v, roots) for v in value]
    if isinstance(value, dict):
        return {k: tokenize(v, roots) for k, v in value.items()}
    if isinstance(value, str):
        for root, token in roots:
            aliases = {str(root), root.as_posix()}
            for _ in range(4):
                aliases |= {json.dumps(a)[1:-1] for a in aliases} | {repr(a)[1:-1] for a in aliases}
            for alias in sorted(aliases, key=len, reverse=True):
                value = value.replace(alias, token)
        if os.name == "nt":
            value = value.replace(roots[0][0].drive, "{DRIVE}")
    return value


def privacy(value, record, field="$"):
    if isinstance(value, dict):
        for key, item in value.items():
            privacy(item, record, field + "." + key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            privacy(item, record, f"{field}[{i}]")
    elif isinstance(value, str) and any(v.casefold() in value.casefold() for v in PRIVATE):
        # Never echo the private value or a real pathname, including in tracebacks.
        raise RuntimeError(f"privacy failure record={record} field={field}")


def capture(args):
    assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    bundle, output, scratch = args.bundle.resolve(), args.output.resolve(), args.scratch.resolve()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="ascii"))
    scratch.mkdir(parents=True, exist_ok=False)
    staged = scratch / "sources"
    hashes = {}
    for row in manifest:
        assert row["pin"] in (REFERENCE, GENERATOR)
        raw = (bundle / row["pin"] / row["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"], "source hash mismatch"
        target = staged / row["pin"] / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[target.resolve()] = row["sha256"]
    os.chdir(scratch)
    home, no_bins = scratch / "home", scratch / "no-binaries"
    home.mkdir()
    no_bins.mkdir()
    os.environ.clear()
    os.environ.update(HOME=str(home), USERPROFILE=str(home), PATH=str(no_bins),
                      TMP=str(scratch), TEMP=str(scratch), TMPDIR=str(scratch))
    sys.path[:] = [str(staged)] + [p for p in sys.path if p and "site-packages" not in p]

    def provenance():
        for module in list(sys.modules.values()):
            filename = getattr(module, "__file__", None)
            if not filename or filename.startswith("<"):
                continue
            path = Path(filename).resolve()
            assert (path == Path(__file__).resolve() or
                    (path in hashes and
                     hashlib.sha256(path.read_bytes()).hexdigest() == hashes[path]) or
                    (path.is_relative_to(Path(sys.base_prefix).resolve()) and
                     "site-packages" not in path.parts)), "module provenance violation"

    tree = ast.parse((staged / GENERATOR / HARNESS).read_bytes())
    # Execute the pinned harness through CASES; omit pytest, live load and fixture reads.
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Import) and any(a.name == "pytest" for a in node.names):
            continue
        if isinstance(node, ast.FunctionDef) and node.name == "load":
            continue
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
                                              {"ROOT", "COPIES", "FIXTURE", "M", "RECORDS"}
                                              for t in node.targets):
            continue
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            continue
        selected.append(node)
    records = {}
    provenance()
    with mock.patch("subprocess.run", side_effect=AssertionError("unexpected process")), \
            mock.patch("subprocess.Popen", side_effect=AssertionError("unexpected child")):
        for key, source in COPIES.items():
            path = staged / REFERENCE / source
            spec = importlib.util.spec_from_file_location("b33_" + key, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            provenance()
            spec.loader.exec_module(module)
            ns = {"M": module}
            provenance()
            code = compile(ast.Module(body=selected, type_ignores=[]),
                           str(staged / GENERATOR / HARNESS), "exec")
            exec(code, ns)
            assert len(ns["CASES"]) == 19, "incomplete case inventory"
            records[key] = {}
            for name, case in sorted(ns["CASES"].items()):
                root = scratch / key / name
                root.mkdir(parents=True)
                original_clean = ns["clean"]

                def clean(value, tmp, original=original_clean):
                    # Replace synthetic roots before hashes, including repr/JSON aliases.
                    roots = [(tmp, "<tmp>"), (tmp.parent, "<parent>")]
                    return original(tokenize(value, roots), tmp)

                ns["clean"] = clean
                provenance()
                value = ns["observe"](case, root)
                ns["clean"] = original_clean
                value = tokenize(value, [(root, "<tmp>"), (root.parent, "<parent>"),
                                         (scratch, "{ROOT}"), (bundle, "{BUNDLE}")])
                privacy(value, key + "/" + name)
                records[key][name] = value
            provenance()
    # Sanity witnesses, derived from synthetic inputs rather than native output.
    for key in records:
        for name in ("refs", "refs_codes"):
            assert "value" in records[key][name], "symlink setup failed; enable Windows symlinks"
        assert records[key]["main"]["value"][8]["value"][0] == [{"value": 2}, []]
        assert records[key]["git"]["value"][0]["value"][0] == {"value": ["a.py", "old"]}
    result = dict(reference_pin=REFERENCE, generator_pin=GENERATOR, sources=manifest,
                  platform=sys.platform, python=list(sys.version_info[:3]), records=records,
                  contract="Pinned observe/clean/digest fields; synthetic roots (raw, repr, JSON) "
                  "tokenized before hashes. No separator normalization or raw path hashes. "
                  "StringIO text is application text, not process CRLF framing.")
    privacy(result, "metadata")
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="ascii")
    print("PASS: 38 records; privacy/provenance checked")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-non-windows-smoke", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.repo.resolve(), args.bundle.resolve())
    else:
        assert args.allow_non_windows_smoke or (sys.platform == "win32" and
                                               sys.version_info[:3] == (3, 12, 13))
        capture(args)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        if not str(exc).startswith("privacy failure record="):
            raise
        print(str(exc), file=sys.stderr)
        sys.exit(1)
