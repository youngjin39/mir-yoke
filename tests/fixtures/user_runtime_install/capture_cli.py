"""Frozen standalone process oracle: python -I capture_cli.py --scratch PATH --output PATH."""
# ruff: noqa: E501 -- compact acquisition rows keep the bounded migration diff reviewable.
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PIN = "0754c36a1bc5814d793984292aa9be6ae26d3001"
REPO = Path(__file__).resolve().parents[3]
CONFIG = {"agents": {"allowlist": [".claude/agents/a.md"]}, "commands": {"allowlist": {}},
          "profiles": {"packs": {"p": {"agents": [".claude/agents/a.md"], "commands": []}}}}
GIT = '''#!/bin/sh
case "$CASE:$3" in
status-fail:status) exit 1;;
dirty:status) echo ' M config/capability-sources.json';;
bad-head:rev-parse) echo invalid;;
head-fail:rev-parse) exit 1;;
*:rev-parse) echo ffffffffffffffffffffffffffffffffffffffff;;
esac
'''
CASES = {
    "help": ["--help"], "short-help": ["-h"], "missing-both": [],
    "missing-codex": ["--claude-home", "{ROOT}/claude"],
    "missing-claude": ["--codex-home", "{ROOT}/codex"],
    "missing-value": ["--claude-home"], "unknown": ["--wat"],
    "ambiguous": ["--c", "x"], "negative": ["--claude-home", "-1", "--codex-home", "{ROOT}/codex"],
    "apply-value": ["--apply=yes"], "short-help-extra": ["-hfoo"], "separator": ["--"],
    "help-ambiguous": ["--help", "--c"], "value-ambiguous": ["--claude-home", "--c"],
    "help-value": ["--help=yes"],
    "unicode-negative": ["--claude-home", "-١", "--codex-home", "{ROOT}/codex"],
    "ambiguous-equals": ["--c=x"], "short-help-equals": ["-hfoo=yes"],
}
VALID = ["--claude-home", "{ROOT}/claude", "--codex-home", "{ROOT}/codex"]
for name in ("dry-run", "apply", "status-fail", "dirty", "bad-head", "head-fail", "unexpected", "apply-mkdir-error", "transaction-error", "broken-stdout", "nonutf"):
    CASES[name] = VALID + (["--apply"] if name in ("apply", "apply-mkdir-error", "transaction-error") else [])
CASES["unknown-valid"] = VALID + ["--wat"]
CASES["separator-valid"] = VALID + ["--"]
CASES["overlap"] = VALID + ["--codex-home", "{ROOT}/claude/nested"]
CASES["root-home"] = VALID + ["--claude-home", "/"]
CASES["abbreviated"] = ["--cla", "{ROOT}/claude", "--cod", "{ROOT}/codex"]
CASES["duplicate"] = VALID + ["--claude-home", "{ROOT}/last", "--apply", "--apply"]
CASES["nonutf"] = ["--claude-home", "{ROOT}/claude{NONUTF}", "--codex-home", "{ROOT}/codex"]
CASES["normalized"] = ["--claude-home", "{ROOT}//claude/./", "--codex-home", "{ROOT}/codex/"]
CASES["missing-git"] = VALID
CASES["nonutf-equals"] = ["--claude-home={ROOT}/claude{NONUTF}", "--codex-home", "{ROOT}/codex"]
CASES["help-broken-stdout"] = ["--help"]
CASES["mixed-anchor"] = ["--claude-home", "/{ROOT}/claude", "--codex-home", "{ROOT}/claude/nested"]
CASES["buffered-report-broken-stdout"] = VALID
CASES["buffered-help-broken-stdout"] = ["--help"]
CASES["apply-nonutf-value"] = ["--apply={NONUTF}"]
for width in (40, 60, 100, 20, 120, 1):
    CASES[f"help-width{width}"] = ["--help"]
WIDTHS = {"help-width-spaces": " 40 ", "help-width-underscore": "1_00", "help-width-unicode": "٤٠"}
CASES.update((name, ["--help"]) for name in WIDTHS)
for prefix in ("", "buffered-"):
    CASES[prefix + "main-broken-stderr"] = ["--claude-home", "relative", "--codex-home", "{ROOT}/codex"]
    CASES[prefix + "parser-broken-stderr"] = []

for name, value in (("short-space", "-h x"), ("unknown", "-x"), ("negative", "-1"),
                    ("separator", "--"), ("dash", "-"), ("space", "a b"), ("unknown-space", "-x x")):
    CASES["fix-value-" + name] = ["--claude-home", value, "--codex-home", "relative"]
for prefix in ("", "buffered-"):
    for route, argv in (("help", ["--help"]), ("dry-run", VALID), ("apply", VALID + ["--apply"])):
        CASES[prefix + "fix-" + route + "-readonly-stdout"] = argv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert sys.flags.isolated
    source = subprocess.check_output(["git", "show", f"{PIN}:scripts/install_user_runtime_agents.py"], cwd=REPO)
    args.scratch.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(dir=args.scratch.resolve()) as temporary:
        for name, argv in CASES.items():
            root = Path(temporary) / name
            for folder in ("provider/scripts", "provider/config", "provider/.claude/agents", "provider/.codex/agents", "bin"):
                (root / folder).mkdir(parents=True)
            provider = root / "provider"
            (provider / "scripts/install_user_runtime_agents.py").write_bytes(source)
            (provider / "config/capability-sources.json").write_bytes(b'\xff' if name == "unexpected" else json.dumps(CONFIG).encode())
            (provider / ".claude/agents/a.md").write_text("agent\n")
            (provider / ".codex/agents/a.toml").write_text("agent = true\n")
            script = GIT
            if name == "apply-mkdir-error":
                script = script.replace('case "$CASE:$3" in', 'if [ "$3" = rev-parse ]; then /usr/bin/touch "$CASE_ROOT/claude"; fi\ncase "$CASE:$3" in')
            if name != "missing-git":
                (root / "bin/git").write_text(script)
                (root / "bin/git").chmod(0o755)
            if name == "transaction-error":
                (root / "claude").mkdir(mode=0o555)
            env = {**os.environ, "HOME": str(root / "home"), "TMPDIR": str(root), "PATH": str(root / "bin"), "CASE": name, "CASE_ROOT": str(root), "PYTHONIOENCODING": "utf-8:strict"}
            env.pop("PYTHONUNBUFFERED", None)
            env["COLUMNS"] = WIDTHS.get(name, name.removeprefix("help-width") if name.startswith("help-width") else "80")
            # Standalone source has no package imports; isolated interpreter cannot load live repo code.
            bootstrap = "import argparse,hashlib,json,os,stat,subprocess,sys,tempfile,dataclasses,typing,textwrap,__future__; from pathlib import Path; p=sys.argv.pop(1); sys.path[:]=[str(Path(p).parent)]; sys.argv[0]='install_user_runtime_agents.py'; before=set(sys.modules); namespace=sys.modules['__main__'].__dict__; namespace['__file__']=p; exec(compile(Path(p).read_bytes().split(b'if __name__ ==')[0],p,'exec'),namespace); assert all(Path(sys.modules[n].__file__).resolve().is_relative_to(Path(p).parent.parent) for n in set(sys.modules)-before); sys.exit(namespace['main']())"
            destination = subprocess.PIPE
            if name.endswith("readonly-stdout"):
                destination = os.open(os.devnull, os.O_RDONLY)
            elif name.endswith("broken-stdout"):
                reader, destination = os.pipe()
                os.close(reader)
            error_destination = subprocess.PIPE
            if name.endswith("broken-stderr"):
                reader, error_destination = os.pipe()
                os.close(reader)
            process = subprocess.Popen([sys.executable, *([] if name.startswith("buffered-") else ["-u"]), "-I", "-c", bootstrap, str(provider / "scripts/install_user_runtime_agents.py"), *[arg.replace("{ROOT}", str(root)).replace("{NONUTF}", "\udcff") for arg in argv]], cwd=root, env=env, stdout=destination, stderr=error_destination)
            if destination != subprocess.PIPE:
                os.close(destination)
            if error_destination != subprocess.PIPE:
                os.close(error_destination)
            stdout, stderr = process.communicate()
            result = subprocess.CompletedProcess([], process.returncode, stdout or b"", stderr or b"")
            if name == "transaction-error":
                (root / "claude").chmod(0o755)
            records.append({"name": name, "argv": argv, "code": result.returncode, "stdout": result.stdout.decode().replace(str(root), "{ROOT}"), "stderr": result.stderr.decode().replace(str(root), "{ROOT}")})
    args.output.write_text("[\n" + ",\n".join(json.dumps(record, ensure_ascii=True, separators=(",", ":")) for record in records) + "\n]\n")


if __name__ == "__main__":
    main()
