"""Pinned E02 oracle: Windows CPython 3.12.13 -I, offline and synthetic roots only."""
import __future__  # noqa: F401 -- preload pinned dependencies before isolation

import argparse
import contextlib
import hashlib
import io
import json
import locale
import os
import platform
import re  # noqa: F401 -- pinned dependency
import shutil  # noqa: F401 -- pinned dependency
import subprocess
import sys
import tempfile
import urllib.parse  # noqa: F401 -- pinned dependency
from functools import partial
from importlib import resources, util  # noqa: F401 -- preload pinned resources import
from pathlib import Path

PIN = "ba6aa95673deefcb5f418b3fe9f3007f9b22e62a"
GENERATOR = Path(__file__).resolve()
LEAVES = ("mir.core.capabilities.native", "mir.cli._adoption_native", "mir.cli.project_hooks")
PACKAGES = ("mir", "mir.core", "mir.core.capabilities", "mir.cli")
TARGET = "x86_64-pc-windows-msvc"
def audit(root):
    stdlib = Path(sys.base_prefix).resolve()
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename or filename.startswith("<"):
            continue
        path = Path(filename).resolve()
        if path == GENERATOR or path.is_relative_to(root):
            continue
        if path.is_relative_to(stdlib) and not {
            "site-packages", "dist-packages"
        }.intersection(path.parts) and name.partition(".")[0] in sys.stdlib_module_names:
            continue
        raise RuntimeError(f"non-isolated import: {name}: {path}")
def capture(repo, scratch):
    run = Path(tempfile.mkdtemp(prefix="e02-windows-", dir=scratch)).resolve()
    provider = run / "provider"
    hashes = {}
    for name in (*PACKAGES, *LEAVES):
        relative = "src/" + name.replace(".", "/")
        relative += "/__init__.py" if name in PACKAGES else ".py"
        data = subprocess.run(["git", "-C", str(repo), "show", f"{PIN}:{relative}"],
                              check=True, capture_output=True).stdout
        path = provider / relative.removeprefix("src/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    (provider / "httpx.py").write_text(
        "class HTTPError(Exception): pass\nclass InvalidURL(Exception): pass\n"
        "def stream(*a, **k): raise RuntimeError('network forbidden')\n", encoding="utf-8")
    payload = GENERATOR.with_name("probe.exe").read_bytes()
    source = run / "probe.exe"
    source.write_bytes(payload)
    rust = subprocess.check_output(["rustc", "--version"]).decode().strip()
    system = platform.platform()
    for name in list(os.environ):
        if name.startswith("MIR"):
            del os.environ[name]
    for name, folder in (("HOME", "home"), ("USERPROFILE", "home"), ("TMP", "temp"),
                         ("TEMP", "temp"), ("TMPDIR", "temp")):
        (run / folder).mkdir(exist_ok=True)
        os.environ[name] = str(run / folder)
    tempfile.tempdir = str(run / "temp")
    os.chdir(run)
    sys.path[:] = [str(provider)]
    for name in (*PACKAGES, *LEAVES):
        path = provider / name.replace(".", "/")
        path = path / "__init__.py" if name in PACKAGES else path.with_suffix(".py")
        spec = util.spec_from_file_location(name, path)
        module = util.module_from_spec(spec)
        sys.modules[name] = module
        if "." in name:
            parent, attribute = name.rsplit(".", 1)
            setattr(sys.modules[parent], attribute, module)
        if name in LEAVES:
            audit(run)
            spec.loader.exec_module(module)
    native, adoption, hooks = (sys.modules[name] for name in LEAVES)
    assert native.host_target() == TARGET, native.host_target()
    records = {}
    def tree(root):
        return {p.relative_to(root).as_posix(): {
            "directory": p.is_dir(), "attributes": p.lstat().st_file_attributes,
            "mode": p.lstat().st_mode & 0o777,
            "hex": None if p.is_dir() else p.read_bytes().hex()}
            for p in sorted(root.rglob("*"))}
    temporary_names = []
    original = tempfile.NamedTemporaryFile
    def named(*args, **kwargs):
        result = original(*args, **kwargs)
        temporary_names.append((result.name, kwargs.get("prefix", "tmp")))
        return result
    tempfile.NamedTemporaryFile = named
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if not isinstance(value, str):
            return value
        text = value
        for i, (name, prefix) in enumerate(temporary_names):
            token = str(Path(name).with_name(f"{prefix}{{TEMP-{i}}}"))
            text = text.replace(name.replace("\\", "\\\\"), token.replace("\\", "\\\\"))
            text = text.replace(name, token)
        text = text.replace(str(run).replace("\\", "\\\\"), "{ROOT}").replace(str(run), "{ROOT}")
        text = text.replace(run.drive, "{DRIVE}")
        return text
    def record(key, root, function):
        out, err, error, value = io.StringIO(), io.StringIO(), None, None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                value = function()
                audit(run)
            except (OSError, ValueError) as exc:
                error = {k: getattr(exc, k, None) for k in
                         ("errno", "winerror", "strerror", "filename", "filename2")}
                error.update({"class": type(exc).__name__, "rendered": str(exc)})
        records[key] = clean({"value": value, "error": error, "stdout": out.getvalue(),
                              "stderr": err.getvalue(), "tree": tree(root)})
    def root(key):
        path = run / key
        path.mkdir()
        return path
    digest = hashlib.sha256(payload).hexdigest()
    for name in ("bootstrap-gate", "project-hooks"):
        project = root(f"{name}-valid")
        pin = {"url": str(source), "size": len(payload), "sha256": digest}
        record(f"install:{name}:valid", project,
               partial(adoption._install, project, source_root=None, name=name, artifact_pin=pin))
    pin = {"path": ".mir/bin/project-hooks.exe", "sha256": digest}
    for mode in ("valid", "readonly"):
        project = root(f"receipt-{mode}")
        path = project / "receipt.json"
        if mode == "readonly":
            path.write_bytes(b"old")
            path.chmod(0o444)
        record(f"receipt:{mode}", project, partial(hooks._write_receipt, path, pin))
        if mode == "readonly":
            path.chmod(0o644)
    project = root("probe")
    hooks._probe_binary(source, project)
    output = subprocess.run([str(source), "capabilities"], check=True, capture_output=True)
    assert output.stdout == b"mir-project-hooks-v1\r\nmir-project-hooks-compact-v1\r\n", output
    assert output.stderr == b"", output
    records["probe:bytes"] = {"code": output.returncode, "stdout_hex": output.stdout.hex(),
                              "stderr_hex": output.stderr.hex()}
    for mode in ("valid", "metadata-exists"):
        project = root(f"placement-{mode}")
        if mode != "valid":
            (project / "bin").mkdir()
            (project / "bin/native-artifacts.json").write_bytes(b"old")
        entries = {"mir-mcp": {"plugin": "mir-mcp", "install_path": "bin/mir-mcp", "targets": {
            TARGET: {"url": str(source), "size": len(payload), "sha256": digest}}}}
        record(f"placement:{mode}", project,
               partial(native.place_artifacts, project, "mir-mcp", entries, target=TARGET))
    audit(run)
    return {"manifest": {"reference_pin": PIN, "sources": hashes, "python": sys.version,
                         "rust": rust, "os": system, "locale": locale.setlocale(0),
                         "generator_sha256": hashlib.sha256(GENERATOR.read_bytes()).hexdigest(),
                         "pe_sha256": digest, "pe_size": len(payload)},
            "records": records}
def main():
    if os.name != "nt" or sys.version_info[:3] != (3, 12, 13) or not sys.flags.isolated:
        raise SystemExit("Requires Windows CPython 3.12.13 with -I; no records written")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo, scratch, output = GENERATOR.parents[3], args.scratch.resolve(), args.output.resolve()
    if (scratch.is_relative_to(repo) or repo.is_relative_to(scratch)
            or not output.is_relative_to(scratch)):
        parser.error("scratch and repo must be separate; output must be under scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    result = capture(repo, scratch)
    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    assert not re.search(r"[A-Za-z]:[\\/]|" + re.escape(os.environ["USERNAME"]), text)
    output.write_text(text, encoding="utf-8", newline="\n")
if __name__ == "__main__":
    main()
