"""Freeze result with the shared pinned status oracle machinery."""
import importlib.util
import sqlite3
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "result_oracle_support", Path(__file__).with_name("generate_executor_status.py"))
SUPPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPPORT)
SUPPORT.PIN = "3cd0588da4fbfc894bfd5c9a969ece58a60972da"
SUPPORT.OUTPUT = Path(__file__).with_name("executor_result.json")
SUPPORT.BASE_ARGV = ["result", "--job-id", "fixture"]
SUPPORT.SELECTORS = (*SUPPORT.SELECTORS, "MIR_EXECUTOR_RESULT_IMPL")
CASES = [case for case in SUPPORT.cases()
         if not case["name"].startswith("leading-") or "space" not in case["name"]]
for case in CASES:
    if "argv" in case:
        case["argv"] = ["result" if arg == "status" else arg for arg in case["argv"]]
for column, values in (
    ("status", ["running", "failed", "cancelled", "queued", "", {"bytes": "72756e6e696e67"}]),
    ("stdout", ["x" * 499 + "\U0001f600tail", {"bytes": "ff00" * 260}, 7]),
    ("stderr", ["x" * 501, {"bytes": "ff00" * 260}, 7]),
    ("dispatch_brief_path", ["<HOME>/missing.json", "<HOME>/tasks/jobs.db", "bad-\u754c", None]),
    ("exit_code", [0, 1, -9, "bad", {"bytes": "ff"}]),
    ("duration_seconds", [0.0, 1.23456789, float("inf"), "bad"]),
):
    for index, value in enumerate(values):
        CASES.append({"name": f"result-{column}-{index}", "update": [column, value]})
for codec in ("ascii:strict", "cp1252:strict", "utf-8:strict", "utf-16:strict"):
    CASES.append({"name": "result-stream-" + codec.replace(":", "-"),
                  "update": ["dispatch_brief_path", "\u754c\u754c"],
                  "env": {"PYTHONIOENCODING": codec}})
SUPPORT.CASES = CASES
PIN = SUPPORT.PIN
BASE_SEED = SUPPORT.seed


def seed(home, case, database):
    path = BASE_SEED(home, case, database)
    if "artifact" in case:
        artifact = home / "artifact"
        if case["artifact"] != "absent":
            artifact.write_bytes(b"\xff\x00" if case["artifact"] == "nonutf8" else b"{}")
            if case["artifact"] == "unreadable":
                artifact.chmod(0)
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE jobs SET dispatch_brief_path=?", (str(artifact),))
    return path


for mode in ("present", "absent", "unreadable", "nonutf8"):
    CASES.append({"name": "artifact-" + mode, "artifact": mode})
CASES.append({"name": "artifact-nonutf8-path", "update": [
    "dispatch_brief_path", {"bytes": "61727469666163742dff"}]})
for name, prefix in (
    ("leading-inline-repo-space", ["--repo-root=<HOME>"]),
    ("leading-inline-repo-space-end", ["--repo-root=<HOME>", "--"]),
    ("leading-inline-repo-abbreviation-space", ["--rep=<HOME>"]),
    ("leading-unknown-inline-space", ["--unknown=two words"]),
):
    CASES.append({"name": name, "argv": [*prefix, *SUPPORT.BASE_ARGV]})
SUPPORT.seed = seed
capture = SUPPORT.capture
install_local_hook = SUPPORT.install_local_hook

if __name__ == "__main__":
    SUPPORT.main()
