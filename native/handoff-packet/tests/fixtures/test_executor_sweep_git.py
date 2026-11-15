"""Exercise the fixture Git boundary without importing the live executor package."""

import ast
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FixtureGitTest(unittest.TestCase):
    def test_failure_exposes_stderr_and_keeps_exit(self):
        source = Path(__file__).with_name("generate_executor_sweep.py").read_text()
        function = next(
            node
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "git"
        )
        namespace = {
            "os": os,
            "subprocess": subprocess,
            "sys": sys,
            "OLD": "2026-01-01T00:00:00+00:00",
        }
        code = compile(ast.Module(body=[function], type_ignores=[]), "fixture-git", "exec")
        exec(code, namespace)
        with tempfile.TemporaryDirectory() as scratch:
            missing = Path(scratch) / "missing-repo"
            expected = subprocess.run(
                ["git", "-C", str(missing), "status"], capture_output=True, check=False
            )
            self.assertEqual(expected.returncode, 128)
            stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
            with (
                contextlib.redirect_stderr(stream),
                self.assertRaises(subprocess.CalledProcessError) as raised,
            ):
                namespace["git"](missing, "status")
            self.assertEqual(raised.exception.returncode, 128)
            self.assertEqual(raised.exception.stderr, expected.stderr)
            stream.flush()
            self.assertEqual(stream.buffer.getvalue(), expected.stderr)


if __name__ == "__main__":
    unittest.main()
