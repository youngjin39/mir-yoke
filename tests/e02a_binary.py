"""Resolve explicit E02a binaries or build each checkout binary once per test session."""

import os
import subprocess
from functools import cache
from pathlib import Path

CRATE = Path(__file__).resolve().parents[1] / "native/handoff-packet"


def binary(name, variable):
    override = os.environ.get(variable)
    if override:
        return Path(override)
    return build_binary(name)


@cache
def build_binary(name):
    environment = dict(os.environ, CARGO_BUILD_JOBS="4", CARGO_TARGET_DIR=str(CRATE / "target"))
    subprocess.run(
        ["cargo", "build", "--offline", "--locked", "--bin", name],
        cwd=CRATE,
        env=environment,
        check=True,
    )
    return CRATE / "target/debug" / (name + ".exe" if os.name == "nt" else name)
