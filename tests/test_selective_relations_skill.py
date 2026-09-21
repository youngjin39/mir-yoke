"""Behavioral contracts for the portable selective-relations skill."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
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


def test_selected_provider_invocation_avoids_an_old_local_console_and_preserves_space_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "target root with spaces"
    nested = root / "nested"
    nested.mkdir(parents=True)
    old_console = root / ".venv" / "bin" / "mir"
    old_console_called = tmp_path / "old-console-called"
    old_console.parent.mkdir(parents=True)
    old_console.write_text(
        f"#!/bin/sh\nprintf called > {old_console_called}\nexit 97\n",
        encoding="utf-8",
    )
    old_console.chmod(0o755)
    provider = tmp_path / "selected provider" / "mir"
    provider.parent.mkdir()
    provider.write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2 $3" = "relations query --help" ]; then\n'
        "  printf '%s\\n' '  --memory supported'\n"
        "  exit 0\n"
        "fi\n"
        "printf '<%s>\\n' \"$@\"\n",
        encoding="utf-8",
    )
    provider.chmod(0o755)

    preflight = subprocess.run(
        [str(provider), "relations", "query", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=nested,
    )
    assert preflight.returncode == 0
    assert "--memory" in preflight.stdout

    completed = subprocess.run(
        [
            str(provider),
            "relations",
            "query",
            "REQ-LOGIN",
            "--memory",
            "--root",
            str(root),
            "--purpose",
            "implementation",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=nested,
        env={**os.environ, "PATH": f"{old_console.parent}{os.pathsep}{os.environ['PATH']}"},
    )

    assert completed.returncode == 0
    assert f"<{root}>" in completed.stdout
    assert not old_console_called.exists()


def test_selected_provider_preflight_identifies_an_unsupported_runtime(tmp_path: Path) -> None:
    provider = tmp_path / "unsupported provider"
    provider.write_text("#!/bin/sh\nprintf '%s\\n' 'relations query options'\n", encoding="utf-8")
    provider.chmod(0o755)

    preflight = subprocess.run(
        [str(provider), "relations", "query", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert preflight.returncode == 0
    assert "--memory" not in preflight.stdout


def test_memory_ingest_example_changes_to_the_explicit_target_root(tmp_path: Path) -> None:
    reference = (SKILL / "references" / "memory-relations.md").read_text(encoding="utf-8")
    snippet = (
        "(\n"
        '  cd -- "$MIR_SRR_ROOT" && \\\n'
        '    "$MIR_SRR_PROVIDER" memory ingest-md docs/decisions/adr-checkout.md '
        "--db .mir/memory.db\n"
        ")\n"
    )
    assert f"```bash\n{snippet}```" in reference
    root = tmp_path / "target root with spaces"
    root.mkdir()
    provider = tmp_path / "selected provider"
    provider.write_text('#!/bin/sh\nprintf \'<%s>\\n\' "$PWD" "$@"\n', encoding="utf-8")
    provider.chmod(0o755)

    completed = subprocess.run(
        ["sh", "-c", snippet],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "MIR_SRR_ROOT": str(root),
            "MIR_SRR_PROVIDER": str(provider),
        },
    )

    assert completed.returncode == 0
    assert f"<{root}>" in completed.stdout
    assert "<memory>" in completed.stdout
    assert "<ingest-md>" in completed.stdout
    assert "<docs/decisions/adr-checkout.md>" in completed.stdout
    assert "<.mir/memory.db>" in completed.stdout

    missing_root = tmp_path / "missing target root"
    missing = subprocess.run(
        ["sh", "-c", snippet],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "MIR_SRR_ROOT": str(missing_root),
            "MIR_SRR_PROVIDER": str(provider),
        },
    )

    assert missing.returncode != 0
    assert missing.stdout == ""


def test_skill_requires_one_time_selected_provider_preflight_and_search_fallback() -> None:
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL / "references" / "selective-relations.md").read_text(encoding="utf-8")

    assert "Do not invoke bare `mir`" in skill
    assert "`MIR_SRR_PROVIDER` and `MIR_SRR_ROOT`" in skill
    assert "Do not repeat that preflight for each query." in skill
    assert "use ordinary search" in skill
    assert '"$MIR_SRR_PROVIDER" relations query' in reference
    assert ' --root "$MIR_SRR_ROOT"' in reference
