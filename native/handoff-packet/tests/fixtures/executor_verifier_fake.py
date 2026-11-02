"""Portable, standard-library-only verifier used by both E7 implementations."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time


def main():
    receipt, mode, dispatch, *literal = sys.argv[1:]
    root = pathlib.Path.cwd()
    home = pathlib.Path(os.environ["HOME"])
    cache = pathlib.Path(os.environ["UV_CACHE_DIR"])
    result = {
        "cwd": str(root),
        "home": str(home),
        "cache": str(cache),
        "pid": os.getpid(),
        "literal": literal,
        "stdin_eof": sys.stdin.read() == "",
        "code": (root / "code.txt").read_text(encoding="utf-8"),
        "profile": (root / ".mir/repo-profile.toml").read_text(encoding="utf-8"),
        "env": {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "HOME",
                "UV_CACHE_DIR",
                "OPENAI_API_KEY",
                "EXPLICIT_TOKEN",
                "UNLISTED",
                "CODEX_HOME",
                "CODEX_EVENTS_FILE",
                "LC_MESSAGES",
                "LANG",
            }
        },
        "home_exists": home.is_dir(),
        "cache_exists": cache.is_dir(),
        "home_preexisting": (home / "verifier-marker").exists(),
    }
    pathlib.Path(receipt).write_text(json.dumps(result), encoding="utf-8")
    (root / "code.txt").write_text("verifier mutated checkout\n", encoding="utf-8")
    (root / "generated.txt").write_text("isolated\n", encoding="utf-8")
    if mode == "dirty":
        (pathlib.Path(dispatch) / "unexpected.txt").write_text("dirty\n", encoding="utf-8")
    if mode.startswith("lock"):
        subprocess.run(["git", "-C", str(root), "worktree", "lock", str(root)], check=True)
    if mode == "timeout":
        time.sleep(8)
        pathlib.Path(receipt + ".late").write_text("child survived timeout\n", encoding="utf-8")
    (home / "verifier-marker").touch()
    (cache / "verifier-marker").touch()
    if mode == "home-cleanup-error":
        shutil.rmtree(home)
        home.write_text("cleanup blocker\n", encoding="utf-8")
    if mode == "output-large":
        os.write(1, b"x" * 262144)
        os.write(2, b"y" * 262144)
    if mode == "output-invalid":
        os.write(1, b"\xff")
    if mode == "descendant-invalid":
        subprocess.Popen(
            [sys.executable, "-c", "import os,time; time.sleep(0.1); os.write(1, b'\\xff')"]
        )
    return 7 if mode in {"fail", "lock-fail"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
