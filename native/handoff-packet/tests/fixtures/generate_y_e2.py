"""Acquire pinned console records, with no live repository imports."""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import typing_extensions

PIN = "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"
p = argparse.ArgumentParser()
p.add_argument("--scratch", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--query-bin", type=Path, required=True)
p.add_argument("--fix", action="store_true")
a = p.parse_args()
repo = Path(__file__).resolve().parents[4]
root = a.scratch.resolve() / "oracle"
root.mkdir(parents=True, exist_ok=True)
archive = subprocess.check_output(
    ["git", "archive", PIN, "src/mir", "tools/mir_executor"], cwd=repo
)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(root, filter="data")
# Preserve every package initializer at its pinned spelling.
for path in ["tools/__init__.py"]:
    data = subprocess.run(["git", "show", f"{PIN}:{path}"], cwd=repo, capture_output=True)
    if data.returncode == 0:
        (root / path).write_bytes(data.stdout)
for name in (
    "yaml sqlite_vec jsonschema attrs attr referencing rpds jsonschema_specifications"
).split():
    module = __import__(name)
    shutil.copytree(Path(module.__file__).parent, root / name, dirs_exist_ok=True)
shutil.copy2(typing_extensions.__file__, root / "typing_extensions.py")
provider = root / ".mir/bin"
provider.mkdir(parents=True, exist_ok=True)
shutil.copy2(a.query_bin, provider / "executor-query")
(provider / "executor-query.json").write_text(
    json.dumps(
        {
            "path": ".mir/bin/executor-query",
            "sha256": hashlib.sha256(a.query_bin.read_bytes()).hexdigest(),
        }
    )
)
wrapper = root / "console.py"
wrapper.write_text("""import sys, pathlib, sysconfig
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
from mir.cli.__main__ import main
from mir.cli import policy, runtime_manifest, run_python, migrate
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in {
        'mir', 'tools', 'yaml', 'sqlite_vec', 'jsonschema', 'attrs', 'attr', 'referencing',
        'rpds', 'jsonschema_specifications', 'typing_extensions',
    }:
        locations = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in locations), name
try:
    raise SystemExit(main())
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    raise SystemExit(1)
""")
common = (
    "--runtime-root runtime --manifest runtime/manifest.json --source-url synthetic "
    "--source-commit abc --constraints-sha256 def"
).split()

cases = [
    ["policy"],
    ["policy", "--help"],
    ["policy", "resolve"],
    ["policy", "resolve", "--category", "unit", "--repo-root", "."],
    ["policy", "resolve", "--category", "unit", "--format", "text"],
    ["runtime-manifest"],
    ["runtime-manifest", "--help"],
    ["runtime-manifest", "create", *common],
    ["runtime-manifest", "verify", *common],
    ["run-python", "--help"],
    ["run-python"],
    ["run-python", "--project-root", ".", "--"],
    ["run-python", "--project-root", ".", "--", "-c", "print('extension'); raise SystemExit(7)"],
    ["migrate"],
    ["migrate", "--help"],
    ["migrate", "status", "--db", "memory.db"],
    ["migrate", "up", "--db", "memory.db"],
    ["migrate", "up", "--db", "."],
    ["runtime-manifest", "verify", *common],
    ["migrate", "status", "--db", "memory.db"],
    ["migrate", "up", "--db", "memory.db"],
    ["run-python", "--project-root", ".", "--", "-c"],
    ["run-python", "--project-root", ".", "--", "-m", "missing_synthetic_module"],
    ["run-python", "--project-root", ".", "--", "helper.py"],
    ["migrate", "up", "--db", "helper.py/db.db"],
]
if a.fix:
    cases = [
        ["migrate", "\udcff"],
        ["migrate", "status", "--db", "raw-\udcff.db"],
        ["migrate", "status", "--db=raw-\udcff.db"],
        ["migrate", "literal-\\udcff-\udcff"],
        *[["migrate", "up", "--db", v, "--help"]
          for v in ["-inf", "-1e3", "-NaN", "-1", "-.5", "-1.", "-١", "-1\n"]],
        ["migrate", "up", "-hgarbage"],
        ["migrate", "-hgarbage"],
        ["migrate", "up", "-h=garbage"],
        ["migrate", "status", "--db", "helper.py"],
        ["run-python", "--project-root", ".", "--", "-c",
         "import sys; print('run-python' in sys.orig_argv); "
         "print(sys.orig_argv[-1] == sys.argv[1]); print(sys.argv)", "tail"],
        ["policy", "--help"], ["migrate", "--help"],
        ["migrate", "up", "--db", "-inf", "--help"],
        *[["migrate", "up", "--db", v, "--help"] for v in ["-\U00010d40", "-\U00011f50"]],
    ]
records = []
for i, argv in enumerate(cases):
    work = root / f"case-{i}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    (work / "config").mkdir(exist_ok=True)
    (work / "config/model-routing.lock.json").write_text('{"policy": {}}')
    (work / "runtime").mkdir(exist_ok=True)
    (work / "runtime/data").write_text("payload\n")
    env = {"HOME": str(work), "PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}
    (work / "helper.py").write_text("print('script extension')\n")
    setup = not a.fix and i in {18, 19, 20}
    if setup:
        seed = (
            ["runtime-manifest", "create", *common]
            if i == 18
            else ["migrate", "up", "--db", "memory.db"]
        )
        subprocess.run(
            [sys.executable, "-I", str(wrapper), *seed],
            cwd=work,
            env=env,
            check=True,
            capture_output=True,
        )
    deleted = a.fix and 17 <= i < 20
    def remove_cwd(work=work):
        shutil.rmtree(work)
    result = subprocess.run(
        [sys.executable, "-I", str(wrapper), *argv], cwd=work, env=env, capture_output=True,
        preexec_fn=remove_cwd if deleted else None,
    )
    out, err = result.stdout.decode(), result.stderr.decode()
    assert result.returncode in {0, 1, 2, 7}, (argv, out, err)
    if i == 0 and not a.fix:
        assert result.returncode == 2 and not out and err.startswith("usage: mir policy")
    manifest = work / "runtime/manifest.json"
    if a.fix:
        if i == 16:
            assert (result.returncode, out) == (0, "True\nTrue\n['-c', 'tail']\n")
        if i in {1, 2}:
            assert result.returncode == 1
            assert err == "OperationalError: unable to open database file\n"
            assert not (work / "raw-�.db").exists()
        records.append(dict(argv=[os.fsencode(v).hex() for v in argv], deleted=deleted,
                            exit=result.returncode, stdout=result.stdout.hex(),
                            stderr=result.stderr.hex(),
                            raw_db=(work / "raw-\udcff.db").is_file()))
        continue
    records.append(
        dict(
            setup=setup,
            argv=argv,
            exit=result.returncode,
            stdout=out.replace(str(work), "@ROOT@"),
            stderr=err.replace(str(work), "@ROOT@"),
            manifest=manifest.read_text() if manifest.exists() else None,
        )
    )
a.output.write_text(json.dumps(records, separators=(",", ":")) + "\n")
