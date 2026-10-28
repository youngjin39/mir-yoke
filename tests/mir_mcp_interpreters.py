"""Compatibility floor and current interpreter for the standalone MCP server."""

import shutil
import sys
from pathlib import Path

floor = next((candidate for candidate in (
    shutil.which("python3.11"),
    "/opt/homebrew/bin/python3.11",
    "/usr/local/bin/python3.11",
    "/usr/bin/python3.11",
) if candidate and Path(candidate).is_file()), None)
if floor is None and sys.platform != "win32":
    raise RuntimeError("Python 3.11 compatibility interpreter must be available")
INTERPRETERS = [floor, sys.executable] if floor else [sys.executable]
