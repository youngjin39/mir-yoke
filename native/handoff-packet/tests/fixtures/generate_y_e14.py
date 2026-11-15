"""Freeze bootstrap-adoption from 5f8f69f, isolated and without network."""

import json
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

# Reuse only the pinned archive/dependency acquisition, before its wrapper/cases.
scope = {"__file__": __file__}
source = Path(__file__).with_name("generate_y_e13.py").read_text()
exec(source.split("resources =")[0].replace("yaml sqlite_vec", "yaml"), scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
with scope["tarfile"].open( fileobj=scope["io"].BytesIO(
        subprocess.check_output(["git", "archive", scope["pin"], ".claude/hooks/_lib"]) ) ) as tar:
    tar.extractall(root, filter="data")
wrapper = root / "capture.py"
wrapper.write_text( """import sys, pathlib, sysconfig, socket
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
from mir.cli.__main__ import main
from mir.cli import bootstrap_adoption
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
def forbidden(*args, **kwargs):
    raise AssertionError('network forbidden')
socket.socket = forbidden
try:
    code = main(sys.argv[1:])
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    code = 1
raise SystemExit(code)
""".replace("PACKAGE_SET", repr(set(["mir", *packages]))) )
keys = [ "bootstrap_start_gate", "project_profile", "identity_finalize",
    "managed_python_launcher", "content_onboarding", "memory_acceptance", "phase2_spec", ]
profile = ( '[repo]\nslug="sample"\nrepository_type="code_app"\noverlay_archetype="code_app"\n'
    'purpose="Build a calendar"\ntechnology_stack=["Rust"]\n' )
base = dict( schema_version=1, project_slug="sample",
    repository_archetype="code_app", profile="code_app", mir_yoke_source_commit="a" * 40,
    surfaces={ k: dict( disposition="exception", evidence_paths=["evidence.txt"],
            reason="Await owner review", blockers=["Approval pending"], ) for k in keys }, )
cases = [ ("ready", v) for v in [ [], ["--json"], ["--apply", "--json"],
        ["--apply"], ["--apply", "--native-evaluator", "artifact", "--json"], ] ]
cases += [("local", ["--apply", "--native-evaluator", "artifact", "--json"])]
cases += [("missing", v) for v in [[], ["--json"], ["--apply", "--json"]]]
cases += [ (m, ["--apply", "--json"]) for m in [ "malformed", "array", "schema",
        "profile", "surfaces", "escape", "untracked", "gate", "launcher", "content", "memory",
        "phase2", "settings", "receipt-dir", "memory-hit", "memory-miss", "memory-bad", ] ]
for tail in [ ["--help"], ["--he"], ["--help=yes"], ["-hgarbage"],
    ["--bad"], ["--"], ["--project-r=."], ["--j"], ["--apply=yes"], ["--native-e=artifact"],
    ["--project-root"], ["--project-root", "-1"], ["--project-root", "-inf"],
    ["--project-root", "-inf x", "--help"], ["--project-root=./"], ["--json=yes"], ]:
    cases.append(("ready", tail))
records = []
for mode, tail in cases:
    work = root / ("case-" + str(len(records)))
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    manifest = json.loads(json.dumps(base))
    files = { ".mir/repo-profile.toml": profile, "evidence.txt": "Reviewed evidence\n",
        "artifact": "synthetic evaluator\n", ".mir/bootstrap-receipt.json": "old receipt\n", }
    if mode in ["gate", "launcher", "content", "memory", "phase2"] or mode.startswith("memory-"):
        key = ( keys[5] if mode.startswith("memory-") else dict(
                gate=keys[0], launcher=keys[3], content=keys[4], memory=keys[5], phase2=keys[6]
            )[mode] )
        manifest["surfaces"][key] = dict(disposition="applied", evidence_paths=["evidence.txt"])
        if mode.startswith("memory"):
            manifest["surfaces"][key]["queries"] = [
                dict(archive_slug="archive", query="calendar", expected_path="note.txt") ]
    if mode == "schema":
        manifest.update(schema_version=2, extra=True, mir_yoke_source_commit="bad")
    if mode == "surfaces":
        manifest["surfaces"] = {}
    if mode == "profile":
        files[".mir/repo-profile.toml"] = "[other]\n"
    if mode == "escape":
        manifest["surfaces"][keys[1]]["evidence_paths"] = ["../outside.txt"]
    if mode == "settings":
        files[".claude/settings.json"] = "{}"
        manifest["surfaces"][keys[1]]["evidence_paths"] = [".claude/settings.json"]
    if mode != "missing":
        files["config/bootstrap-adoption.json"] = (
            "{" if mode == "malformed" else "[]" if mode == "array" else json.dumps(manifest) )
    for name, body in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    sql = ""
    if mode in ["memory-hit", "memory-miss"]:
        sql = ( "CREATE TABLE external_archives(id,slug,root_path);"
            "CREATE TABLE external_documents(id,archive_id,relative_path);"
            "CREATE TABLE external_chunks(id,document_id);"
            "CREATE VIRTUAL TABLE external_chunks_fts USING fts5(body);"
            "INSERT INTO external_archives VALUES(1,'archive','/synthetic/archive');"
            "INSERT INTO external_documents VALUES(1,1,'note.txt');"
            "INSERT INTO external_chunks VALUES(1,1);"
            "INSERT INTO external_chunks_fts(rowid,body) VALUES(1,'calendar');" )
        if mode == "memory-miss":
            sql += "DELETE FROM external_chunks_fts;"
        with sqlite3.connect(work / ".mir/memory.db") as db:
            db.executescript(sql)
    if mode == "memory-bad":
        (work / ".mir/memory.db").write_bytes(b"bad database")
    if mode == "receipt-dir":
        (work / ".mir/bootstrap-receipt.json").unlink()
        (work / ".mir/bootstrap-receipt.json").mkdir()
    env = dict( HOME=str(work),
        PATH=os.defpath, MIR_CAPABILITY_NATIVE_ARTIFACTS="1" if mode == "local" else "0",
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, )
    subprocess.run(["git", "init", "-q", str(work)], env=env, check=True)
    if mode != "untracked":
        subprocess.run(["git", "-C", str(work), "add", "."], env=env, check=True)
    argv = ["bootstrap-adoption", *tail]
    result = subprocess.run( [scope["sys"].executable, "-I", str(wrapper), *argv],
        cwd=work, env=env, capture_output=True, timeout=20, )
    receipt = work / ".mir/bootstrap-receipt.json"
    records.append( dict( mode=mode, files=files, sql=sql, argv=argv,
            exit=result.returncode, stdout=result.stdout.decode().replace(str(work), "{ROOT}"),
            stderr=re.sub( r"\.bootstrap-receipt\.json\.[^\']+", ".bootstrap-receipt.json.<TEMP>",
                result.stderr.decode().replace(str(work), "{ROOT}"),
            ), receipt=receipt.read_text() if receipt.is_file() else None, ) )
assert records[2]["exit"] == 0 and records[2]["receipt"] != "old receipt\n"
assert records[9]["exit"] == 2 and records[9]["receipt"] == "old receipt\n"
a.output.write_text(json.dumps(records, separators=(",", ":")) + "\n")
