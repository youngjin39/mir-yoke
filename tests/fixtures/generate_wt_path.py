"""Capture isolated WT-PATH reference helpers; run with python -I, no live imports."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import types

PINS = {
    "status": ("84b7b8a33cff26cd782170befa8621a1c65d9744",
               "tools/mir_executor/cli.py", "_resolve_jobs_db"),
    "content": ("273d6c0328fde1db5db0554c1c48a3b4aa86855f",
                "src/mir/cli/bootstrap.py", "_project_relative"),
}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--scratch", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    assert sys.flags.isolated, "invoke with python -I"
    repo, scratch, output = (p.resolve() for p in (args.repo, args.scratch, args.output))
    scratch.mkdir(parents=True, exist_ok=False)
    home = scratch / "home"
    home.mkdir()
    os.environ.update(HOME=str(home), USERPROFILE=str(home))
    os.chdir(scratch)
    references, provenance = {}, {}
    for family, (pin, source, function) in PINS.items():
        raw = subprocess.check_output(["git", "-C", str(repo), "show", f"{pin}:{source}"])
        dest = scratch / family / source
        dest.parent.mkdir(parents=True)
        dest.write_bytes(raw)
        # Preserve every package initializer; selected helpers import no package.
        for parent in pathlib.PurePosixPath(source).parents:
            if str(parent) in (".", "src", "tools"):
                break
            init = str(parent / "__init__.py")
            data = subprocess.check_output(["git", "-C", str(repo), "show", f"{pin}:{init}"])
            (scratch / family / init).write_bytes(data)
        node = next(n for n in ast.parse(raw).body
                    if isinstance(n, ast.FunctionDef) and n.name == function)
        module = types.ModuleType(f"wt_path_{family}")
        module.__file__ = str(dest)
        module.__dict__.update(Path=pathlib.Path, pathlib=pathlib,
                               _DEFAULT_JOBS_DB_RELPATH=pathlib.Path("tasks/jobs.db"))
        references[family] = (module, node, function)
        provenance[family] = {"pin": pin, "source": source, "helper": function,
                              "sha256": hashlib.sha256(raw).hexdigest()}
    assert all(pathlib.Path(m.__file__).is_relative_to(scratch)
               for m, _, _ in references.values())
    for module, node, _ in references.values():
        exec(compile(ast.Module(body=[node], type_ignores=[]), module.__file__, "exec"),
             module.__dict__)
    status = getattr(references["status"][0], references["status"][2])
    content = getattr(references["content"][0], references["content"][2])
    root = scratch / "project"
    (root / "notes").mkdir(parents=True)
    (root / "file").write_text("synthetic", encoding="utf-8")
    outside = scratch / "outside"
    outside.mkdir()
    records = []

    def observe(route, call):
        try:
            value = call()
            records.append({"route": route, "value": value})
        except (OSError, ValueError, RuntimeError) as exc:
            records.append({"route": route, "error": type(exc).__name__,
                            "message": str(exc), "errno": getattr(exc, "errno", None),
                            "winerror": getattr(exc, "winerror", None)})

    for name, path in [("ordinary", root / "notes"), ("missing", root / "missing/leaf"),
                       ("missing_parent", root / "missing/../notes"),
                       ("file_child", root / "file/child"),
                       ("drive_root", pathlib.Path(root.anchor))]:
        observe("status." + name, lambda p=path: str(status(str(p), root)))
    observe("status.default_db", lambda: str(status(None, root)))
    observe("absent_selector.root", lambda: str(root.resolve()))
    for raw in ["notes", "missing/leaf", "missing/../notes", ".", "../outside", str(outside)]:
        observe("content." + raw, lambda r=raw: list(map(str, content(root, r))))
    observe("content.canonical_root", lambda: list(map(str, content(root.resolve(), "notes"))))
    if os.name == "nt":
        verbatim = pathlib.Path("\\\\?\\" + str(root))
        observe("content.verbatim_root", lambda: list(map(str, content(verbatim, "notes"))))
    for name, target in [("alias", root / "notes"), ("escape", outside),
                         ("dangling", root / "missing")]:
        link = root / name
        if os.name == "nt":
            created = subprocess.run(
                ["cmd.exe", "/D", "/C", "mklink", "/J", str(link), str(target)],
                capture_output=True, check=False)
            assert created.returncode == 0, repr(created)
        else:
            link.symlink_to(target, target_is_directory=True)
        observe("readlink." + name, lambda p=link: os.readlink(p))
        observe("status." + name, lambda p=link: str(status(str(p / "leaf"), root)))
        observe("content." + name, lambda n=name: list(map(str, content(root, n))))
    observe("readlink.ordinary", lambda: os.readlink(root / "notes"))
    assert records[0]["value"] == str(root / "notes"), "ordinary resolution sanity"
    assert next(r for r in records if r["route"] == "content.notes")["value"][1] == "notes"
    payload = {"python": sys.version, "platform": sys.platform, "references": provenance,
               "records": records,
               "not_observed": ["access denied", "unsupported reparse tag", "UNC share",
                                "junction cycle", "directory changed during probe"]}
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
