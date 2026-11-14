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
cases = [
    (["loop", "next", "--j"], "utf-8", "normal"),
    *[(["loop", "mark", "--step" + suffix, *value, "--status", "DONE"], "utf-8", "normal")
      for suffix, value in [("", ["-1"]), ("=1", []), ("", [" +0_1 "]),
                            ("", ["١"]), ("", ["1__0"]), ("", ["\x1c1"]) ]],
    (["loop", "mark", "--st", "1"], "utf-8", "normal"),
    (["--help"], "cp932", "normal"),
    (["é"], "ascii:namereplace", "normal"),
    *[(["--help"], codec, "normal") for codec in ["utf-16", "utf-32"]],
    (["--help"], "utf-8", "closed"),
    (["loop", "--help"], "utf-8", "deleted"),
    (["--help"], "unknown-codec", "startup"),
    (["loop", "next"], "ascii:namereplace", "normal"),
    (["loop", "next"], "cp932", "normal"),
    (["loop", "next"], "utf-8", "write-closed"),
    (["loop", "next"], "utf-8", "large-closed"),
    (["--help"], "utf-8", "badfd"),
]
records = []
for index, (argv, encoding, mode) in enumerate(cases):
    work = root / f"work-{index}"
    (work / "tasks").mkdir(parents=True, exist_ok=True)
    plan = "## Active Task\nStep 1: TODO | brief=é\n"
    if mode in {"write-closed", "large-closed"}:
        size = 9000 if mode == "write-closed" else 100000
        plan = "## Active Task\nStep 1: TODO | brief=" + "x" * size + "\n"
    (work / "tasks/plan.md").write_text(plan)
    env = {"HOME": str(root), "PATH": os.defpath, "PYTHONIOENCODING": encoding}
    command = [sys.executable, "-I", str(wrapper), *argv]
    setup = None
    if mode == "startup":
        # Startup fails before loading any code; -I would ignore PYTHONIOENCODING.
        command = [sys.executable, "-c", "raise AssertionError('startup must fail')"]
    if mode == "deleted":
        def setup(work=work):
            shutil.rmtree(work)
    if mode == "badfd":
        with (work / "tasks/plan.md").open("rb") as output:
            proc = subprocess.run(command, cwd=work, env=env, stdout=output,
                                  stderr=subprocess.PIPE, check=False)
        stdout = b""
    elif mode in {"closed", "write-closed", "large-closed"}:
        read, write = os.pipe()
        os.close(read)
        proc = subprocess.run(command, cwd=work, env=env, stdout=write,
                              stderr=subprocess.PIPE, check=False)
        os.close(write)
        stdout = b""
    else:
        proc = subprocess.run(command, cwd=work, env=env, capture_output=True,
                              preexec_fn=setup, check=False)
        stdout = proc.stdout
    stderr = proc.stderr.replace(str(root).encode(), b"<ROOT>")
    if mode == "startup":
        # Interpreter version-specific frame addresses are not part of the contract.
        import re
        stderr = re.sub(rb'0x[0-9a-fA-F]+', b'<ADDRESS>', stderr)
    records.append(dict(argv=[os.fsencode(a).hex() for a in argv], encoding=encoding,
                        mode=mode, plan=plan,
                        after=(work / "tasks/plan.md").read_text() if mode != "deleted" else None,
                        exit=proc.returncode,
                        stdout=stdout.hex(), stderr=stderr.hex()))
args.output.write_text(json.dumps(records, ensure_ascii=True, separators=(",", ":")) + "\n")
