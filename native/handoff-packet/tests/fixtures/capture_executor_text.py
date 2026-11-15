"""WT-TEXT: isolated Windows stream capture, before changing any Rust expectations.

Run python -I -X utf8; archives are made by the commands in pc-capture-commands.txt.
Non-Windows mode is a smoke check and must never supply Windows expected bytes.
"""

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile

REFERENCES = {
    "status": ("84b7b8a33cff26cd782170befa8621a1c65d9744",
               "21cdfe9b8d08e2671b9b4311713bc834dd837bb06d26768953a7d516d29b68ca"),
    "sweep": ("f10edf21f5a94db1254eacabfdb06b517f9daeca",
              "514df70e49fa65cca9c247eb05a1a868c278e664f7214f0235ad7147eea6f606"),
}

# This child runs from the synthetic case root, with no live package on sys.path.
CHILD = r'''
import importlib.util, json, pathlib, sys
from functools import partial
from unittest.mock import patch
source, root, route, option = sys.argv[1:]
source, root = pathlib.Path(source), pathlib.Path(root)
sys.path[:] = [str(source)] + [p for p in sys.path if p and
    pathlib.Path(p).resolve().is_relative_to(pathlib.Path(sys.base_prefix).resolve())
    and 'site-packages' not in pathlib.Path(p).parts]
from tools.mir_executor import cli

def check_origins():
    for name, module in list(sys.modules.items()):
        if name == 'tools' or name.startswith('tools.') or name == 'fixture':
            paths = ([module.__file__] if getattr(module, '__file__', None)
                     else list(module.__path__))
            for path in paths:
                if not pathlib.Path(path).resolve().is_relative_to(source):
                    raise RuntimeError('non-isolated import: ' + name)
check_origins()
sys.argv = ['python -m tools.mir_executor']
if route == 'sweep':
    file = source / 'native/handoff-packet/tests/fixtures/generate_executor_sweep.py'
    spec = importlib.util.spec_from_file_location('fixture', file)
    fixture = importlib.util.module_from_spec(spec)
    sys.modules['fixture'] = fixture
    spec.loader.exec_module(fixture)
    check_origins()
    fixture.setup(root, 'artifact')
    args = ['sweep', '--repo-root', str(root / 'repo'), '--jobs-db', str(root / 'jobs.db')]
    if option == 'true':
        args.append('--apply')
    # Freeze the g6 capture date; real sweep functions run (no result stub).
    from tools.mir_executor import sweep
    now = fixture.datetime.datetime.fromisoformat('2026-11-05T17:01:06.467179+00:00')
    with (patch.object(sweep, 'sweep_run_state', partial(sweep.sweep_run_state, now=now)),
          patch.object(sweep, 'sweep_terminal_artifacts',
                       partial(sweep.sweep_terminal_artifacts, now=now))):
        cli.main(args)
else:
    args = ['status', '--job-id']
    if route == 'legacy':
        args = ['status', '--job-id=missing'] + ([option] if option else [])
    try:
        cli.main(args)
    finally:
        check_origins()
check_origins()
'''


def capture(args):
    if not sys.flags.isolated or not sys.flags.utf8_mode:
        raise RuntimeError("python -I -X utf8 is required")
    if os.name != "nt" and not args.allow_non_windows:
        raise RuntimeError("Windows required; non-Windows smoke cannot freeze Windows bytes")
    # A fresh directory avoids following existing links or overwriting user data.
    root = args.scratch.resolve() / "capture"
    root.mkdir(parents=True, exist_ok=False)
    git = pathlib.Path(shutil.which("git")).resolve(strict=True)
    sources = {}
    for kind, (_, digest) in REFERENCES.items():
        archive = (args.archives / (kind + "-reference.tar")).resolve(strict=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise RuntimeError(kind + " archive digest mismatch")
        target = root / (kind + "-reference")
        target.mkdir()
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                if not (member.isfile() or member.isdir()):
                    raise RuntimeError("non-regular archive member")
                if not (target / member.name).resolve().is_relative_to(target):
                    raise RuntimeError("archive path escapes synthetic root")
            bundle.extractall(target, filter="data")
        sources[kind] = target
    records = []
    cases = [("parser", "", "status"), ("legacy", "", "status"),
             ("legacy", "--help", "status"), ("legacy", "--unknown", "status"),
             ("sweep", "false", "sweep"), ("sweep", "true", "sweep")]
    for index, (route, option, kind) in enumerate(cases):
        case = root / (str(index) + "-" + route)
        case.mkdir()
        home, tmp, repo = case / "home", case / "tmp", case / "repo"
        home.mkdir()
        tmp.mkdir()
        repo.mkdir()
        if route == "legacy":
            # A dedicated reference copy prevents contaminating other cases.
            source = repo
            shutil.copytree(sources[kind], source, dirs_exist_ok=True)
            (source / "tools/mir_executor/local.py").write_text(
                "raise AssertionError('must not import')\n", encoding="utf-8")
        else:
            source = sources[kind]
        env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ}
        env.update(HOME=str(home), USERPROFILE=str(home), PATH=str(git.parent),
                   TMP=str(tmp), TEMP=str(tmp), TMPDIR=str(tmp),
                   PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8:strict",
                   MIR_EXECUTOR_ARGPARSE_PROG="python -m tools.mir_executor", COLUMNS="80",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        out = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-c", CHILD,
             str(source), str(repo), route, option],
            cwd=repo, env=env, capture_output=True, timeout=120, check=False)

        def normalized(data):
            text = data.decode("utf-8", "strict")
            text = text.replace(sys.base_prefix, "{ROOT}/python")
            for spelling in (repr(str(root))[1:-1], str(root), root.as_posix()):
                text = text.replace(spelling, "{ROOT}")
            if root.drive:
                text = text.replace(root.drive, "{DRIVE}")
            return text.encode("utf-8").hex()

        if route == "sweep":
            frozen = json.loads((pathlib.Path(__file__).parent / "g6/sweep.json").read_text())
            actual = json.loads(out.stdout)
            if out.returncode != 0 or out.stderr or actual != frozen["cli"][option]["result"]:
                raise RuntimeError(f"unexpected sweep output: {out!r}")
        elif route == "parser":
            if out.returncode != 2 or out.stdout or b"expected one argument" not in out.stderr:
                raise RuntimeError(f"unexpected parser output: {out!r}")
        elif out.returncode != 1 or b"AssertionError: must not import" not in out.stderr:
            raise RuntimeError(f"legacy Python must import its local hook: {out!r}")
        records.append({"route": route, "option": option, "reference_pin": REFERENCES[kind][0],
                        "exit": out.returncode, "stdout_hex": normalized(out.stdout),
                        "stderr_hex": normalized(out.stderr),
                        "jobs_db_created": (repo / "tasks/jobs.db").exists(),
                        "native_gate_covered": route != "legacy"})
    result = {"platform": sys.platform, "python": sys.version.split()[0],
              "references": REFERENCES, "records": records,
              "excluded": ["legacy native-only facade refusal; Python imports local.py",
                           "Windows expectations until this capture runs on Windows"]}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=pathlib.Path, required=True)
    parser.add_argument("--scratch", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-non-windows", action="store_true")
    capture(parser.parse_args())
