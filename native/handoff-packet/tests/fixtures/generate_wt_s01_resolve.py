"""Capture the pinned capability root expression, without importing Mir or a database.

Run with python -I; scratch and output must be explicit. On Windows an optional
--unc-root must name an existing, synthetic share directory owned by the caller.
"""

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

PIN = "a61c3013dc382989c321577bb93dd937d11884fd"


def main():
    assert sys.flags.isolated, "run with python -I"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unc-root", type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.unc_root:
        args.unc_root = args.unc_root.resolve()
    repo = Path(__file__).resolve().parents[4]
    source = subprocess.check_output(
        ["git", "show", f"{PIN}:src/mir/cli/capability.py"], cwd=repo
    )
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    (scratch / "capability.py").write_bytes(source)
    # Preserve the package ancestors too; none of these files is imported.
    for name in ["src/mir/__init__.py", "src/mir/cli/__init__.py"]:
        (scratch / name.replace("/", "_")).write_bytes(
            subprocess.check_output(["git", "show", f"{PIN}:{name}"], cwd=repo)
        )
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                    and n.name == "main")
    assignment = next(n for n in function.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "project_root"
                              for t in n.targets))
    assert ast.unparse(assignment.value) == "namespace.project_root.expanduser().resolve()"
    expression = compile(ast.Expression(assignment.value), "pinned-capability.py", "eval")
    assert not any(n == "mir" or n.startswith("mir.") for n in sys.modules)
    home = scratch / "home"
    home.mkdir()
    os.environ.update(HOME=str(home), USERPROFILE=str(home))
    os.chdir(scratch)
    root = scratch / "project"
    root.mkdir()
    (root / "file").write_text("synthetic")
    if os.name != "nt":
        (root / "dangling").symlink_to("absent")
        (root / "loop").symlink_to("loop")
    roots = [("plain", root)]
    if os.name == "nt":
        roots.append(("verbatim", Path("\\\\?\\" + str(root))))
        if args.unc_root:
            unc = args.unc_root.resolve()
            assert str(unc).startswith("\\\\") and unc.is_dir()
            roots.extend([("unc", unc), ("verbatim-unc", Path("\\\\?\\UNC\\" + str(unc)[2:]))])
    records = []
    for kind, base in roots:
        cases = [("existing", str(base)), ("missing", str(base / "absent" / "tail")),
                 ("parent", str(base / "absent" / ".." / "tail")),
                 ("anchor", base.anchor)]
        if kind in {"plain", "verbatim"}:
            cases.append(("file-parent", str(base / "file" / "child")))
        if kind == "plain" and os.name == "nt":
            cases.append(("slash", str(base).replace("\\", "/")))
        if os.name != "nt":
            cases.extend((name, str(base / name)) for name in ["dangling", "loop"])
        for case, text in cases:
            try:
                result = {"value": str(eval(expression, {"namespace": SimpleNamespace(
                    project_root=Path(text))}))}
            except Exception as exc:
                result = {"class": type(exc).__name__, "message": str(exc)}
            # Observe only path fields, retaining prefixes and all suffixes.
            record = dict(kind=kind, case=case, input=text, **result)
            for key in ["input", "value", "message"]:
                if key in record:
                    record[key] = record[key].replace(str(base), "{ROOT}")
                    record[key] = record[key].replace(str(base).replace("\\", "/"), "{ROOT_SLASH}")
                    if case == "anchor":
                        record[key] = record[key].replace(base.anchor, "{ANCHOR}")
            records.append(record)
    assert records[0]["value"] == "{ROOT}", records[0]
    output = dict(reference_pin=PIN, platform=sys.platform, records=records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
