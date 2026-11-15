"""Offline WT-DEEP capture; run with python -I -X utf8, never a live repo/db."""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PIN = "8c58654"
SOURCES = {
    "handoff": "plugins/mir-lifecycle-hooks/skills/runtime-continuity/scripts/handoff_packet.py",
    "tdd": ".claude/hooks/tdd-matrix-guard.py",
}
# This runs at module level immediately before the original __main__ guard, so
# isolation adds no call frames to the frozen entry point's JSON depth boundary.
ISOLATION = '''
import os
import sysconfig
_root = Path(__file__).resolve().parent
_stdlib = Path(sysconfig.get_path("stdlib")).resolve()
_platstdlib = Path(sysconfig.get_path("platstdlib")).resolve()
_dlls = (Path(sys.base_prefix) / "DLLs").resolve()  # Windows extension modules (e.g. _hashlib.pyd)
for _module in list(sys.modules.values()):
    _file = getattr(_module, "__file__", None)
    if _file:
        _path = Path(_file).resolve()
        assert any(_path.is_relative_to(_d) for _d in (_root, _stdlib, _platstdlib, _dlls)), _path
sys.path[:] = [str(_root)]
if os.environ.get("WT_DEEP_TRACE"):
    def _trace(frame, event, arg):
        if event == "exception" and frame.f_code.co_name in {"main", "load_ledger"}:
            (_root / "exceptions.json").write_text(json.dumps(
                {"class": arg[0].__name__, "message": str(arg[1])}), encoding="utf-8")
        return _trace
    sys.settrace(_trace)
'''


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--bisect", action="store_true",
                        help="Find each consumer's first reference decision change in 0..10000")
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    args.target = args.target.resolve()
    args.output = args.output.resolve()
    root = args.scratch.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "home").mkdir(exist_ok=True)
    project = root / "project"
    (project / "tasks").mkdir(parents=True, exist_ok=True)
    sources = {}
    for consumer, path in SOURCES.items():
        raw = subprocess.check_output(["git", "-C", str(args.repo), "show", f"{PIN}:{path}"])
        assert raw.count(b"if __name__ == '__main__':") + raw.count(
            b'if __name__ == "__main__":'
        ) == 1
        marker = b"if __name__ == "
        offset = raw.rfind(marker)
        oracle = root / f"{consumer}.py"
        oracle.write_bytes(raw[:offset] + ISOLATION.encode() + raw[offset:])
        sources[consumer] = {"pin": f"{PIN}:{path}", "sha256": hashlib.sha256(raw).hexdigest()}
    env = dict(os.environ, HOME=str(root / "home"), USERPROFILE=str(root / "home"),
               PATH="", TMPDIR=str(root), TMP=str(root), TEMP=str(root),
               PYTHONDONTWRITEBYTECODE="1")

    def clean(raw):
        text = raw.decode("utf-8", errors="backslashreplace")
        for path, marker in [(root, "{ROOT}"), (args.repo, "{REPO}"),
                             (Path(sys.base_prefix), "{PYTHON}")]:
            text = text.replace(str(path), marker)
        return re.sub(r"(thread '[^'\r\n]*' \()\d+(\))", r"\g<1>{TID}\2", text)

    def outcome(command, data=b"", trace=False):
        result = subprocess.run(command, input=data, cwd=project,
                                env=dict(env, WT_DEEP_TRACE="1") if trace else env,
                                capture_output=True, check=False, timeout=60)
        stderr = clean(result.stderr)
        final = stderr.splitlines()[-1] if stderr else ""
        return dict(code=result.returncode, stdout=clean(result.stdout), stderr=stderr,
                    final_exception=final if "Error:" in final or "Exit:" in final else None,
                    stdout_base64=base64.b64encode(result.stdout).decode("ascii"))

    records = []
    depths = [0, *range(990, 1001), *range(9990, 10001)]
    prefix = ('{"hook_event_name":"PreToolUse","tool_name":"Bash",'
              '"prompt":"Write a handoff for agent receiver. Do not run any commands. '
              'Owner instruction: no commands.","ignored":')
    suffix = ".exe" if os.name == "nt" else ""

    def capture(consumer, depth, native=True):
        nested = "[" * depth + "0" + "]" * depth
        data = (prefix + nested + "}").encode() if consumer == "handoff" else b""
        argv = [] if consumer == "handoff" else ["prewrite", str(project), "src/a.py"]
        if consumer == "tdd":
            (project / "tasks/tdd.json").write_text(
                '{"changes":[],"metadata":' + nested + "}", encoding="utf-8")
        command = [sys.executable, "-I", "-S", "-X", "utf8",
                   str(root / f"{consumer}.py"), *argv]
        reference = outcome(command, data)
        exception_path = root / "exceptions.json"
        exception_path.unlink(missing_ok=True)
        traced = outcome(command, data, trace=True)
        assert reference == traced, (consumer, depth, reference, traced)
        if exception_path.exists():
            reference["exception"] = json.loads(clean(exception_path.read_bytes()))
        record = dict(consumer=consumer, depth=depth, reference=reference)
        if native:
            binary = "handoff-packet" if consumer == "handoff" else "project-hooks"
            record["native"] = outcome(
                [str(args.target / (binary + suffix)),
                 *([] if consumer == "handoff" else ["tdd-matrix", *argv])], data)
        return record

    for depth in depths:
        for consumer in SOURCES:
            records.append(capture(consumer, depth))
    # Sanity: these inputs demand the owner-command denial / missing TDD entry.
    assert records[0]["reference"]["code"] == 2, records[0]
    assert records[1]["reference"]["code"] == 2, records[1]
    boundaries = []
    if args.bisect:
        for consumer in SOURCES:
            low = capture(consumer, 0, native=False)
            high = capture(consumer, 10000, native=False)
            baseline = low["reference"]
            assert high["reference"] != baseline, ("No transition bracketed", consumer, high)
            probes = [low, high]
            while high["depth"] - low["depth"] > 1:
                mid = capture(consumer, (low["depth"] + high["depth"]) // 2, native=False)
                probes.append(mid)
                if mid["reference"] == baseline:
                    low = mid
                else:
                    high = mid
            # Full adjacent outcomes and all probes; no native boundary is inferred.
            boundaries.append(dict(consumer=consumer, last_baseline=low,
                                   first_changed=high, probes=probes))
    probes = []
    for phase in ["parsed", "converted", "drop-python", "drop-serde"]:
        probe_env = dict(env, WT_DEEP_PHASE=phase)
        matches = list((args.target / "deps").glob("wt_deep-*" + suffix))
        tests = [p for p in matches if p.is_file() and (os.name == "nt" or os.access(p, os.X_OK))]
        assert len(tests) == 1, tests
        result = subprocess.run(
            [str(tests[0]), "--exact", "deep_json_small_stack_probe", "--nocapture"],
            cwd=project, env=probe_env, capture_output=True, check=False, timeout=60)
        probes.append(dict(phase=phase, code=result.returncode,
                           stderr=clean(result.stderr)))
    args.output.write_text(json.dumps(dict(platform=sys.platform, python=sys.version,
                                          sources=sources, records=records, probes=probes,
                                          boundaries=boundaries),
                                      indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
