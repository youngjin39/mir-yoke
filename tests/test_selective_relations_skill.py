"""Behavioral contracts for the portable selective-relations skill."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from mir.cli.relations import main as relations_main
from mir.core.capabilities.manager import _validate_plugin
from mir.core.relations import bundle_relations

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "mir-core" / "skills" / "selective-relations"


def test_selective_relations_skill_is_standalone_and_links_its_reference(tmp_path: Path) -> None:
    isolated = tmp_path / "mir-core"
    shutil.copytree(ROOT / "plugins" / "mir-core", isolated)

    skill = isolated / "skills" / "selective-relations" / "SKILL.md"
    assert _validate_plugin(isolated, "mir-core", package_kind="skills")
    links = re.findall(r"\[[^]]+\]\(([^)]+)\)", skill.read_text(encoding="utf-8"))
    assert "references/selective-relations.md" in links
    assert (skill.parent / "references/selective-relations.md").is_file()


def test_selective_relations_example_runs_against_existing_fixture_files(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "src/auth").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "spec").mkdir()
    (tmp_path / "src/auth/login.py").write_text("def login(): pass\n", encoding="utf-8")
    (tmp_path / "src/auth/token_store.py").write_text("TOKEN = object()\n", encoding="utf-8")
    (tmp_path / "tests/test_login.py").write_text("def test_login(): pass\n", encoding="utf-8")
    (tmp_path / "spec/graph.yaml").write_text(
        "edges:\n"
        "  - [REQ-LOGIN, realized_by, MOD-AUTH]\n"
        "  - [MOD-AUTH, implemented_in, src/auth/login.py]\n"
        "  - [REQ-LOGIN, verified_by, tests/test_login.py]\n"
        "  - [MOD-AUTH, depends_on, MOD-TOKEN]\n"
        "  - [MOD-TOKEN, implemented_in, src/auth/token_store.py]\n",
        encoding="utf-8",
    )

    assert (
        relations_main(
            [
                "bundle",
                "REQ-LOGIN",
                "--purpose",
                "implementation",
                "--purpose",
                "verification",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "route=graph" in output
    assert "REQ-LOGIN realized_by MOD-AUTH" in output
    assert "MOD-AUTH implemented_in src/auth/login.py" in output
    assert "REQ-LOGIN verified_by tests/test_login.py" in output


def test_absent_graph_uses_search_route_without_creating_it(tmp_path: Path) -> None:
    result = bundle_relations(
        ["REQ-LOGIN"],
        ["implementation", "verification"],
        root=tmp_path,
    )

    assert result["route"] == "search"
    assert result["reason"] == "graph unavailable"
    assert not (tmp_path / "spec/graph.yaml").exists()
