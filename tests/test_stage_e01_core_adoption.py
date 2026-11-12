"""Independent E01 records from the pinned provider, including durable file effects.

Regenerate: python tests/test_stage_e01_core_adoption.py --write --scratch "$E01_SCRATCH"
The scratch argument must name a synthetic, disposable migration fixture directory.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PIN = "9ce2c2efcf10862b907f7c801b8ff40a9dbfb04f"
REFERENCE_PATCH = {
    "src/mir/core/adoption/_filesystem.py": (
        "77463d2151d68e11e177d61612217b2e50b0e8fd61c9c16f120a10c643503c13"
    ),
    "src/mir/core/adoption/slim.py": (
        "e9d8479dd3ac87cb6f02fb5391976cc031f87c3834231eb38ff955a8255eb8c3"
    ),
    "src/mir/core/adoption/runtime.py": (
        "29cfc15e43004c60c2ce78225a7a147fa7d2fa5e5d742a7fad0fda41b86a617b"
    ),
}
REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "native/handoff-packet/tests/fixtures/stage-e01-core-adoption.json"
TID = "a" * 32
PID = 424242
JOURNAL = ".mir/slim-transaction.json"
QUARANTINE = ".mir/slim-quarantine/" + TID
REPORT = {"status": "applied", "transaction_id": TID}


def file(body, mode=0o644):
    raw = body if isinstance(body, bytes) else body.encode()
    return {"kind": "file", "hex": raw.hex(), "mode": mode}


def js(value):
    return file(json.dumps(value, sort_keys=True))


def journal(**changes):
    return {
        "schema_version": 1,
        "transaction_id": TID,
        "pid": PID,
        "status": "moving",
        "paths": ["provider/a", "provider/z"],
        **changes,
    }


def basic():
    return {".mir": {"kind": "dir", "mode": 0o755}}


def adopter():
    import hashlib

    files = basic()
    files[".mir/repo-profile.toml"] = file(
        '[repo]\nslug="product"\nrepository_type="code_app"\nprofile_base_commit="'
        + "b" * 40
        + '"\n'
    )
    files["config/adopter-boundary.json"] = js(
        {
            "schema_version": 1,
            "provider_markers": ["provider"],
            "provider_text_markers": [],
            "provider_owners": [
                {"slug": "mir-yoke", "repository_types": ["public_harness_template"]}
            ],
            "payload_manifest": "config/adopter-payload.json",
            "ephemeral_globs": ["provider/*.pyc"],
        }
    )
    files["config/adopter-payload.json"] = js(
        {
            "schema_version": 1,
            "files": [
                {"path": name, "sha256": hashlib.sha256(body).hexdigest(), "disposition": "remove"}
                for name, body in [("provider/z", b"last\n"), ("provider/a", b"first\xff\n")]
            ],
        }
    )
    files["provider/z"] = file(b"last\n", 0o755)
    files["provider/a"] = file(b"first\xff\n", 0o640)
    return files


def cases():
    out = []

    def add(name, operation, initial=None, value=None, options=None, steps=None):
        out.append(
            {
                "name": name,
                "initial": initial if initial is not None else basic(),
                "options": options or {},
                "steps": steps or [{"operation": operation, "input": value or {}}],
            }
        )

    for name, value in [
        ("empty", ""),
        ("null", None),
        ("integer", 1),
        ("backslash", "a\\b"),
        ("absolute", "/a"),
        ("parent", "a/../b"),
        ("dot", "."),
        ("dot_slash", "./a//b/"),
        ("unicode", "\uac00/\u03b1"),
        ("dotdot", ".."),
        ("ordinary", "a/b"),
        ("list", []),
    ]:
        add("safe_relative." + name, "safe_relative", value={"value": value})
    for name, body in [
        ("valid", '[repo]\nslug="sample"\n'),
        ("missing_repo", "version=1"),
        ("wrong_repo", 'repo="x"'),
        ("malformed", "[repo"),
        ("bare_cr", '[repo]\rslug="x"\r'),
        ("non_utf8", b"\xff"),
    ]:
        add("profile." + name, "load_profile", {**basic(), ".mir/repo-profile.toml": file(body)})
    add("profile.missing", "load_profile")
    boundary = json.loads(bytes.fromhex(adopter()["config/adopter-boundary.json"]["hex"]))
    for name, body in [
        ("valid", boundary),
        ("not_object", []),
        ("bad_version", {**boundary, "schema_version": 2}),
        ("empty_markers", {**boundary, "provider_markers": []}),
        ("markers_type", {**boundary, "provider_markers": "x"}),
        ("unsafe_marker", {**boundary, "provider_markers": ["../x"]}),
        ("text_type", {**boundary, "provider_text_markers": None}),
        ("text_entry", {**boundary, "provider_text_markers": [1]}),
        ("text_contains", {**boundary, "provider_text_markers": [{"path": "a", "contains": ""}]}),
        (
            "text_valid",
            {**boundary, "provider_text_markers": [{"path": "./a//b", "contains": "marker"}]},
        ),
    ]:
        add(
            "boundary." + name,
            "load_boundary",
            {**basic(), "config/adopter-boundary.json": js(body)},
        )
    for name, body in [("json", b"{"), ("non_utf8", b"\xff")]:
        add(
            "boundary." + name,
            "load_boundary",
            {**basic(), "config/adopter-boundary.json": file(body)},
        )
    add("boundary.missing", "load_boundary")
    for name, profile, b in [
        (
            "match",
            {"repo": {"slug": "mir-yoke", "repository_type": "public_harness_template"}},
            boundary,
        ),
        (
            "miss",
            {"repo": {"slug": "other", "repository_type": "public_harness_template"}},
            boundary,
        ),
        ("owners_type", {"repo": {}}, {"provider_owners": {}}),
        ("owner_skips", {"repo": {}}, {"provider_owners": [1, {}, {"repository_types": []}]}),
        ("missing_repo", {}, boundary),
        ("repo_list", {"repo": []}, boundary),
        (
            "numeric_equal",
            {"repo": {"slug": 1, "repository_type": True}},
            {"provider_owners": [{"slug": True, "repository_types": [1]}]},
        ),
        (
            "numeric_precision",
            {"repo": {"slug": 9007199254740993, "repository_type": "type"}},
            {"provider_owners": [{"slug": 9007199254740992.0, "repository_types": ["type"]}]},
        ),
    ]:
        add("owner." + name, "is_provider_owner", value={"profile": profile, "boundary": b})
    add("journal.missing", "load_journal")
    for name, raw in [
        ("valid", js(journal())),
        ("non_object", js([])),
        ("json", file("{")),
        ("non_utf8", file(b"\xff")),
        ("bad_id", js(journal(transaction_id="A" * 32))),
        ("paths_type", js(journal(paths="a"))),
        ("path_escape", js(journal(paths=["../a"]))),
        ("duplicate", js(journal(paths=["a", "a"]))),
        ("status_unchecked", js(journal(status="odd"))),
        ("directory", {"kind": "dir", "mode": 0o755}),
        ("symlink", {"kind": "symlink", "target": "../outside"}),
    ]:
        add("journal." + name, "load_journal", {**basic(), JOURNAL: raw})
    for name, entry in [
        ("new", None),
        ("existing", {"kind": "dir", "mode": 0o711}),
        ("file", file("occupied")),
        ("symlink", {"kind": "symlink", "target": "../outside"}),
    ]:
        initial = basic()
        if entry:
            initial[".mir/slim-quarantine"] = entry
        add("quarantine." + name, "quarantine_root", initial)
    # Crash images at journal publication, each completed rename, and verification publication.
    for moved in range(4):
        initial = adopter()
        initial[JOURNAL] = js(journal(status="verified" if moved == 3 else "moving"))
        initial[".mir/slim.lock"] = file(str(PID), 0o600)
        for name in ["provider/a", "provider/z"][:moved]:
            initial[QUARANTINE + "/" + name] = initial.pop(name)
        add(
            "recover.interrupted_" + str(moved),
            "recover",
            initial,
            steps=[{"operation": "recover", "input": {}}, {"operation": "recover", "input": {}}],
        )
    for mode in [
        "ambiguous",
        "missing",
        "unsafe_source",
        "unsafe_parent",
        "restore_denied",
        "reverse_order",
    ]:
        initial = {
            **basic(),
            JOURNAL: js(journal()),
            ".mir/slim.lock": file(str(PID), 0o600),
            QUARANTINE + "/provider/a": file(b"a\xff", 0o640),
            QUARANTINE + "/provider/z": file("z", 0o755),
        }
        options = {}
        if mode == "ambiguous":
            initial["provider/a"] = file("original")
        if mode == "missing":
            del initial[QUARANTINE + "/provider/a"]
        if mode == "unsafe_source":
            initial[QUARANTINE + "/provider/a"] = {
                "kind": "symlink",
                "target": "../../../../outside",
            }
        if mode == "unsafe_parent":
            initial["provider"] = {"kind": "symlink", "target": "../outside"}
        if mode == "restore_denied":
            options["deny_replace"] = "provider/z"
        add(
            "rollback_journal." + mode, "rollback_journal", initial, {"journal": journal()}, options
        )
    for mode in [
        "clean",
        "stale_lock",
        "bad_lock",
        "active_lock",
        "lock_symlink",
        "lock_directory",
        "receipt_commit",
        "receipt_wrong",
        "receipt_json",
        "receipt_non_utf8",
        "receipt_symlink",
        "receipt_list",
        "receipt_integer",
        "receipt_null",
        "active_journal",
    ]:
        initial = basic()
        options = {}
        if mode != "clean":
            initial[".mir/slim.lock"] = file("stale" if mode == "bad_lock" else str(PID), 0o600)
        if mode == "lock_symlink":
            initial[".mir/slim.lock"] = {"kind": "symlink", "target": "../outside"}
        if mode == "lock_directory":
            initial[".mir/slim.lock"] = {"kind": "dir", "mode": 0o755}
        if mode in ["active_lock", "active_journal"]:
            options["alive"] = True
        if mode.startswith("receipt") or mode == "active_journal":
            initial[JOURNAL] = js(journal(paths=[], status="verified"))
        if mode.startswith("receipt"):
            initial[".mir/bootstrap-receipt.json"] = js(
                {
                    "status": "ready",
                    "slim": {"transaction_id": TID if mode == "receipt_commit" else "b" * 32},
                }
            )
        if mode in ["receipt_list", "receipt_integer", "receipt_null"]:
            initial[".mir/bootstrap-receipt.json"] = js(
                {"receipt_list": [], "receipt_integer": 1, "receipt_null": None}[mode]
            )
        if mode == "receipt_json":
            initial[".mir/bootstrap-receipt.json"] = file("{")
        if mode == "receipt_non_utf8":
            initial[".mir/bootstrap-receipt.json"] = file(b"\xff")
        if mode == "receipt_symlink":
            initial[".mir/bootstrap-receipt.json"] = {"kind": "symlink", "target": "../outside"}
        add("recover." + mode, "recover", initial, options=options)
    for op in ["commit", "rollback"]:
        for mode in ["ignored", "missing_journal", "wrong_id", "moving", "verified"]:
            initial = {**basic(), ".mir/slim.lock": file(str(PID), 0o600)}
            if mode not in ["ignored", "missing_journal"]:
                initial[JOURNAL] = js(
                    journal(
                        transaction_id="b" * 32 if mode == "wrong_id" else TID,
                        paths=[],
                        status=mode,
                    )
                )
            add(op + "." + mode, op, initial, {"report": {} if mode == "ignored" else REPORT})
    for mode in [
        "success",
        "deferred_commit",
        "deferred_rollback",
        "verify_fail",
        "move_denied",
        "modified",
        "marker_conflict",
        "symlink",
        "cli_inside",
        "cli_missing",
        "preflight_fail",
        "release_changed",
        "preexisting_destination",
        "ephemeral",
        "already_slim",
        "already_fail",
        "text_non_utf8",
    ]:
        initial = adopter()
        options = {}
        inp = {"external_cli": "<external>", "defer_commit": mode.startswith("deferred")}
        if mode in ["verify_fail", "already_fail"]:
            options["verify_ready"] = False
        if mode == "move_denied":
            options["deny_replace"] = QUARANTINE + "/provider/z"
        if mode == "text_non_utf8":
            boundary = json.loads(bytes.fromhex(initial["config/adopter-boundary.json"]["hex"]))
            boundary["provider_text_markers"] = [{"path": "contract", "contains": "provider"}]
            initial["config/adopter-boundary.json"] = js(boundary)
            initial["contract"] = file(b"\xff")
        if mode == "modified":
            initial["provider/z"] = file("modified")
        if mode == "marker_conflict":
            initial["provider/owned"] = file("user")
        if mode == "symlink":
            initial["provider/a"] = {"kind": "symlink", "target": "../outside"}
        if mode == "cli_inside":
            initial["cli"] = file("cli", 0o755)
            inp["external_cli"] = "<root>/cli"
        if mode == "cli_missing":
            inp["external_cli"] = "<root>/absent"
        if mode == "preflight_fail":
            options["preflight_fail"] = True
        if mode == "release_changed":
            options["release_changed"] = True
        if mode == "preexisting_destination":
            initial[QUARANTINE + "/provider/z"] = file("preexisting", 0o600)
        if mode == "ephemeral":
            initial["provider/cache.pyc"] = file(b"\x00cache", 0o600)
        if mode.startswith("already"):
            del initial["provider/a"], initial["provider/z"]
        steps = [{"operation": "apply", "input": inp}]
        if mode.startswith("deferred"):
            steps.append(
                {
                    "operation": "commit" if mode.endswith("commit") else "rollback",
                    "input": {"report": REPORT},
                }
            )
        add("apply." + mode, "apply", initial, options=options, steps=steps)
    # Admission and payload refusal permutations share the real apply route.
    for mode in [
        "missing",
        "json",
        "non_utf8",
        "object",
        "schema_version",
        "files_type",
        "entry_type",
        "duplicate",
        "digest",
        "digest_unicode",
        "disposition",
        "disposition_list",
        "disposition_dict",
        "path_escape",
    ]:
        initial = adopter()
        payload = json.loads(bytes.fromhex(initial["config/adopter-payload.json"]["hex"]))
        if mode == "missing":
            del initial["config/adopter-payload.json"]
        elif mode in ["json", "non_utf8"]:
            initial["config/adopter-payload.json"] = file(b"{" if mode == "json" else b"\xff")
        else:
            if mode == "object":
                payload = []
            elif mode == "schema_version":
                payload["schema_version"] = 2
            elif mode == "files_type":
                payload["files"] = {}
            elif mode == "entry_type":
                payload["files"] = [1]
            elif mode == "duplicate":
                payload["files"].append(payload["files"][0])
            elif mode == "digest":
                payload["files"][0]["sha256"] = "short"
            elif mode == "digest_unicode":
                payload["files"][0]["sha256"] = "\u00e9" * 64
            elif mode.startswith("disposition"):
                payload["files"][0]["disposition"] = {
                    "disposition": "unknown",
                    "disposition_list": [],
                    "disposition_dict": {},
                }[mode]
            elif mode == "path_escape":
                payload["files"][0]["path"] = "../escape"
            initial["config/adopter-payload.json"] = js(payload)
        add("apply.payload_" + mode, "apply", initial, {"external_cli": "<external>"})
    for mode in [
        "not_object",
        "invalid_json",
        "command_error",
        "readonly_evidence",
        "changed_paths",
    ]:
        options = {}
        if mode == "not_object":
            options["verify_stdout"] = "[]"
        elif mode == "invalid_json":
            options["verify_stdout"] = "{"
        elif mode == "command_error":
            options["verify_returncode"] = 3
        elif mode == "readonly_evidence":
            options["verify_stdout"] = json.dumps(
                {
                    "ready": True,
                    "change_evidence": {
                        "status": "not-applicable",
                        "reason": "read-only-operation",
                    },
                }
            )
        elif mode == "changed_paths":
            options["verify_stdout"] = json.dumps({"ready": True, "changed_paths": ["changed"]})
        add("apply.verify_" + mode, "apply", adopter(), {"external_cli": "<external>"}, options)
    for mode, system in [("windows", "Windows"), ("unknown", "Other")]:
        add("platform." + mode, "recover", options={"platform": system})
    for mode, entry in [
        ("missing", None),
        ("symlink", {"kind": "symlink", "target": "../outside"}),
        ("file", file("occupied")),
    ]:
        add("recover.mir_" + mode, "recover", {} if entry is None else {".mir": entry})
    add(
        "recover.pid_bool",
        "recover",
        {**basic(), JOURNAL: js(journal(paths=[], pid=True))},
        options={"alive": True},
    )
    add("recover.lock_huge_pid", "recover", {**basic(), ".mir/slim.lock": file("9" * 30)})
    add("recover.lock_digit_limit", "recover", {**basic(), ".mir/slim.lock": file("9" * 5000)})
    add("recover.lock_invalid_utf8", "recover", {**basic(), ".mir/slim.lock": file(b"\xff")})
    for kind in ["boundary", "payload"]:
        for mode in ["missing", "json", "valid", "error"]:
            initial = adopter()
            name = "config/adopter-" + kind + ".json"
            payload = json.loads(bytes.fromhex(initial[name]["hex"]))
            payload["$schema"] = "adopter-schema.json"
            initial[name] = js(payload)
            if mode != "missing":
                initial["config/adopter-schema.json"] = file("{" if mode == "json" else "{}")
            add(
                "schema." + kind + "_" + mode,
                "load_boundary" if kind == "boundary" else "apply",
                initial,
                {"external_cli": "<external>"},
                {"schema_error": mode == "error"},
            )
    for mode in [
        "owner",
        "canonical_fallback",
        "text_marker",
        "ephemeral_type",
        "no_marker",
        "no_marker_unsafe",
    ]:
        initial = adopter()
        boundary = json.loads(bytes.fromhex(initial["config/adopter-boundary.json"]["hex"]))
        if mode in ["owner", "canonical_fallback"]:
            initial[".mir/repo-profile.toml"] = file(
                '[repo]\nslug="mir-yoke"\nrepository_type="public_harness_template"\n'
                + ('profile_base_commit="' + "b" * 40 + '"\n' if mode == "owner" else "")
            )
        if mode == "text_marker":
            boundary["provider_text_markers"] = [{"path": "contract", "contains": "provider"}]
            initial["contract"] = file("provider")
        if mode == "ephemeral_type":
            boundary["ephemeral_globs"] = "wrong"
        if mode.startswith("no_marker"):
            boundary["provider_markers"] = ["absent"]
        if mode == "no_marker_unsafe":
            initial["provider/a"] = {"kind": "symlink", "target": "../../external-cli"}
        initial["config/adopter-boundary.json"] = js(boundary)
        add("apply." + mode, "apply", initial, {"external_cli": "<external>"})
    for value in [[], {}]:
        initial = adopter()
        initial[".mir/repo-profile.toml"] = file(
            '[repo]\nslug="mir-yoke"\nrepository_type='
            + ("[]" if isinstance(value, list) else "{}")
            + "\n"
        )
        add(
            "apply.canonical_unhashable_" + type(value).__name__,
            "apply",
            initial,
            {"external_cli": "<external>"},
        )
    for mode, extension in [
        ("nonfinite", float("nan")),
        ("large_integer", 2**80),
        ("surrogate", "\ud800"),
        ("deep", [[[[0]]]]),
    ]:
        if mode == "deep":
            extension = 0
            for _ in range(140):
                extension = [extension]
        initial = adopter()
        payload = json.loads(bytes.fromhex(initial["config/adopter-payload.json"]["hex"]))
        payload["extension"] = extension
        initial["config/adopter-payload.json"] = js(payload)
        initial[".mir/slim.lock"] = file("stale", 0o600)
        add("unsupported.payload_" + mode, "apply", initial, {"external_cli": "<external>"})
        out[-1]["native_decline"] = "Python-only JSON value outside native JSON subset"
    for mode, expression in [
        ("nan", "nan"),
        ("inf", "inf"),
        ("datetime", "2000-01-01T00:00:00Z"),
        ("large_integer", str(2**80)),
    ]:
        initial = adopter()
        initial[".mir/repo-profile.toml"]["hex"] += (
            ("extension=" + expression + "\n").encode().hex()
        )
        initial[".mir/slim.lock"] = file("stale", 0o600)
        add("unsupported.toml_" + mode, "apply", initial, {"external_cli": "<external>"})
        out[-1]["native_decline"] = "Python-only TOML value outside native JSON subset"
    initial = {
        **basic(),
        "protected": {"kind": "dir", "mode": 0o555},
        JOURNAL: js(journal(paths=["a", "protected/sub/z"])),
        ".mir/slim.lock": file(str(PID), 0o600),
        QUARANTINE + "/protected/sub/z": file("protected", 0o640),
        QUARANTINE + "/a": file(b"a\xff", 0o755),
    }
    add(
        "rollback_journal.mkdir_permission",
        "rollback_journal",
        initial,
        {"journal": journal(paths=["a", "protected/sub/z"])},
    )
    initial = adopter()
    del initial["provider/a"], initial["provider/z"]
    initial["provider"] = {"kind": "dir", "mode": 0}
    initial[".mir/slim.lock"] = file("stale", 0o600)
    add("unsupported.unreadable_marker", "apply", initial, {"external_cli": "<external>"})
    out[-1]["native_decline"] = (
        "Unreadable marker directory requires Python fallback before effects"
    )
    for mode, extension in [
        ("nonfinite", float("nan")),
        ("large_integer", 2**80),
        ("surrogate", "\ud800"),
        ("deep", None),
    ]:
        if mode == "deep":
            extension = 0
            for _ in range(140):
                extension = [extension]
        output = json.dumps({"ready": True, "changed_paths": [], "extension": extension})
        add(
            "apply.verify_output_" + mode,
            "apply",
            adopter(),
            {"external_cli": "<external>"},
            {"verify_stdout": output},
        )
    initial = adopter()
    boundary = json.loads(bytes.fromhex(initial["config/adopter-boundary.json"]["hex"]))
    boundary["provider_markers"] = [None]
    initial["config/adopter-boundary.json"] = js(boundary)
    add("boundary.invalid_scalar", "load_boundary", initial)
    for mode, options in [
        ("git_failure", {"git_returncode": 1}),
        ("release_read_failure", {"git_remove_control": "config/adopter-boundary.json"}),
        ("marker_disappears", {"preflight_action": "remove_marker"}),
        ("lock_race", {"preflight_action": "create_lock"}),
        ("unsafe_before_move", {"journal_action": "unsafe_source"}),
        ("changed_before_move", {"journal_action": "changed_source"}),
        ("unsafe_quarantine_parent", {"journal_action": "unsafe_parent"}),
        ("first_journal_failure", {"deny_journal_at": 1}),
        ("verified_journal_failure", {"deny_journal_at": 2}),
        ("verify_stderr", {"verify_returncode": 2, "verify_stderr": "status denied"}),
        ("verify_integer_ready", {"verify_stdout": '{"ready":1,"changed_paths":[]}'}),
    ]:
        add("apply." + mode, "apply", adopter(), {"external_cli": "<external>"}, options)
    for mode in ["file", "symlink"]:
        initial = adopter()
        boundary = json.loads(bytes.fromhex(initial["config/adopter-boundary.json"]["hex"]))
        boundary["provider_markers"] = ["provider/a"]
        initial["config/adopter-boundary.json"] = js(boundary)
        if mode == "symlink":
            initial["provider/a"] = {"kind": "symlink", "target": "../outside"}
        add("apply.marker_" + mode, "apply", initial, {"external_cli": "<external>"})
    initial = adopter()
    initial["provider/empty"] = {"kind": "dir", "mode": 0o755}
    add("apply.remaining_empty_marker", "apply", initial, {"external_cli": "<external>"})
    initial = adopter()
    del initial["config/adopter-boundary.json"]
    add("apply.boundary_error", "apply", initial, {"external_cli": "<external>"})
    add("quarantine.mkdir_permission", "quarantine_root", {".mir": {"kind": "dir", "mode": 0o555}})
    ambiguous = next(row for row in out if row["name"] == "rollback_journal.ambiguous")
    for operation in ["recover", "rollback"]:
        add(
            operation + ".incomplete",
            operation,
            json.loads(json.dumps(ambiguous["initial"])),
            {"report": REPORT},
        )
    for mode, pid, options in [("zero", 0, {}), ("permission", PID, {"alive_permission": True})]:
        add(
            "recover.pid_" + mode,
            "recover",
            {**basic(), JOURNAL: js(journal(paths=[], pid=pid))},
            options=options,
        )
    add(
        "rollback_journal.parent_lstat_permission",
        "rollback_journal",
        {
            **basic(),
            "protected": {"kind": "dir", "mode": 0},
            JOURNAL: js(journal(paths=["protected/sub/z"])),
            QUARANTINE + "/protected/sub/z": file("protected"),
        },
        {"journal": journal(paths=["protected/sub/z"])},
    )
    for operation in ["commit", "rollback"]:
        initial = {
            **basic(),
            JOURNAL: js(journal(status="verified")),
            ".mir/slim.lock": file(str(PID), 0o600),
            QUARANTINE + "/provider/a": file(b"a\xff", 0o640),
            QUARANTINE + "/provider/z": file("z", 0o755),
        }
        initial[".mir"]["mode"] = 0o555
        add(operation + ".unlink_permission", operation, initial, {"report": REPORT})
    for operation, phase in [
        ("write", "lock"),
        ("fsync", "lock"),
        ("write", "journal-file"),
        ("fsync", "journal-file"),
        ("fsync", "journal-directory"),
    ]:
        for occurrence in [1] if phase == "lock" else [1, 2]:
            add(
                "apply.fd_" + operation + "_" + phase + "_" + str(occurrence),
                "apply",
                adopter(),
                {"external_cli": "<external>"},
                {
                    "fd_fail": {
                        "operation": operation,
                        "phase": phase,
                        "at": occurrence,
                        "errno": 28 if operation == "write" else 5,
                    }
                },
            )
    add(
        "recover.lock_target_permission",
        "recover",
        {
            **basic(),
            "protected": {"kind": "dir", "mode": 0},
            ".mir/slim.lock": {"kind": "symlink", "target": "../protected/pid"},
        },
    )
    add("recover.mir_permission", "recover", {".mir": {"kind": "dir", "mode": 0}})
    add(
        "profile.symlink_loop",
        "load_profile",
        {**basic(), ".mir/repo-profile.toml": {"kind": "symlink", "target": "repo-profile.toml"}},
    )
    add(
        "boundary.symlink_loop",
        "load_boundary",
        {
            **basic(),
            "config/adopter-boundary.json": {"kind": "symlink", "target": "adopter-boundary.json"},
        },
    )
    initial = adopter()
    initial["provider/link"] = {"kind": "symlink", "target": "../../outside/secret"}
    add(
        "apply.nested_symlink_target_permission",
        "apply",
        initial,
        {"external_cli": "<external>"},
        {"outside_permission": True},
    )
    for mode in ["root", "siblings"]:
        initial = adopter()
        if mode == "root":
            initial["provider/z_dir"] = {"kind": "dir", "mode": 0o755}
            initial["provider/z_dir/child"] = {
                "kind": "symlink",
                "target": "../../../outside/secret",
            }
            initial["provider/a_link"] = {"kind": "symlink", "target": "../../outside/secret"}
        else:
            initial["provider/a_dir"] = {"kind": "dir", "mode": 0o755}
            initial["provider/b_dir"] = {"kind": "dir", "mode": 0o755}
            initial["provider/b_dir/sub"] = {"kind": "dir", "mode": 0o755}
            initial["provider/b_dir/sub/child"] = {
                "kind": "symlink",
                "target": "../../../../outside/secret",
            }
            initial["provider/a_dir/link"] = {
                "kind": "symlink",
                "target": "../../../outside/secret",
            }
        add(
            "apply.rglob_order_" + mode,
            "apply",
            initial,
            {"external_cli": "<external>"},
            {"outside_permission": True},
        )
    initial = adopter()
    initial["provider/cache\\name.pyc"] = file(b"cache\x00", 0o600)
    add("apply.literal_backslash_filename", "apply", initial, {"external_cli": "<external>"})
    initial = adopter()
    initial[".mir/repo-profile.toml"] = file("[repo]\nx=")
    initial[".mir/slim.lock"] = file("stale", 0o600)
    add("unsupported.toml_unmapped", "apply", initial, {"external_cli": "<external>"})
    out[-1]["native_decline"] = "Unmapped TOML diagnostic requires Python fallback before effects"
    add("apply.double_slash_cli", "apply", adopter(), {"external_cli": "/<external>"})
    for operation in ["commit", "rollback"]:
        for mode, report in [("null", None), ("list", [])]:
            add(operation + ".report_" + mode, operation, value={"report": report})
    add(
        "rollback_journal.numeric_path",
        "rollback_journal",
        {**basic(), JOURNAL: js(journal(paths=[7])), ".mir/slim.lock": file(str(PID), 0o600)},
        {"journal": journal(paths=[7])},
    )
    initial = adopter()
    initial[".mir"]["mode"] = 0o555
    initial[".mir/slim-quarantine"] = {"kind": "dir", "mode": 0o700}
    add("apply.lock_permission", "apply", initial, {"external_cli": "<external>"})
    for race in [
        "source",
        "destination",
        "source_leaf",
        "rollback",
        "rollback_source",
        "recovery",
        "recovery_source",
    ]:
        initial = (
            adopter()
            if race in {"source", "destination", "source_leaf"}
            else {
                **basic(),
                JOURNAL: js(journal()),
                ".mir/slim.lock": file(str(PID), 0o600),
                QUARANTINE + "/provider/a": file(b"first\xff\n"),
                QUARANTINE + "/provider/z": file(b"last\n"),
                "provider": {"kind": "dir", "mode": 0o755},
            }
        )
        operation = (
            "apply"
            if race in {"source", "destination", "source_leaf"}
            else ("recover" if race.startswith("recovery") else "rollback")
        )
        add(
            "race." + race,
            operation,
            initial,
            {"external_cli": "<external>", "report": REPORT},
            {"race": race},
        )
    return out


def private_cases():
    rows = [
        {
            "name": name,
            "initial": basic(),
            "options": {},
            "steps": [{"operation": operation, "input": {"path": path, "label": "lexical"}}],
        }
        for name, operation, path in [
            ("safe_file.lexical_escape", "private_safe_file", "<outside>"),
            ("safe_directory.lexical_escape", "private_safe_directory", "<outside>"),
            ("safe_parent.lexical_escape", "private_safe_parent", "<outside>"),
            ("safe_directory.unavailable", "private_safe_directory", "<root>/missing"),
        ]
    ]
    rows.append(
        {
            "name": "safe_parent.lstat_failure",
            "initial": {**basic(), "node": {"kind": "dir", "mode": 0o755}},
            "options": {},
            "steps": [
                {
                    "operation": "private_safe_parent_lstat_failure",
                    "input": {"path": "<root>/node", "label": "lexical"},
                }
            ],
        }
    )
    return rows


def populate(root, entries):
    root.mkdir(parents=True)
    permissions = []
    for name, entry in sorted(entries.items(), key=lambda pair: (pair[0].count("/"), pair[0])):
        path = root / name.replace("<byte-ff>", "\udcff")
        path.parent.mkdir(parents=True, exist_ok=True)
        if entry["kind"] == "dir":
            path.mkdir(exist_ok=True)
        elif entry["kind"] == "symlink":
            path.symlink_to(entry["target"])
            continue
        else:
            path.write_bytes(bytes.fromhex(entry["hex"]))
        permissions.append((path, entry["mode"]))
    for path, mode in reversed(permissions):
        path.chmod(mode)


def snapshot(root):
    rows = {}

    def walk(directory):
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return
        for path in entries:
            name = path.relative_to(root).as_posix().replace("\udcff", "<byte-ff>")
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                rows[name] = {"kind": "symlink", "target": os.readlink(path)}
            elif stat.S_ISDIR(mode):
                rows[name] = {"kind": "dir", "mode": stat.S_IMODE(mode)}
                walk(path)
            else:
                rows[name] = file(path.read_bytes(), stat.S_IMODE(mode))

    walk(root)
    return rows


def record(case, base, boundary, slim):
    root = base / case["name"] / "project"
    external = root.parent / "external-cli"
    populate(root, case["initial"])
    external.write_text("synthetic cli")
    external.chmod(0o755)
    outside = root.parent / "outside"
    outside.mkdir()
    if case["options"].get("outside_permission"):
        (outside / "secret").write_text("outside")
        outside.chmod(0)
    if case["options"].get("race"):
        for name in ["a", "z"]:
            (outside / name).write_bytes(("OUTSIDE-" + name.upper()).encode())
    swapped = False

    def before_move(_root, source, destination):
        nonlocal swapped
        race = case["options"].get("race", "")
        if destination.name == "slim-transaction.json" or not race or swapped:
            return
        swapped = True
        if race == "source_leaf":
            source.unlink()
            source.symlink_to(os.path.relpath(outside / "a", source.parent))
            return
        parent = (
            source.parent
            if race in {"source", "rollback_source", "recovery_source"}
            else destination.parent
        )
        real_rename(parent, parent.with_name(parent.name + "-saved"))
        parent.symlink_to(os.path.relpath(outside, parent.parent))

    events = []

    def normalize(value):
        if isinstance(value, Path):
            value = str(value)
        if isinstance(value, str):
            return (
                value.replace(str(external), "<external>")
                .replace(str(root), "<root>")
                .replace("\udcff", "<byte-ff>")
                .replace(f"[Errno {errno.ELOOP}]", "[Errno <ELOOP>]")
            )
        if isinstance(value, list):
            return [normalize(x) for x in value]
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        return value

    real_replace = os.replace
    real_rename = os.rename
    fd_paths = {}
    journal_calls = 0
    fd_phases = {}
    fd_counts = {}
    real_open, real_fdopen, real_fsync = os.open, os.fdopen, os.fsync

    def fd_event(operation, phase):
        key = (operation, phase)
        occurrence = fd_counts[key] = fd_counts.get(key, 0) + 1
        events.append(["fd", operation, phase, occurrence])
        fail = case["options"].get("fd_fail", {})
        if (fail.get("operation"), fail.get("phase"), fail.get("at")) == (
            operation,
            phase,
            occurrence,
        ):
            number = fail.get("errno", 5)
            raise OSError(number, os.strerror(number))

    def open_fd(path, *args, **kwargs):
        descriptor = real_open(path, *args, **kwargs)
        path = Path(path)
        if kwargs.get("dir_fd") is not None:
            path = fd_paths[kwargs["dir_fd"]] / path
        fd_paths[descriptor] = path
        if path == root / ".mir/slim.lock":
            fd_phases[descriptor] = "lock"
        elif path == root / ".mir":
            fd_phases[descriptor] = "journal-directory"
        elif path.name.startswith(".slim-transaction.json."):
            fd_phases[descriptor] = "journal-file"
        return descriptor

    class RecordingHandle:
        def __init__(self, inner, phase):
            self.inner, self.phase, self.started = inner, phase, False

        def __enter__(self):
            self.inner.__enter__()
            return self

        def __exit__(self, *args):
            return self.inner.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def write(self, text):
            if not self.started:
                self.started = True
                fd_event("write", self.phase)
            return self.inner.write(text)

    def fdopen(descriptor, *args, **kwargs):
        inner = real_fdopen(descriptor, *args, **kwargs)
        return RecordingHandle(inner, fd_phases[descriptor])

    def fsync(descriptor):
        fd_event("fsync", fd_phases[descriptor])
        return real_fsync(descriptor)

    def rename(source, destination, *, src_dir_fd, dst_dir_fd):
        return replace(
            fd_paths[src_dir_fd] / source,
            fd_paths[dst_dir_fd] / destination,
            relative=(source, destination, src_dir_fd, dst_dir_fd),
        )

    def replace(source, destination, relative=None):
        nonlocal journal_calls
        src, dst = normalize(source), normalize(destination)
        if Path(destination).name == "slim-transaction.json":
            src = "<journal-temp>"
            journal_calls += 1
        events.append(["replace", src, dst])
        if (
            normalize(destination) == "<root>/" + case["options"].get("deny_replace", "!")
            or Path(destination).name == "slim-transaction.json"
            and journal_calls == case["options"].get("deny_journal_at")
        ):
            raise PermissionError(13, "Permission denied", str(destination))
        if relative is None:
            real_replace(source, destination)
        else:
            src, dst, src_fd, dst_fd = relative
            real_rename(src, dst, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
        if Path(destination).name == "slim-transaction.json" and journal_calls == 1:
            action = case["options"].get("journal_action")
            if action == "unsafe_source":
                (root / "provider").mkdir(exist_ok=True)
                (root / "provider/a").unlink(missing_ok=True)
                (root / "provider/a").symlink_to("../outside")
            elif action == "changed_source":
                (root / "provider").mkdir(exist_ok=True)
                (root / "provider/a").write_bytes(b"changed")
            elif action == "unsafe_parent":
                parent = root / QUARANTINE
                parent.mkdir(parents=True, exist_ok=True)
                if not (parent / "provider").exists():
                    (parent / "provider").symlink_to("../../../../outside")

    release = {
        name: (root / name).read_bytes()
        for name in ["config/adopter-boundary.json", "config/adopter-payload.json"]
        if (root / name).is_file()
    }

    def run(argv, **kwargs):
        events.append(["run", normalize(argv)])
        if argv[0] == "git":
            path = argv[2].split(":", 1)[1]
            if path == case["options"].get("git_remove_control"):
                (root / path).unlink()
            return SimpleNamespace(
                returncode=case["options"].get("git_returncode", 0),
                stdout=b"changed" if case["options"].get("release_changed") else release[path],
                stderr=b"",
            )
        if argv[1] == "bootstrap":
            if case["options"].get("preflight_action") == "remove_marker":
                shutil.rmtree(root / "provider")
            elif case["options"].get("preflight_action") == "create_lock":
                (root / ".mir/slim.lock").write_text("race")
                (root / ".mir/slim.lock").chmod(0o600)
            return SimpleNamespace(
                returncode=1 if case["options"].get("preflight_fail") else 0,
                stdout="",
                stderr="preflight denied",
            )
        return SimpleNamespace(
            returncode=case["options"].get("verify_returncode", 0),
            stdout=case["options"].get(
                "verify_stdout",
                json.dumps(
                    {"ready": case["options"].get("verify_ready", True), "changed_paths": []}
                ),
            ),
            stderr=case["options"].get("verify_stderr", ""),
        )

    def kill(pid, signal):
        if pid > sys.maxsize:
            raise OverflowError("Python int too large to convert to C long")
        if case["options"].get("alive_permission"):
            raise PermissionError(13, "Permission denied")
        if not case["options"].get("alive"):
            raise ProcessLookupError()

    observed = []
    lines = set()

    def trace(frame, event, _arg):
        filename = frame.f_code.co_filename
        if event == "line" and filename in [boundary.__file__, slim.__file__]:
            lines.add(Path(filename).name + ":" + str(frame.f_lineno))
        return trace

    previous_trace = sys.gettrace()
    sys.settrace(trace)
    real_validate = slim.jsonschema.validate

    def validate(*args, **kwargs):
        if case["options"].get("schema_error"):
            raise slim.jsonschema.ValidationError("schema denied")
        return real_validate(*args, **kwargs)

    with (
        mock.patch.object(slim.jsonschema, "validate", side_effect=validate),
        mock.patch.object(
            slim.platform, "system", return_value=case["options"].get("platform", "Darwin")
        ),
        mock.patch.dict(os.environ, {"HOME": str(base / "home")}),
        mock.patch.object(slim.uuid, "uuid4", return_value=SimpleNamespace(hex=TID)),
        mock.patch.object(slim.os, "getpid", return_value=PID),
        mock.patch.object(slim.os, "kill", side_effect=kill),
        mock.patch.object(slim, "_before_move", side_effect=before_move),
        mock.patch.object(slim.os, "replace", side_effect=replace),
        mock.patch.object(slim.os, "rename", side_effect=rename),
        mock.patch.object(slim.os, "open", side_effect=open_fd),
        mock.patch.object(slim.os, "fdopen", side_effect=fdopen),
        mock.patch.object(slim.os, "fsync", side_effect=fsync),
        mock.patch.object(slim.subprocess, "run", side_effect=run),
    ):
        for step in case["steps"]:
            inp = step["input"]
            op = step["operation"]
            events.clear()
            try:
                if op == "safe_relative":
                    value = slim._safe_relative(inp.get("value"))
                elif op == "load_profile":
                    value = boundary.load_profile(root)
                elif op == "load_boundary":
                    value = boundary.load_boundary(root)
                elif op == "is_provider_owner":
                    value = boundary.is_provider_owner(inp["profile"], inp["boundary"])
                elif op == "quarantine_root":
                    value = slim._ensure_quarantine_root(root)
                elif op == "load_journal":
                    value = slim._load_journal(root)
                elif op == "rollback_journal":
                    value = slim._rollback_journal(root, inp["journal"])
                elif op == "apply":
                    cli = Path(
                        inp["external_cli"]
                        .replace("<external>", str(external))
                        .replace("<root>", str(root))
                    )
                    value = slim.apply_adopter_slim(
                        root, external_cli=cli, defer_commit=inp.get("defer_commit", False)
                    )
                elif op == "recover":
                    value = slim.recover_adopter_slim(root)
                elif op == "commit":
                    value = slim.commit_adopter_slim(root, inp["report"])
                elif op == "rollback":
                    value = slim.rollback_adopter_slim(root, inp["report"])
                elif op.startswith("private_"):
                    path = Path(
                        inp["path"]
                        .replace("<root>", str(root))
                        .replace("<outside>", str(root.parent / "outside"))
                    )
                    if op == "private_safe_file":
                        value = slim._is_safe_project_file(root, path)
                    elif op == "private_safe_parent":
                        value = slim._safe_parent_for_restore(root, path)
                    elif op == "private_safe_parent_lstat_failure":
                        original_lstat = slim.os.lstat

                        def denied_lstat(
                            candidate, *args, _path=path, _lstat=original_lstat, **kwargs
                        ):
                            if Path(candidate) == _path:
                                raise PermissionError(13, "Permission denied", str(candidate))
                            return _lstat(candidate, *args, **kwargs)

                        with mock.patch.object(slim.os, "lstat", side_effect=denied_lstat):
                            value = slim._safe_parent_for_restore(root, path)
                    else:
                        value = slim._validated_project_directory(root, path, label=inp["label"])
                else:
                    raise AssertionError(op)
                result = {"value": normalize(value)}
            except Exception as exc:  # noqa: BLE001 - capture the independent oracle
                result = {"error": [type(exc).__name__, normalize(str(exc))]}
            observed.append({"result": result, "events": list(events), "tree": snapshot(root)})
    if case["options"].get("race"):
        assert swapped, "race seam was not reached"
        assert snapshot(outside) == {name: file("OUTSIDE-" + name.upper()) for name in ["a", "z"]}
        assert any("unsafe slim move" in str(row["result"]) for row in observed), observed
    outside.chmod(0o755)
    sys.settrace(previous_trace)
    return {**case, "expected": observed, "reference_lines": sorted(lines)}


def generate(scratch):
    # Never import the checkout's Python implementation as the reference.
    archive = subprocess.check_output(["git", "archive", PIN, "src"], cwd=REPO)
    reference = scratch / "pinned-reference"
    reference.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(reference, filter="data")
    # Commit-free pin: overlay only content-addressed patched reference files on git archive.
    for name, digest in REFERENCE_PATCH.items():
        body = (REPO / name).read_bytes()
        assert hashlib.sha256(body).hexdigest() == digest, name
        (reference / name).write_bytes(body)
    sys.path.insert(0, str(reference / "src"))
    from mir.core.adoption import boundary, slim

    assert Path(slim.__file__).is_relative_to(reference)
    run_dir = scratch / "records"
    if run_dir.exists():
        for parent, directories, _files in os.walk(run_dir):
            for name in directories:
                path = Path(parent) / name
                if not path.is_symlink():
                    path.chmod(0o755)
        shutil.rmtree(run_dir)
    run_dir.mkdir()
    old_umask = os.umask(0o022)
    try:
        helpers = [record(case, run_dir, boundary, slim) for case in private_cases()]
        return {
            "reference": PIN,
            "reference_patch": REFERENCE_PATCH,
            "records": [record(case, run_dir, boundary, slim) for case in cases()],
            "private_helpers": [
                {
                    "name": row["name"],
                    "initial": row["initial"],
                    "operation": row["steps"][0]["operation"],
                    "input": row["steps"][0]["input"],
                    "expected": row["expected"][0]["result"],
                    "reference_lines": row["reference_lines"],
                }
                for row in helpers
            ],
        }
    finally:
        os.umask(old_umask)


def test_oracle_is_complete_and_pinned():
    frozen = json.loads(FIXTURE.read_text())
    assert frozen["reference"] == PIN
    assert frozen["reference_patch"] == REFERENCE_PATCH
    for name, digest in REFERENCE_PATCH.items():
        assert hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest
    assert [row["name"] for row in frozen["records"]] == [case["name"] for case in cases()]
    assert all(len(row["steps"]) == len(row["expected"]) for row in frozen["records"])
    assert [row["name"] for row in frozen["private_helpers"]] == [
        case["name"] for case in private_cases()
    ]


def source_function(name):
    source = (REPO / "native/handoff-packet/src/mir_cli/bootstrap_core_adoption.rs").read_text()
    body = source.split("fn " + name + "(", 1)[1]
    return body.split("\nfn ", 1)[0].split("\npub", 1)[0]


def test_subset_admission_precedes_recovery_effects():
    apply = source_function("apply_adopter_slim")
    assert apply.index("admit_path(external)?") < apply.index("slim_root(root, host)?")
    assert apply.index("preflight_inputs(&root)?") < apply.index("recover(&root, host)?")
    recover = source_function("core_adoption_operation").split('"recover" =>', 1)[1]
    assert recover.index("admit_path(&root)?") < recover.index("recover(&root, host)")
    direct = source_function("core_adoption_operation").split('"rollback_journal" =>', 1)[1]
    direct = direct.split('"recover" =>', 1)[0]
    assert direct.index("admit_direct_rollback(") < direct.index("rollback_journal(root")
    preflight = source_function("preflight_inputs")
    assert "check_marker_names(&root.join(relative))?" in preflight
    assert "admit_path(&path)?" in source_function("check_marker_names")
    assert "path.to_str().ok_or_else(outside_subset)" in source_function("admit_path")
    marker = source_function("check_marker_names")
    assert "fs::read_dir(&path).map_err(|_| outside_subset())?" in marker
    assert "entry.map_err(|_| outside_subset())?.path()" in marker


def test_readers_preserve_python_json_text_and_profile_boundaries():
    source = (REPO / "native/handoff-packet/src/mir_cli/bootstrap_core_adoption.rs").read_text()
    assert "serde_json::from_" not in source
    assert "read_to_string" not in source
    assert ".trim(" not in source
    parser = source_function("parse_json")
    assert "crate::python_json::parse(text)" in parser
    assert parser.index("if supported") < parser.index("value.to_serde()")
    assert "parse_json(&read_text(path)?)" in source_function("json_text")
    assert "authored::decode(fs::read(path)" in source_function("read_text")
    profile = source_function("load_profile")
    unmapped = profile.index('if message == "unmapped TOML parse error" {')
    assert unmapped < profile.index('Error::new("TOMLDecodeError", message)')
    assert profile.index("fs::read(&path)") < profile.index("bootstrap_adoption::decode(bytes)")
    assert profile.index("admit_profile(&profile)?") < profile.index(
        "serde_json::to_value(profile)"
    )


def test_schema_preflight_reads_one_declared_schema_only():
    schema = source_function("preflight_schema")
    assert schema.count("preflight_value(") == 1
    assert "preflight_schema(" not in schema
    assert "jsonschema" not in schema


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    data = generate(args.scratch.resolve())
    if args.write:
        FIXTURE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    else:
        assert data == json.loads(FIXTURE.read_text())
    print(f"{len(data['records'])} pinned core adoption records")
