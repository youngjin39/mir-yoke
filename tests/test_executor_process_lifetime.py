"""Synthetic process lifetime regressions; never uses a real provider."""

from __future__ import annotations

import os
import runpy
import signal
import subprocess
import time
from pathlib import Path

import pytest
from test_executor_status_native_parity import binary  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_direct.py"))
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX signals")


def changing(path):
    before = path.read_bytes() if path.exists() else b""
    time.sleep(0.15)
    return before != (path.read_bytes() if path.exists() else b"")


def wait_for_heartbeat(path, deadline):
    before = path.read_bytes() if path.exists() else b""
    while before == (path.read_bytes() if path.exists() else b""):
        assert time.monotonic() < deadline, f"No heartbeat progress: {path}"
        time.sleep(0.01)


@pytest.mark.parametrize("mode", [
    "timeout", "selfkill", "parent", "running-int",
    "before-term", "before-int", "cleanup-term", "cleanup-int",
])
def test_owned_provider_lifetime(binary, tmp_path, mode):  # noqa: F811
    home = tmp_path.resolve() / "synthetic"
    case = {"name": mode}
    launcher = SUPPORT["seed"](home, case)
    script = launcher.read_text()
    injection = """
import threading, signal, subprocess
(root / 'provider-pid').write_text(str(os.getpid()))
def beat():
    while True:
        with (root/'provider-heartbeat').open('ab') as h: h.write(b'x')
        time.sleep(.02)
threading.Thread(target=beat, daemon=True).start()
"""
    if mode.startswith("cleanup-"):
        injection += """
def term(s, f):
    (root / 'term-started').write_text('yes')
    time.sleep(2)
    sys.exit(0)
signal.signal(signal.SIGTERM, term)
"""
    signal_only = mode in {"parent", "running-int", "before-term", "before-int"}
    if mode.startswith("before-"):
        injection += """
(root / 'before-start').write_text('ready')
while True:
    time.sleep(0.01)
"""
    if not signal_only:
        descendant = (
            "import os,time\nfrom pathlib import Path\n"
            "p=Path(os.environ['EXECUTE_FIXTURE_ROOT'])/'desc-heartbeat'\n"
            "while True:\n"
            " with p.open('ab') as h:h.write(b'x')\n"
            " time.sleep(.02)\n"
        )
        injection += (
            f"child=subprocess.Popen([sys.executable, '-c', {descendant!r}])\n"
            "(root/'desc-pid').write_text(str(child.pid))\n"
        )
        # Both open pipes and a partial line must be cancellable.
        injection += "sys.stderr.write('partial'); sys.stderr.flush()\n"
    script = script.replace(
        "(root / 'provider-started').write_text('started', encoding='utf-8')",
        "(root / 'provider-started').write_text('started', encoding='utf-8')\n" + injection,
    )
    if mode == "selfkill":
        script = script.replace(
            "if mode == 'timeout':",
            "if mode == 'timeout':\n"
            "            os.kill(os.getpid(), signal.SIGKILL)\n"
            "        if mode == 'timeout':",
        )
    launcher.write_text(script)
    env = SUPPORT["environment"](home, case, launcher)
    env["EXECUTE_FIXTURE_MODE"] = "timeout"
    args = SUPPORT["BASE"] + ([] if signal_only else ["--timeout=1"])
    with (home / "stdout").open("wb") as out, (home / "stderr").open("wb") as err:
        proc = subprocess.Popen(
            [str(binary), "--home-root", str(home), *args],
            cwd=home,
            env=env,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 8
            def ready():
                if mode.startswith("before-"):
                    return (home / "before-start").exists()
                methods = home / "provider-methods"
                return methods.exists() and "turn/start" in methods.read_text()

            while not ready():
                assert time.monotonic() < deadline, (home / "stderr").read_bytes()
                time.sleep(0.01)
            if signal_only:
                wait_for_heartbeat(home / "provider-heartbeat", deadline)
                proc.send_signal(signal.SIGINT if mode.endswith("int") else signal.SIGTERM)
            if mode.startswith("cleanup-"):
                while not (home / "term-started").exists():
                    assert time.monotonic() < deadline
                    time.sleep(0.005)
                proc.send_signal(signal.SIGTERM if mode == "cleanup-term" else signal.SIGINT)
            code = proc.wait(timeout=6)
            expected = (
                130 if mode.endswith("int")
                else 143 if signal_only or mode == "cleanup-term"
                else 1
            )
            assert code == expected
            stderr = (home / "stderr").read_text()
            if signal_only or mode in {"selfkill", "cleanup-term", "cleanup-int"}:
                assert stderr == ""
                if mode == "selfkill":
                    assert b"Codex app-server exited with code -9" in (home / "stdout").read_bytes()
            else:
                assert stderr == (
                    "[mir_executor] Codex timeout after 1s: "
                    f"Command '{[str(launcher), 'app-server']}'"
                    " timed out after 1 seconds\n"
                )
            assert not changing(home / "provider-heartbeat")
            if mode in {"timeout", "selfkill"}:
                # Reference terminates only its direct provider on timeout.
                wait_for_heartbeat(home / "desc-heartbeat", deadline)
        finally:
            # Only PIDs created by this test are signalled; stopped providers
            # have already been reaped by their owner.
            # Scheduling delays must not cause cleanup to skip a live child.
            for name in ("desc-pid", "provider-pid"):
                if (home / name).exists():
                    try:
                        os.kill(int((home / name).read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=3)
            assert not changing(home / "provider-heartbeat")
            assert not changing(home / "desc-heartbeat")
