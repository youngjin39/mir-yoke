"""Check/use swaps must refuse without outside-root effects."""

import pytest
from test_stage_e01_core_adoption import cases, record

from mir.core.adoption import boundary, slim


def test_lock_creation_error_keeps_original_path(tmp_path):
    case = next(case for case in cases() if case["name"] == "apply.lock_permission")
    observed = record(case, tmp_path, boundary, slim)
    assert observed["expected"][0]["result"] == {
        "error": ["PermissionError", "[Errno 13] Permission denied: '<root>/.mir/slim.lock'"]
    }


@pytest.mark.parametrize("publication", ["journal", "runtime"])
def test_temporary_creation_error_keeps_original_path(tmp_path, monkeypatch, publication):
    from mir.core.adoption import _filesystem, runtime

    parent = tmp_path / ".mir"
    parent.mkdir()
    name = "slim-transaction.json" if publication == "journal" else "manifest.json"
    monkeypatch.setattr(
        _filesystem.tempfile, "_get_candidate_names", lambda: iter(["fixedtmp"])
    )
    parent.chmod(0o555)
    try:
        with pytest.raises(PermissionError) as error:
            if publication == "journal":
                slim._atomic_fsync_json(parent / name, {})
            else:
                runtime.create_runtime_manifest(
                    parent,
                    parent / name,
                    source_url="synthetic",
                    source_commit="a" * 40,
                    constraints_sha256="b" * 64,
                )
        assert error.value.filename == str(parent / f".{name}.fixedtmp")
    finally:
        parent.chmod(0o755)


@pytest.mark.parametrize(
    "case",
    [case for case in cases() if case["name"].startswith("race.")],
    ids=lambda case: case["name"],
)
def test_move_refuses_parent_swap(tmp_path, case):
    record(case, tmp_path, boundary, slim)


@pytest.mark.parametrize("publication", ["journal", "runtime"])
def test_publication_refuses_parent_swap(tmp_path, monkeypatch, publication):
    from mir.core.adoption import runtime

    root = tmp_path / "root"
    root.mkdir()
    (root / ".mir").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    name = "slim-transaction.json" if publication == "journal" else "manifest.json"
    (outside / name).write_bytes(b"OUTSIDE")
    module = slim if publication == "journal" else runtime
    seeded = []

    def swap(_root, source, destination):
        (outside / source.name).write_bytes(b"OUTSIDE-TEMP")
        seeded.append(source.name)
        parent = destination.parent
        parent.rename(parent.with_name(parent.name + "-saved"))
        parent.symlink_to(outside)

    monkeypatch.setattr(module, "_before_move", swap)
    with pytest.raises(OSError):
        if publication == "journal":
            slim._atomic_fsync_json(root / ".mir" / name, {"status": "moving"})
        else:
            runtime.create_runtime_manifest(
                root,
                root / name,
                source_url="synthetic",
                source_commit="a" * 40,
                constraints_sha256="b" * 64,
            )
    assert (outside / name).read_bytes() == b"OUTSIDE"
    assert sorted(p.name for p in outside.iterdir()) == sorted([name, seeded[0]])
    assert (outside / seeded[0]).read_bytes() == b"OUTSIDE-TEMP"


def test_rollback_preserves_unreadable_file_layout(tmp_path):
    from test_stage_e01_core_adoption import JOURNAL, QUARANTINE, journal

    (tmp_path / ".mir").mkdir()
    source = tmp_path / QUARANTINE / "provider/a"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"unreadable")
    source.chmod(0)
    (tmp_path / JOURNAL).write_text("{}")
    assert slim._rollback_journal(tmp_path, journal(paths=["provider/a"])) == []
    restored = tmp_path / "provider/a"
    assert restored.stat().st_mode & 0o777 == 0
    restored.chmod(0o600)
    assert restored.read_bytes() == b"unreadable"


@pytest.mark.parametrize("restricted", ["source_parent", "destination_parent", "root"])
def test_rollback_preserves_search_only_directories(tmp_path, restricted):
    from test_stage_e01_core_adoption import JOURNAL, QUARANTINE, journal

    source = tmp_path / QUARANTINE / "provider/a"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"retained")
    destination = tmp_path / "provider/a"
    destination.parent.mkdir()
    (tmp_path / JOURNAL).write_text("{}")
    directory = {
        "source_parent": source.parent,
        "destination_parent": destination.parent,
        "root": tmp_path,
    }[restricted]
    directory.chmod(0o111 if restricted == "root" else 0o300)
    try:
        assert slim._rollback_journal(tmp_path, journal(paths=["provider/a"])) == []
        assert destination.read_bytes() == b"retained"
    finally:
        directory.chmod(0o755)


@pytest.mark.parametrize("publication", ["journal", "runtime"])
def test_publication_refuses_root_ancestor_swap(tmp_path, monkeypatch, publication):
    from mir.core.adoption import runtime

    root = tmp_path / "envelope/root"
    (root / ".mir").mkdir(parents=True)
    outside = tmp_path / "outside"
    target = (
        root / ".mir/slim-transaction.json" if publication == "journal" else root / "manifest.json"
    )
    outside_parent = outside / target.parent.relative_to(root.parent)
    outside_parent.mkdir(parents=True)
    (outside_parent / target.name).write_bytes(b"OUTSIDE")
    module = slim if publication == "journal" else runtime
    seeded = []

    def swap(_root, source, destination):
        (outside_parent / source.name).write_bytes(b"OUTSIDE-TEMP")
        seeded.append(source.name)
        root.parent.rename(tmp_path / "saved")
        root.parent.symlink_to(outside)

    monkeypatch.setattr(module, "_before_move", swap)
    with pytest.raises(OSError):
        if publication == "journal":
            slim._atomic_fsync_json(target, {})
        else:
            runtime.create_runtime_manifest(
                root,
                target,
                source_url="synthetic",
                source_commit="a" * 40,
                constraints_sha256="b" * 64,
            )
    assert (outside_parent / target.name).read_bytes() == b"OUTSIDE"
    assert (outside_parent / seeded[0]).read_bytes() == b"OUTSIDE-TEMP"


def test_runtime_preserves_aliases_long_names_and_temp_collision(tmp_path, monkeypatch):
    from mir.core.adoption import _filesystem, runtime

    root = tmp_path / "runtime"
    root.mkdir()
    (root / "payload").write_bytes(b"closure")
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    name = "m" * 245
    target = root / name
    collision = root / ("." + name + ".aaaaaaaa")
    collision.write_bytes(b"existing")
    monkeypatch.setattr(
        _filesystem.tempfile, "_get_candidate_names", lambda: iter(["aaaaaaaa", "bbbbbbbb"])
    )
    document = runtime.create_runtime_manifest(
        alias,
        alias / name,
        source_url="synthetic",
        source_commit="a" * 40,
        constraints_sha256="b" * 64,
    )
    assert document["schema_version"] == 1
    assert collision.read_bytes() == b"existing"
    assert target.is_file()
    assert runtime.verify_runtime_manifest(alias, alias / name) == []


@pytest.mark.parametrize("mutation", ["mkdir", "unlink", "rmdir"])
def test_directory_mutations_do_not_follow_swapped_parent(tmp_path, monkeypatch, mutation):
    import os

    from mir.core.adoption import _filesystem

    root = tmp_path / "project"
    parent = root / ".mir"
    outside = tmp_path / "outside"
    parent.mkdir(parents=True)
    outside.mkdir()
    victim = parent / "victim"
    if mutation == "unlink":
        victim.write_bytes(b"inside")
        (outside / "victim").write_bytes(b"outside")
    elif mutation == "rmdir":
        victim.mkdir()
        (outside / "victim").mkdir()
    syscall = getattr(os, mutation)
    swapped = False

    def swap_then_mutate(path, *args, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            parent.rename(root / "saved")
            parent.symlink_to(outside)
        return syscall(path, *args, **kwargs)

    monkeypatch.setattr(os, mutation, swap_then_mutate)
    if mutation == "mkdir":
        _filesystem.mkdir(root, victim)
        assert not (outside / "victim").exists()
    elif mutation == "unlink":
        _filesystem.unlink(root, victim)
        assert (outside / "victim").read_bytes() == b"outside"
    else:
        slim._prune_empty_parents(victim / "placeholder", root)
        assert (outside / "victim").is_dir()
    assert swapped


def test_windows_publication_keeps_existing_path_behavior(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace

    from mir.core.adoption import runtime

    # Exercise dispatch on this host; this is not Windows platform evidence.
    monkeypatch.setattr(runtime, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))

    def unavailable(*_args):
        raise AssertionError("Windows must not enter POSIX dir_fd code")

    monkeypatch.setattr(runtime.confined, "parent", unavailable)
    target = tmp_path / "manifest.json"
    document = runtime.create_runtime_manifest(
        tmp_path,
        target,
        source_url="synthetic",
        source_commit="a" * 40,
        constraints_sha256="b" * 64,
    )
    assert document["schema_version"] == 1
    assert runtime.verify_runtime_manifest(tmp_path, target) == []
