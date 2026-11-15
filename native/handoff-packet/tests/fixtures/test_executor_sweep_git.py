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
from unittest.mock import patch


class FixtureGitTest(unittest.TestCase):
    def load_git(self):
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
        return namespace["git"]

    def test_failure_exposes_stderr_and_keeps_exit(self):
        git = self.load_git()
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
                git(missing, "status")
            self.assertEqual(raised.exception.returncode, 128)
            self.assertEqual(raised.exception.stderr, expected.stderr)
            stream.flush()
            self.assertEqual(stream.buffer.getvalue(), expected.stderr)

    def test_drive_prefix_only_at_git_boundary(self):
        git = self.load_git()
        for raw, expected in [
            (r"\\?\C:\scratch\repo", r"C:\scratch\repo"),
            (r"\\?\z:\scratch\repo", r"z:\scratch\repo"),
            (r"\\?\UNC\server\share", r"\\?\UNC\server\share"),
            (r"\\?\Volume{fixture}\repo", r"\\?\Volume{fixture}\repo"),
            ("/scratch/repo", "/scratch/repo"),
        ]:
            with self.subTest(raw=raw), patch.object(
                subprocess, "check_output", return_value=b"unchanged\n"
            ) as run:
                self.assertEqual(git(raw, "worktree", "add", raw, "HEAD"), "unchanged\n")
                self.assertEqual(
                    run.call_args.args[0],
                    ["git", "-C", expected, "worktree", "add", expected, "HEAD"],
                )


class SnapshotRootTest(unittest.TestCase):
    def test_aliases_and_outside_root(self):
        source = Path(__file__).with_name("generate_executor_sweep.py").read_text()
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "normalize"
        )
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "snapshot", "exec"), namespace)
        normalize = namespace["normalize"]
        for root in [r"C:\scratch\native", r"\\?\C:\scratch\native"]:
            for alias in [
                r"C:\scratch\native", r"\\?\C:\scratch\native",
                "C:/scratch/native", "//?/C:/scratch/native",
            ]:
                with self.subTest(root=root, alias=alias):
                    self.assertEqual(normalize(alias + r"\wt-clean", root), "$ROOT/wt-clean")
                    self.assertEqual(normalize(alias, root), "$ROOT")
            for outside in [
                r"C:\scratch\native-other\keep", r"D:\elsewhere\keep", r"literal $ROOT\keep",
            ]:
                self.assertEqual(normalize(outside, root), outside)
        self.assertEqual(normalize("/scratch/native/wt-clean", "/scratch/native"), "$ROOT/wt-clean")


if __name__ == "__main__":
    unittest.main()
