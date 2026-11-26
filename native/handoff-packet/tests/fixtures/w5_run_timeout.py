"""Bound a verification command and terminate its process group on timeout."""
import os
import signal
import subprocess
import sys

process = subprocess.Popen(sys.argv[2:], start_new_session=True)
try:
    result = process.wait(timeout=int(sys.argv[1]))
except (subprocess.TimeoutExpired, KeyboardInterrupt):
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    result = 124
raise SystemExit(result)
