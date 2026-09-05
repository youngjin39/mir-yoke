from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

import pytest

from mir.core.adoption.boundary import load_boundary, payload_findings
from mir.core.adoption.slim import (
    SlimError,
    apply_adopter_slim,
    recover_adopter_slim,
    rollback_adopter_slim,
)

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.mark.parametrize(
    "contract",
    (
        (ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
        "# Mir Yoke — Starter, Project Agent Kit, and Optional CLI Contract\n",
    ),
)
def test_should_detect_current_and_legacy_yoke_contract_markers_in_an_adopter(
    tmp_path: Path, contract: str
) -> None:
    _write(tmp_path / "CLAUDE.md", contract)
    boundary = load_boundary(ROOT)
    profile = {"repo": {"slug": "independent-product", "repository_type": "code_app"}}

    assert payload_findings(tmp_path, boundary=boundary, profile=profile) == [
        {"kind": "text", "path": "CLAUDE.md"}
    ]


# @spec FR-001 FR-004 QR-001
def test_should_reject_native_windows_before_slim_recovery_reads_project_state(
    tmp_path, monkeypatch
):
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve me\n", encoding="utf-8")
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    with pytest.raises(SlimError, match="Native Windows adopter slim is unsupported"):
        recover_adopter_slim(tmp_path)

    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before
    assert marker.read_text(encoding="utf-8") == "preserve me\n"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _project(root: Path) -> None:
    _write(
        root / ".mir/repo-profile.toml",
        '[repo]\nslug = "sample-product"\nrepository_type = "starter_project"\n',
    )
    boundary = {
        "schema_version": 1,
        "provider_owners": [
            {
                "slug": "mir-yoke",
                "repository_types": ["public_harness_template"],
            }
        ],
        "provider_markers": ["src/mir", "tests/provider_test.py"],
        "provider_text_markers": [
            {"path": "CLAUDE.md", "contains": "Mir Yoke provider contract"}
        ],
        "source_asset_manifest": "config/template-assets.json",
        "payload_manifest": "config/adopter-payload.json",
        "remove_classifications": [
            "reference",
            "optional-consumer-tool",
            "template-maintainer-tool",
            "historical",
        ],
    }
    assets = {
        "schema_version": 1,
        "classifications": [
            "starter",
            "reference",
            "optional-consumer-tool",
            "template-maintainer-tool",
            "historical",
        ],
        "rules": [
            {
                "id": "starter",
                "classification": "starter",
                "include": [
                    ".mir/**",
                    "CLAUDE.md",
                    "apps/**",
                    "config/adopter-boundary.json",
                ],
                "exclude": [],
                "reason": "Consumer-owned runtime contract.",
            },
            {
                "id": "provider",
                "classification": "optional-consumer-tool",
                "include": ["src/**"],
                "exclude": [],
                "reason": "Provider implementation source.",
            },
            {
                "id": "maintainer",
                "classification": "template-maintainer-tool",
                "include": ["tests/**", "config/template-assets.json"],
                "exclude": [],
                "reason": "Provider maintenance surface.",
            },
            {
                "id": "reference",
                "classification": "reference",
                "include": ["README.md"],
                "exclude": [],
                "reason": "Provider reference document.",
            },
        ],
        "prohibited_active_paths": [],
    }
    _write(root / "config/adopter-boundary.json", json.dumps(boundary))
    _write(root / "config/template-assets.json", json.dumps(assets))
    _write(root / "CLAUDE.md", "# Product contract\n")
    _write(root / "README.md", "Provider reference\n")
    _write(root / "src/mir/provider.py", "PROVIDER = True\n")
    _write(root / "tests/provider_test.py", "def test_provider(): pass\n")
    payload_files = []
    classifications = {
        ".mir/repo-profile.toml": "starter",
        "CLAUDE.md": "starter",
        "README.md": "reference",
        "config/adopter-boundary.json": "starter",
        "config/template-assets.json": "template-maintainer-tool",
        "src/mir/provider.py": "optional-consumer-tool",
        "tests/provider_test.py": "template-maintainer-tool",
    }
    for relative, classification in classifications.items():
        body = (root / relative).read_bytes()
        payload_files.append(
            {
                "path": relative,
                "sha256": __import__("hashlib").sha256(body).hexdigest(),
                "classification": classification,
                "disposition": "preserve" if classification == "starter" else "remove",
            }
        )
    payload = {
        "schema_version": 1,
        "generated_from": "config/template-assets.json",
        "files": payload_files,
    }
    _write(root / "config/adopter-payload.json", json.dumps(payload))
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    commit = _git(root, "rev-parse", "HEAD")
    profile_path = root / ".mir/repo-profile.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8")
        + f'profile_base_commit = "{commit}"\n',
        encoding="utf-8",
    )
    _git(root, "add", ".mir/repo-profile.toml")
    _git(root, "commit", "--amend", "-qm", "fixture")
    final_commit = _git(root, "rev-parse", "HEAD")
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(commit, final_commit),
        encoding="utf-8",
    )


def _external_cli(tmp_path: Path) -> Path:
    cli = tmp_path.parent / f"{tmp_path.name}-external" / "mir"
    _write(cli, "#!/bin/sh\nexit 0\n")
    cli.chmod(0o755)
    return cli


# @spec FR-001 FR-004
def test_should_remove_unchanged_provider_files_when_finalize_is_ready(tmp_path: Path) -> None:
    _project(tmp_path)
    _write(tmp_path / "README.md", "Product README\n")
    _write(tmp_path / "apps/product.ts", "export const product = true;\n")

    report = apply_adopter_slim(
        tmp_path,
        external_cli=_external_cli(tmp_path),
        verify=lambda _cli, _root: (True, "ready"),
    )

    assert report["status"] == "applied"
    assert not (tmp_path / "src/mir/provider.py").exists()
    assert not (tmp_path / "tests/provider_test.py").exists()
    assert not (tmp_path / "config/template-assets.json").exists()
    assert (tmp_path / "README.md").read_text() == "Product README\n"
    assert (tmp_path / "apps/product.ts").is_file()
    assert "README.md" in report["preserved_modified"]


def test_slim_report_preserves_namespaced_launcher_symlink(tmp_path: Path) -> None:
    _project(tmp_path)
    runtime_root = tmp_path.parent / f"{tmp_path.name}-runtime"
    inner = runtime_root / "tools/mir-harness/bin/mir"
    outer = runtime_root / "bin/mir"
    _write(inner, "#!/bin/sh\nexit 0\n")
    inner.chmod(0o755)
    outer.parent.mkdir(parents=True)
    outer.symlink_to(inner)

    report = apply_adopter_slim(
        tmp_path,
        external_cli=outer,
        verify=lambda _cli, _root: (True, "ready"),
    )

    assert report["external_cli"] == str(outer)


# @spec FR-001 FR-004
def test_should_restore_removed_files_when_external_cli_verification_fails(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    original = (tmp_path / "src/mir/provider.py").read_bytes()

    with pytest.raises(SlimError, match="rollback complete"):
        apply_adopter_slim(
            tmp_path,
            external_cli=_external_cli(tmp_path),
            verify=lambda _cli, _root: (False, "capability status failed"),
        )

    assert (tmp_path / "src/mir/provider.py").read_bytes() == original
    assert (tmp_path / "tests/provider_test.py").is_file()
    assert (tmp_path / "config/template-assets.json").is_file()


# @spec FR-001 FR-004
def test_should_preserve_every_file_when_provider_marker_has_local_changes(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    _write(tmp_path / "src/mir/product_override.py", "PRODUCT = True\n")
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    with pytest.raises(SlimError, match="provider marker contains preserved content"):
        apply_adopter_slim(
            tmp_path,
            external_cli=_external_cli(tmp_path),
            verify=lambda _cli, _root: (True, "ready"),
        )

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after == before


# @spec FR-001 FR-004
def test_should_reject_cli_installed_inside_project_before_removing_files(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    local_cli = tmp_path / ".venv/bin/mir"
    _write(local_cli, "#!/bin/sh\nexit 0\n")
    local_cli.chmod(0o755)

    with pytest.raises(SlimError, match="outside the adopter repository"):
        apply_adopter_slim(
            tmp_path,
            external_cli=local_cli,
            verify=lambda _cli, _root: (True, "ready"),
        )

    assert (tmp_path / "src/mir/provider.py").is_file()


# @spec FR-001 FR-004
def test_should_reject_changed_release_control_before_removing_files(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    payload_path = tmp_path / "config/adopter-payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["files"] = []
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SlimError, match="release control changed after Phase 1"):
        apply_adopter_slim(
            tmp_path,
            external_cli=_external_cli(tmp_path),
            verify=lambda _cli, _root: (True, "ready"),
        )

    assert (tmp_path / "src/mir/provider.py").is_file()
    assert (tmp_path / "tests/provider_test.py").is_file()


# @spec FR-001 FR-004
def test_should_reject_provider_file_beneath_symlinked_parent(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    tests_dir = tmp_path / "tests"
    provider_body = (tests_dir / "provider_test.py").read_bytes()
    (tests_dir / "provider_test.py").unlink()
    tests_dir.rmdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "provider_test.py").write_bytes(provider_body)
    tests_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SlimError, match="provider marker contains preserved content"):
        apply_adopter_slim(
            tmp_path,
            external_cli=_external_cli(tmp_path),
            verify=lambda _cli, _root: (True, "ready"),
        )

    assert (outside / "provider_test.py").read_bytes() == provider_body
    assert (tmp_path / "src/mir/provider.py").is_file()


# @spec FR-001 FR-004
def test_should_rollback_a_deferred_slim_transaction(tmp_path: Path) -> None:
    _project(tmp_path)
    original = (tmp_path / "src/mir/provider.py").read_bytes()

    report = apply_adopter_slim(
        tmp_path,
        external_cli=_external_cli(tmp_path),
        verify=lambda _cli, _root: (True, "ready"),
        defer_commit=True,
    )

    assert report["status"] == "applied"
    assert (tmp_path / ".mir/slim-transaction.json").is_file()
    assert (tmp_path / ".mir/slim.lock").is_file()
    rollback_adopter_slim(tmp_path, report)
    assert (tmp_path / "src/mir/provider.py").read_bytes() == original
    assert not (tmp_path / ".mir/slim-transaction.json").exists()
    assert not (tmp_path / ".mir/slim.lock").exists()


# @spec FR-001 FR-004
def test_should_recover_an_interrupted_slim_before_a_new_transaction(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    original = (tmp_path / "tests/provider_test.py").read_bytes()
    report = apply_adopter_slim(
        tmp_path,
        external_cli=_external_cli(tmp_path),
        verify=lambda _cli, _root: (True, "ready"),
        defer_commit=True,
    )
    journal_path = tmp_path / ".mir/slim-transaction.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["pid"] = 2**31 - 1
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    recovery = recover_adopter_slim(tmp_path)

    assert recovery == {
        "status": "rolled_back",
        "transaction_id": report["transaction_id"],
    }
    assert (tmp_path / "tests/provider_test.py").read_bytes() == original
    assert not journal_path.exists()


# @spec FR-001 FR-004
def test_should_reject_an_unsafe_transaction_journal_symlink(tmp_path: Path) -> None:
    _project(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-journal.json"
    outside.write_text("{}\n", encoding="utf-8")
    (tmp_path / ".mir/slim-transaction.json").symlink_to(outside)

    with pytest.raises(SlimError, match="unsafe slim journal symlink"):
        recover_adopter_slim(tmp_path)

    assert outside.read_text(encoding="utf-8") == "{}\n"


# @spec FR-001 FR-004
def test_recovery_never_unlinks_a_lock_through_a_symlinked_mir_directory(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-mir"
    outside.mkdir()
    outside_lock = outside / "slim.lock"
    outside_lock.write_text("999999999\n", encoding="utf-8")
    (tmp_path / ".mir").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SlimError, match="real .mir directory"):
        recover_adopter_slim(tmp_path)

    assert outside_lock.read_text(encoding="utf-8") == "999999999\n"


# @spec FR-001 FR-004
def test_slim_never_moves_files_through_a_symlinked_quarantine_root(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-quarantine"
    outside.mkdir()
    (tmp_path / ".mir/slim-quarantine").symlink_to(
        outside, target_is_directory=True
    )
    original = (tmp_path / "tests/provider_test.py").read_bytes()

    with pytest.raises(SlimError, match="quarantine root contains a symlink"):
        apply_adopter_slim(
            tmp_path,
            external_cli=_external_cli(tmp_path),
            verify=lambda _cli, _root: (True, "ready"),
        )

    assert (tmp_path / "tests/provider_test.py").read_bytes() == original
    assert list(outside.rglob("*")) == []


# @spec FR-001 FR-004
def test_should_not_accept_already_slim_while_exact_remove_files_remain(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    (tmp_path / "src/mir/provider.py").unlink()
    (tmp_path / "src/mir").rmdir()
    (tmp_path / "src").rmdir()
    (tmp_path / "tests/provider_test.py").unlink()
    (tmp_path / "tests").rmdir()

    with pytest.raises(SlimError, match="unchanged remove payload remains"):
        apply_adopter_slim(
            tmp_path,
            external_cli=_external_cli(tmp_path),
            verify=lambda _cli, _root: (True, "ready"),
        )

    assert (tmp_path / "config/template-assets.json").is_file()


# @spec FR-001 FR-004
def test_should_detect_a_payload_file_changed_between_preflight_and_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path)
    original_replace = os.replace
    changed = False

    def replace_with_concurrent_change(source: Path | str, destination: Path | str) -> None:
        nonlocal changed
        source_path = Path(source)
        if source_path == tmp_path / "src/mir/provider.py" and not changed:
            _write(tmp_path / "tests/provider_test.py", "# concurrent product edit\n")
            changed = True
        original_replace(source, destination)

    monkeypatch.setattr("mir.core.adoption.slim.os.replace", replace_with_concurrent_change)

    with pytest.raises(SlimError, match="provider path changed before move"):
        apply_adopter_slim(
            tmp_path,
            external_cli=_external_cli(tmp_path),
            verify=lambda _cli, _root: (True, "ready"),
        )

    assert changed is True
    assert (tmp_path / "src/mir/provider.py").is_file()
    assert (tmp_path / "tests/provider_test.py").read_text() == "# concurrent product edit\n"
