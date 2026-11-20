"""Freeze f10edf21 sweep paths, or compare native dry-runs, using only fake Git.

Use a fresh --scratch; --output captures the reference, --native checks the record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PIN = "f10edf21f5a94db1254eacabfdb06b517f9daeca"
ROOT = Path(__file__).resolve().parents[4]
RECORD = Path(__file__).with_name("executor_sweep_paths.json")
SOURCES = ["tools/mir_executor/" + n for n in (
    "__init__.py", "sweep.py", "jobs.py", "redaction.py", "local_hooks.py",
)]
# Q-LINK investigation launcher: isolated namespace plus module-origin assertions.
CHILD = """
import json, pathlib, sys, types
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
package = types.ModuleType('tools')
package.__path__ = [str(root / 'tools')]
sys.modules['tools'] = package
from tools.mir_executor.sweep import sweep_run_state
for name, module in list(sys.modules.items()):
    if name == 'tools' or name.startswith('tools.'):
        file = getattr(module, '__file__', None)
        paths = [file] if file else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
try:
    # Home is an adapter input: Python resolves it before comparing repository roots.
    pathlib.Path(sys.argv[4]).resolve()
    result = sweep_run_state(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))
except Exception as error:
    print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
    sys.exit(1)
print(json.dumps(result, sort_keys=True))
"""
FAKE_GIT = r"""#!/bin/sh
test "$1" = '-C' || exit 97
shift 2
case "$*" in
  'worktree list --porcelain -z')
    printf 'worktree %s\000branch refs/heads/mir-dispatch/orphan\000\000' "$QLINK_REGISTERED" ;;
  'rev-parse mir-dispatch/orphan') printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n' ;;
  'merge-base --is-ancestor aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa HEAD') exit 0 ;;
  status*) printf '%s' "$QLINK_DIRTY" ;;
  *) echo "unapproved fake git command: $*" >&2; exit 97 ;;
esac
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--native", type=Path)
    args = parser.parse_args()
    scratch = Path(os.path.realpath(args.scratch))
    scratch.mkdir(parents=True)  # Fail on reuse.
    real = scratch / "real"
    for name in ("repo", "orphan", "home", "bin"):
        (real / name).mkdir(parents=True)
    fake = real / "bin/git"
    fake.write_text(FAKE_GIT)
    fake.chmod(0o755)
    aliases = {"real": real}
    if sys.platform == "darwin":
        aliases["data"] = Path("/System", "Volumes", "Data") / real.relative_to("/")
        assert os.path.samefile(aliases["data"], real)
    for count in (1, 8, 40):
        for index in reversed(range(count)):
            (scratch / f"link{count}-{index}").symlink_to(
                "real" if index == count - 1 else f"link{count}-{index + 1}")
        aliases[f"link{count}"] = scratch / f"link{count}-0"
    (real / "cycle").symlink_to("cycle")
    (real / "dangling").symlink_to("future")
    (real / "absolute").symlink_to(real / "orphan")
    cases = {name: (base / "repo", base / "absent.db", base / "repo", base / "orphan")
             for name, base in aliases.items()}
    for field in ("repo", "home", "db"):
        values = [real / "repo", real / "absent.db", real / "repo", real / "orphan"]
        values[{"repo": 0, "db": 1, "home": 2}[field]] = aliases["link40"] / (
            "absent.db" if field == "db" else "repo")
        cases[field + "40"] = tuple(values)
        values = list(cases["real"])
        values[{"repo": 0, "db": 1, "home": 2}[field]] = real / "cycle"
        if field == "db":
            values[1] /= "absent.db"
        cases[field + "-cycle"] = tuple(values)
    cases["missing-db-parent"] = (real / "repo", real / "missing/absent.db",
                                  real / "repo", real / "orphan")
    if "data" in cases:
        cases["data-dirty"] = cases["data"]
    cases["relative"] = (Path("repo"), Path("absent.db"), Path("repo"), Path("orphan"))
    for name, registered in (
        ("registered-cycle", real / "cycle"),
        ("registered-dangling", real / "dangling"),
        ("registered-repeated", aliases["link1"] / "../link1-0/orphan"),
        ("registered-loop-parent", real / "cycle/../dangling"),
        ("registered-absolute", real / "absolute"),
    ):
        cases[name] = (*cases["real"][:3], registered)
    reference, digests = scratch / "reference", {}
    if args.output:
        for name in SOURCES:
            source = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{PIN}:{name}"])
            path = reference / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source)
            digests[name] = hashlib.sha256(source).hexdigest()
    frozen = json.loads(RECORD.read_text()) if args.native else None
    rows, failures = {}, []
    for name, (repo, db, home, registered) in cases.items():
        env = dict(os.environ, HOME=str(real / "home"), TMPDIR=str(real),
                   PATH=str(real / "bin"), QLINK_REGISTERED=str(registered),
                   QLINK_DIRTY="dirty" if name == "data-dirty" else "",
                   PYTHONDONTWRITEBYTECODE="1")
        command = ([str(args.native), "--home-root", str(home), "sweep", "--repo-root",
                    str(repo), "--jobs-db", str(db)] if args.native else
                   [sys.executable, "-I", "-c", CHILD, str(reference),
                    str(repo), str(db), str(home)])
        result = subprocess.run(command, cwd=real, env=env, capture_output=True, text=True)
        value = json.loads(result.stdout) if result.stdout else None
        # terminal_artifacts is a later native surface, outside the pinned shared fields.
        if value is not None:
            value.pop("terminal_artifacts", None)
        row = json.loads(json.dumps(dict(status=result.returncode, result=value,
                                        stderr=result.stderr)).replace(str(scratch), "$ROOT"))
        rows[name] = row
        if frozen and row != frozen["cases"][name]:
            failures.append(name)
            print(name, "expected", frozen["cases"][name], "actual", row)
    assert not list(real.rglob("*.db")), "dry-run created a database"
    if args.output:
        assert rows["real"]["status"] == 0
        assert rows["real"]["result"]["orphan_worktrees"] == ["$ROOT/real/orphan"]
        record = json.dumps(dict(reference_pin=PIN, source_sha256=digests), indent=2)
        body = ",\n".join("    " + json.dumps(k) + ": " + json.dumps(v)
                          for k, v in rows.items())
        body = body.replace("/" + "Volumes/", r"\u002fVolumes/")
        args.output.write_text(record[:-2] + ',\n  "cases": {\n' + body + "\n  }\n}\n")
    assert not failures, failures
    print(f"{len(rows)} path cases passed")


if __name__ == "__main__":
    main()
