from __future__ import annotations

import io
import sys
from pathlib import Path

from mir.cli import run_python


def test_should_run_project_script_when_separator_is_present(tmp_path: Path) -> None:
    script = tmp_path / "helper.py"
    output = tmp_path / "result.txt"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n",
        encoding="utf-8",
    )

    assert (
        run_python.main(
            ["--project-root", str(tmp_path), "--", str(script), str(output), "ready"]
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == "ready"


def test_should_reject_script_outside_project(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-hook.py"
    outside.write_text("pass\n", encoding="utf-8")

    assert run_python.main(["--project-root", str(tmp_path), "--", str(outside)]) == 2


def test_should_run_inline_code_and_stdin_for_hook_parity(
    tmp_path: Path, monkeypatch
) -> None:
    inline = tmp_path / "inline.txt"
    stdin_output = tmp_path / "stdin.txt"

    assert run_python.main(
        [
            "--project-root",
            str(tmp_path),
            "--",
            "-c",
            "from pathlib import Path; Path('inline.txt').write_text('ok')",
        ]
    ) == 0
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO("from pathlib import Path; Path('stdin.txt').write_text('ok')\n"),
    )
    assert run_python.main(["--project-root", str(tmp_path), "--", "-"]) == 0

    assert inline.read_text(encoding="utf-8") == "ok"
    assert stdin_output.read_text(encoding="utf-8") == "ok"
