from __future__ import annotations

import json
from pathlib import Path

import pytest

from mir.cli.relations import main


def test_cli_json_query(tmp_path: Path, capsys) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text("edges:\n  - [A, has_req, B]\n", encoding="utf-8")
    assert (
        main(["query", "A", "--purpose", "implementation", "--root", str(tmp_path), "--json"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["edges"][0]["source_line"] == 2


def test_cli_invalid_anchor_exits_two(tmp_path: Path, capsys) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text("edges:\n  - [A, has_req, B]\n", encoding="utf-8")
    assert main(["query", "missing", "--purpose", "impact", "--root", str(tmp_path)]) == 2
    assert "unknown anchor" in capsys.readouterr().err


def test_cli_bundle_search_json(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "bundle",
            "A",
            "B",
            "--purpose",
            "implementation",
            "--purpose",
            "verification",
            "--root",
            str(tmp_path),
            "--json",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["route"] == "search"


def test_cli_accepts_custom_graph_and_dependencies_json(tmp_path: Path, capsys) -> None:
    graph = tmp_path / "relation maps/graph.yaml"
    graph.parent.mkdir()
    graph.write_text("edges:\n  - [APP, depends_on, LIB]\n", encoding="utf-8")
    assert (
        main(
            [
                "query",
                "APP",
                "--purpose",
                "dependencies",
                "--root",
                str(tmp_path),
                "--graph",
                "relation maps/graph.yaml",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["source"]["graph"] == "relation maps/graph.yaml"
    assert result["edges"][0]["target"] == "LIB"


def test_cli_reports_invalid_custom_graph_as_error(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "query",
                "A",
                "--purpose",
                "implementation",
                "--root",
                str(tmp_path),
                "--graph",
                "../outside.yaml",
            ]
        )
        == 2
    )
    assert "safe repository-relative" in capsys.readouterr().err


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("separator", [r"\n", r"\u0085", r"\u2028", r"\u2029"])
def test_cli_rejects_control_characters_before_human_or_json_rendering(
    tmp_path: Path, capsys, json_output: bool, separator: str
) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text(
        f'edges: [[A, has_req, "B{separator}notice: forged"]]\n', encoding="utf-8"
    )
    args = ["query", "A", "--purpose", "implementation", "--root", str(tmp_path)]
    if json_output:
        args.append("--json")
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "control" in captured.err
