"""Freeze non-text startup diagnostics and the console's no-dup boundary."""
import sys
import sysconfig
from pathlib import Path

assert sys.flags.isolated and sys.flags.no_site, "run with python -I -S"
assert sys.version_info[:3] == (3, 12, 13), sys.version
stdlib = Path(sysconfig.get_path("stdlib")).resolve()
sys.path[:] = [str(stdlib), str(stdlib / "lib-dynload")]

import argparse  # noqa: E402
import codecs  # noqa: E402
import encodings.aliases  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402

PIN = "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scratch", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[4]
assert args.scratch.is_absolute() and args.output.is_absolute()
root = args.scratch.resolve()
root.mkdir(parents=True, exist_ok=True)
(root / "home").mkdir(exist_ok=True)
for path in ("src/mir/__init__.py", "src/mir/cli/__init__.py", "src/mir/cli/__main__.py"):
    target = root / path.removeprefix("src/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(subprocess.check_output(["git", "show", f"{PIN}:{path}"], cwd=repo))
os.chdir(root)
records = []
candidates = set(encodings.aliases.aliases) | set(encodings.aliases.aliases.values())
candidates.update(p.stem for p in Path(encodings.__file__).parent.glob("*.py"))
for alias in sorted(candidates):
    try:
        info = codecs.lookup(alias)
    except LookupError:
        continue
    if info._is_text_encoding:
        continue
    # -I ignores PYTHONIOENCODING; startup uses -S, synthetic env/cwd and
    # no project imports. The acquisition driver always runs with -I -S.
    proc = subprocess.run([sys.executable, "-S", "-c", "raise AssertionError('startup succeeded')"],
                          env={"HOME": str(root / "home"), "PYTHONIOENCODING": alias},
                          cwd=root, capture_output=True, check=False)
    assert proc.returncode == 1 and not proc.stdout
    assert b"is not a text encoding" in proc.stderr or b"unknown encoding" in proc.stderr
    records.append({"alias": alias, "canonical": info.name, "exit": proc.returncode,
                    "stdout": proc.stdout.hex(),
                    "stderr": re.sub(rb"0x[0-9a-fA-F]+", b"<ADDRESS>", proc.stderr).hex()})
wrapper = root / "probe.py"
wrapper.write_text('''import sys, pathlib, sysconfig, os, resource, json
root = pathlib.Path(__file__).resolve().parent
stdlib = pathlib.Path(sysconfig.get_path("stdlib"))
sys.path[:] = [str(root), str(stdlib), str(stdlib / "lib-dynload")]
from mir.cli.__main__ import main
for name, module in tuple(sys.modules.items()):
    location = getattr(module, "__file__", None)
    if location:
        p = pathlib.Path(location).resolve()
        assert p.is_relative_to(root) or p.is_relative_to(stdlib), (name, p)
resource.setrlimit(resource.RLIMIT_NOFILE, (3, 3))
try:
    os.dup(1)
except OSError as exc:
    print(json.dumps({"dup_error": type(exc).__name__ + ": " + str(exc)}), file=sys.stderr)
else:
    raise AssertionError("dup must fail")
raise SystemExit(main(["--help"]))
''')
proc = subprocess.run([sys.executable, "-I", "-S", str(wrapper)], cwd=root,
                      env={"HOME": str(root / "home")}, capture_output=True, check=False)
assert proc.returncode == 0 and proc.stdout.startswith(b"usage: mir <subcommand>")
dup = json.loads(proc.stderr)
assert dup["dup_error"] == "OSError: [Errno 24] Too many open files"
for name, module in tuple(sys.modules.items()):
    location = getattr(module, "__file__", None)
    if location and name != "__main__":
        assert Path(location).resolve().is_relative_to(stdlib), (name, location)
args.output.write_text(json.dumps({"reference_pin": PIN, "non_text": records,
                                  "no_dup_console": {"exit": proc.returncode,
                                                     "stdout": proc.stdout.hex(), **dup}},
                                 separators=(",", ":")) + "\n")
print(f"captured {len(records)} non-text aliases and exhausted-descriptor console")
