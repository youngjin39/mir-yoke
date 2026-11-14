"""Capture the pinned console; explicit scratch only, no live package imports."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

PIN = "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"
parser = argparse.ArgumentParser()
parser.add_argument("--scratch", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[4]
root = args.scratch.resolve() / "oracle"
root.mkdir(parents=True, exist_ok=True)
paths = [
    "src/mir/__init__.py", "src/mir/cli/__init__.py", "src/mir/cli/__main__.py",
    "src/mir/cli/loop.py", "tools/autonomous_loop/__init__.py",
    "tools/autonomous_loop/loop.py", "tools/plan_archive/__init__.py",
    "tools/plan_archive/archiver.py",
]
for path in paths:
    target = root / path.removeprefix("src/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(subprocess.check_output(["git", "show", f"{PIN}:{path}"], cwd=repo))
# The detector imports yaml but these CLI routes do not call its yaml functions.
# Copy the dependency itself, rather than admitting the live repository to sys.path.
shutil.copytree(Path(yaml.__file__).parent, root / "yaml", dirs_exist_ok=True)
wrapper = root / "console.py"
wrapper.write_text('''import sys, pathlib, sysconfig, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
# -I ignores PYTHONIOENCODING at startup; restore the console's stream settings.
encoding, _, errors = os.environ['PYTHONIOENCODING'].partition(':')
sys.stdout.reconfigure(encoding=encoding, errors=errors or 'strict')
sys.stderr.reconfigure(encoding=encoding, errors='backslashreplace')
from mir.cli.__main__ import main
import mir.cli.loop
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in {'mir', 'tools', 'yaml'}:
        locations = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in locations), name
try:
    raise SystemExit(main())
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    raise SystemExit(1)
''')
cases = [([], ""), (["--help"], ""), (["-h", "ignored"], ""),
         (["unknown"], ""), (["--"], ""), (["a'b"], ""), (["é"], ""),
         (["loop", "--help"], ""), (["loop"], ""),
         (["loop", "next", "--json"], ""), (["loop", "mark"], ""),
         (["loop", "mark", "--step", "1", "--status", "DONE"], ""),
         (["loop", "next", "--json"], "## Active Task\nStep 1: TODO | brief=é\n"),
         (["loop", "next"], "## Active Task\nStep 1: TODO | brief=é\n"),
         (["loop", "mark", "--step", "1", "--status", "DONE"],
          "## Active Task\nStep 1: TODO brief=é\n")]
if os.name == "posix":
    cases.append(([b"\xff"], ""))
    cases.append((["loop", b"\xff"], ""))
    cases.append((["loop", "mark", "--step", "1", "--status", "DONE", "--reason", b"\xff"],
                  "## Active Task\nStep 1: TODO\n"))
records = []
for index, (argv, plan) in enumerate(cases):
    for encoding in ["utf-8", "ascii:ignore", "ascii:replace",
                     "ascii:backslashreplace", "ascii:strict"]:
        work = root / "work"
        (work / "tasks").mkdir(parents=True, exist_ok=True)
        (work / "tasks/plan.md").write_text(plan)
        env = {"HOME": str(root), "PATH": os.defpath, "PYTHONIOENCODING": encoding}
        proc = subprocess.run([sys.executable, "-I", str(wrapper), *argv], cwd=work,
                              env=env, capture_output=True, check=False)
        assert proc.returncode in {0, 1, 2}, proc.stderr
        if index == 0:
            assert proc.returncode == 2 and proc.stdout.startswith(b"usage: mir ")
        records.append(dict(argv=[os.fsencode(a).hex() for a in argv], encoding=encoding,
                            plan=plan, after=(work / "tasks/plan.md").read_text(),
                            exit=proc.returncode, stdout=proc.stdout.hex(),
                            stderr=proc.stderr.hex()))
args.output.write_text(json.dumps(records, ensure_ascii=True, separators=(",", ":")) + "\n")
