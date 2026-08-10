from __future__ import annotations

import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _runtime_id(project: Path, source_url: str, source_commit: str) -> str:
    return sha256(
        f"{project.resolve()}\n{source_url}\n{source_commit}\n".encode()
    ).hexdigest()[:24]


def _write_fake_runtime_manifest(runtime_root: Path) -> tuple[Path, str]:
    manifest = runtime_root / "runtime-manifest.json"
    manifest.write_text('{"schema_version":1,"entries":[]}\n', encoding="utf-8")
    return manifest, sha256(manifest.read_bytes()).hexdigest()


_FAKE_MANIFEST_CREATE = (
    'if [ "$1 $2" = "runtime-manifest create" ]; then\n'
    "  shift 2\n"
    "  while [ $# -gt 0 ]; do\n"
    '    if [ "$1" = "--manifest" ]; then shift; '
    'printf \'%s\\n\' \'{"schema_version":1,"entries":[]}\' > "$1"; exit 0; fi\n'
    "    shift\n"
    "  done\n"
    "  exit 2\n"
    "fi\n"
)


def test_shell_wrapper_is_thin_and_valid_bash():
    wrapper = ROOT / "setup.sh"
    body = wrapper.read_text(encoding="utf-8")

    assert "uv sync --project" not in body
    assert "uv tool install --force --link-mode copy" in body
    assert 'TOOL_SOURCE="git+$SOURCE_URL@$SOURCE_COMMIT"' in body
    assert '--constraints "$ROOT/config/cli-runtime-constraints.txt"' in body
    assert '.mir/capability-lock.json' in body
    assert '.mir/cli-runtime-lock.json' not in body
    assert '"$MIR_CLI" bootstrap --project-root "$ROOT" "$@"' in body
    assert "--storage-root" in body
    assert "UV_CACHE_DIR" in body
    assert "UV_PYTHON_INSTALL_DIR" in body
    assert "UV_TOOL_DIR" in body
    assert "UV_TOOL_BIN_DIR" in body
    assert "MIR_CAPABILITY_HOME" in body
    assert "memory.db" not in body
    subprocess.run(["bash", "-n", str(wrapper)], check=True)


# @spec FR-004 QR-001
def test_should_stop_before_mutation_when_setup_sh_runs_in_native_windows_bash(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uname = fake_bin / "uname"
    fake_uname.write_text("#!/bin/sh\nprintf 'MINGW64_NT-10.0\\n'\n", encoding="utf-8")
    fake_uname.chmod(0o755)
    uv_marker = tmp_path / "uv-called"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        f"#!/bin/sh\ntouch '{uv_marker}'\nexit 99\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    storage = tmp_path / "storage"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    completed = subprocess.run(
        ["bash", str(ROOT / "setup.sh"), "--storage-root", str(storage)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 1
    assert "Native Windows automated bootstrap is unsupported" in completed.stderr
    assert "setup.sh inside WSL" in completed.stderr
    assert not storage.exists()
    assert not uv_marker.exists()


def test_setup_rejects_provider_push_remote_before_host_mutation(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
    (project / ".mir").mkdir()
    (project / ".mir/capability-lock.json").write_text(
        json.dumps(
            {
                "source": {
                    "url": "https://github.com/example/mir-yoke.git",
                    "commit": "a" * 40,
                }
            }
        ),
        encoding="utf-8",
    )
    (project / "config").mkdir()
    (project / "config/capability-sources.json").write_text(
        json.dumps({"source": {"url": "https://github.com/example/mir-yoke.git"}}),
        encoding="utf-8",
    )
    (project / "config/cli-runtime-constraints.txt").write_text(
        "pyyaml==6.0.3\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/mir-yoke.git"],
        cwd=project,
        check=True,
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_marker = tmp_path / "uv-called"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(f"#!/bin/sh\ntouch '{uv_marker}'\nexit 99\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    storage = tmp_path / "storage"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    completed = subprocess.run(
        ["bash", str(project / "setup.sh"), "--storage-root", str(storage)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 1
    assert "Git push remote 'origin' still targets the Mir Yoke provider" in completed.stderr
    assert "git remote set-url --push mir-yoke-upstream DISABLED" in completed.stderr
    assert not storage.exists()
    assert not uv_marker.exists()


def test_setup_rejects_provider_push_remote_with_default_ports(tmp_path):
    for push_url in (
        "ssh://git@github.com:22/example/mir-yoke.git",
        "https://github.com:443/example/mir-yoke.git",
    ):
        project = tmp_path / sha256(push_url.encode()).hexdigest()[:8]
        project.mkdir()
        shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
        (project / ".mir").mkdir()
        (project / ".mir/capability-lock.json").write_text(
            json.dumps(
                {
                    "source": {
                        "url": "https://github.com/example/mir-yoke.git",
                        "commit": "a" * 40,
                    }
                }
            ),
            encoding="utf-8",
        )
        (project / "config").mkdir()
        (project / "config/capability-sources.json").write_text(
            json.dumps({"source": {"url": "https://github.com/example/mir-yoke.git"}}),
            encoding="utf-8",
        )
        (project / "config/cli-runtime-constraints.txt").write_text(
            "pyyaml==6.0.3\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(["git", "remote", "add", "origin", push_url], cwd=project, check=True)

        completed = subprocess.run(
            ["bash", str(project / "setup.sh")], check=False, capture_output=True, text=True
        )

        assert completed.returncode == 1
        assert "still targets the Mir Yoke provider" in completed.stderr


def test_setup_rejects_storage_inside_project_before_creating_it(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
    nested_storage = project / ".local-runtime"

    completed = subprocess.run(
        ["bash", str(project / "setup.sh"), "--storage-root", str(nested_storage)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "must be outside the project" in completed.stderr
    assert not nested_storage.exists()


def test_setup_rejects_explicit_empty_storage_before_invoking_uv(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_marker = tmp_path / "uv-called"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(f"#!/bin/sh\ntouch '{uv_marker}'\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    for argument in ("--storage-root=", "--storage-root"):
        command = ["bash", str(ROOT / "setup.sh"), argument]
        if argument == "--storage-root":
            command.append("")
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert completed.returncode == 1
        assert "requires a non-empty path" in completed.stderr
        assert not uv_marker.exists()


def test_setup_rejects_nonexistent_storage_path_with_parent_traversal(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
    traversal = project / ".." / "new" / ".." / "project" / ".local-runtime"

    completed = subprocess.run(
        ["bash", str(project / "setup.sh"), "--storage-root", str(traversal)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "cannot be resolved" in completed.stderr
    assert not (tmp_path / "new").exists()
    assert not (project / ".local-runtime").exists()


def test_shell_wrapper_exports_external_storage_before_tool_install(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
    (project / ".mir").mkdir()
    (project / ".mir/capability-lock.json").write_text(
        json.dumps(
            {
                "source": {
                    "url": "https://github.com/example/mir-yoke.git",
                    "commit": "a" * 40,
                }
            }
        ),
        encoding="utf-8",
    )
    (project / "config").mkdir()
    (project / "config/capability-sources.json").write_text(
        json.dumps({"source": {"url": "https://github.com/example/mir-yoke.git"}}),
        encoding="utf-8",
    )
    (project / "config/cli-runtime-constraints.txt").write_text(
        "pyyaml==6.0.3\n", encoding="utf-8"
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'uv:%s|%s|%s|%s|%s|%s\\n' \"$*\" \"$UV_CACHE_DIR\" "
        "\"$UV_PYTHON_INSTALL_DIR\" \"$UV_TOOL_DIR\" \"$UV_TOOL_BIN_DIR\" "
        '"$MIR_CAPABILITY_HOME" >> "$UV_TEST_LOG"\n'
        "if [ \"$1 $2 $3\" = \"tool dir --bin\" ]; then printf '%s\\n' \"$UV_TEST_BIN\"; fi\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    storage = tmp_path / "external storage"
    runtime_id = _runtime_id(
        project,
        "https://github.com/example/mir-yoke.git",
        "a" * 40,
    )
    tool_bin = storage / "mir/cli" / runtime_id / "bin"
    tool_bin.mkdir(parents=True)
    fake_mir = tool_bin / "mir"
    fake_mir.write_text(
        "#!/usr/bin/env bash\n"
        + _FAKE_MANIFEST_CREATE
        + "printf 'mir:%s|%s\\n' \"$*\" \"$MIR_BOOTSTRAP_CLI_PATH\" >> \"$UV_TEST_LOG\"\n",
        encoding="utf-8",
    )
    fake_mir.chmod(0o755)
    log = tmp_path / "uv.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "UV_TEST_BIN": str(tool_bin),
            "UV_TEST_LOG": str(log),
        }
    )

    completed = subprocess.run(
        ["bash", str(project / "setup.sh"), "--storage-root", str(storage), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    lines = log.read_text(encoding="utf-8").splitlines()
    first = lines[0].split("|")
    assert first[0].startswith("uv:tool install --force --link-mode copy")
    assert "--constraints" in first[0]
    assert "git+https://github.com/example/mir-yoke.git@" + "a" * 40 in first[0]
    assert first[1] == str(storage / "uv" / "cache")
    assert first[2] == str(storage / "uv" / "python")
    assert Path(first[3]).is_relative_to(storage / "mir" / "cli")
    assert Path(first[4]).is_relative_to(storage / "mir" / "cli")
    assert first[5] == str(storage / "mir" / "capabilities")
    assert lines[-1] == (
        f"mir:bootstrap --project-root {project} --storage-root {storage} --json|{fake_mir}"
    )


def test_two_projects_sharing_storage_get_distinct_tool_namespaces(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s|%s\\n' \"$UV_TOOL_DIR\" \"$UV_TOOL_BIN_DIR\" >> \"$UV_TEST_LOG\"\n"
        "if [ \"$1 $2 $3\" = \"tool dir --bin\" ]; then printf '%s\\n' \"$UV_TOOL_BIN_DIR\"; fi\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    storage = tmp_path / "storage"
    log = tmp_path / "uv.log"
    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}{os.pathsep}{env['PATH']}", "UV_TEST_LOG": str(log)})

    for name in ("one", "two"):
        project = tmp_path / name
        project.mkdir()
        shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
        (project / ".mir").mkdir()
        (project / ".mir/capability-lock.json").write_text(
            json.dumps(
                {
                    "source": {
                        "url": "https://github.com/example/mir-yoke.git",
                        "commit": "a" * 40,
                    }
                }
            ),
            encoding="utf-8",
        )
        (project / "config").mkdir()
        (project / "config/capability-sources.json").write_text(
            json.dumps({"source": {"url": "https://github.com/example/mir-yoke.git"}}),
            encoding="utf-8",
        )
        (project / "config/cli-runtime-constraints.txt").write_text(
            "pyyaml==6.0.3\n", encoding="utf-8"
        )
        runtime_id = sha256(
            f"{project.resolve()}\nhttps://github.com/example/mir-yoke.git\n{'a' * 40}\n".encode()
        ).hexdigest()[:24]
        tool_bin = storage / "mir" / "cli" / runtime_id / "bin"
        tool_bin.mkdir(parents=True, exist_ok=True)
        fake_mir = tool_bin / "mir"
        fake_mir.write_text(
            "#!/bin/sh\n" + _FAKE_MANIFEST_CREATE + "exit 0\n", encoding="utf-8"
        )
        fake_mir.chmod(0o755)
        completed = subprocess.run(
            ["bash", str(project / "setup.sh"), "--storage-root", str(storage), "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr

    namespaces = {line.split("|")[0] for line in log.read_text().splitlines()}
    assert len(namespaces) == 2
    assert all(Path(path).is_relative_to(storage / "mir" / "cli") for path in namespaces)


# @spec QR-001
def test_should_return_guidance_when_powershell_wrapper_runs_on_native_windows():
    wrapper = ROOT / "setup.ps1"
    body = wrapper.read_text(encoding="utf-8")

    assert "Native Windows automated bootstrap is unsupported" in body
    assert "setup.sh inside WSL" in body
    assert "agent-guided existing-repository/reference adaptation" in body
    assert "uv " not in body.lower()
    assert "New-Item" not in body
    assert "MIR_BOOTSTRAP_CLI_PATH" not in body

    pwsh = shutil.which("pwsh")
    if pwsh:
        completed = subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-File",
                str(wrapper),
                "-Profile",
                "code_app",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 1
        assert "Native Windows automated bootstrap is unsupported" in completed.stderr


def test_should_target_supported_unix_platforms_when_portable_bootstrap_ci_runs():
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
        encoding="utf-8"
    )

    assert "os: [ubuntu-latest, macos-latest]" in workflow
    assert "windows-latest" not in workflow
    assert "Bootstrap phase 1 on Windows PowerShell" not in workflow
    assert "Finalize ready bootstrap on Windows PowerShell" not in workflow


def test_shell_cli_launcher_uses_receipt_executable(tmp_path):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/mir.sh", scripts / "mir.sh")
    external = tmp_path / "external-mir"
    external.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\"\n", encoding="utf-8")
    external.chmod(0o755)
    receipt = project / ".mir/bootstrap-receipt.json"
    receipt.parent.mkdir()
    receipt.write_text(
        json.dumps(
            {
                "cli": {
                    "executable": str(external),
                    "sha256": sha256(external.read_bytes()).hexdigest(),
                }
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["bash", str(scripts / "mir.sh"), "capability", "status"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "capability status"


def test_shell_wrapper_reuses_hash_bound_external_cli_after_slim(tmp_path):
    project = tmp_path / "product"
    project.mkdir()
    shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
    source_url = "https://github.com/example/mir-yoke.git"
    source_commit = "a" * 40
    runtime_id = _runtime_id(project, source_url, source_commit)
    data_home = tmp_path / "data"
    external = data_home / "mir-yoke" / "cli" / runtime_id / "bin" / "mir"
    external.parent.mkdir(parents=True)
    log = tmp_path / "external.log"
    external.write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2" = "runtime-manifest verify" ]; then exit 0; fi\n'
        "printf '%s\\n' \"$*\" >> \"$MIR_TEST_LOG\"\n",
        encoding="utf-8",
    )
    external.chmod(0o755)
    executable_hash = sha256(external.read_bytes()).hexdigest()
    constraints = "pyyaml==6.0.3\n"
    receipt = project / ".mir/bootstrap-receipt.json"
    receipt.parent.mkdir()
    (project / ".mir/capability-lock.json").write_text(
        json.dumps(
            {
                "source": {
                    "url": source_url,
                    "commit": source_commit,
                }
            }
        ),
        encoding="utf-8",
    )
    (project / "config").mkdir()
    (project / "config/capability-sources.json").write_text(
        json.dumps({"source": {"url": "https://github.com/example/mir-yoke.git"}}),
        encoding="utf-8",
    )
    (project / "config/cli-runtime-constraints.txt").write_text(
        constraints, encoding="utf-8"
    )
    runtime_manifest, runtime_manifest_hash = _write_fake_runtime_manifest(
        external.parents[1]
    )
    receipt.write_text(
        json.dumps(
            {
                "cli": {
                    "executable": str(external),
                    "sha256": executable_hash,
                    "runtime_id": runtime_id,
                    "source_url": source_url,
                    "source_commit": source_commit,
                    "source_lock_sha256": "b" * 64,
                    "constraints_sha256": sha256(constraints.encode()).hexdigest(),
                    "runtime_manifest": str(runtime_manifest),
                    "runtime_manifest_sha256": runtime_manifest_hash,
                }
            }
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\nprintf 'unexpected uv call: %s\\n' \"$*\" >&2\nexit 99\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "MIR_TEST_LOG": str(log),
            "XDG_DATA_HOME": str(data_home),
        }
    )

    completed = subprocess.run(
        ["bash", str(project / "setup.sh"), "--profile", "code_app", "--finalize"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert log.read_text(encoding="utf-8").strip() == (
        f"bootstrap --project-root {project} --profile code_app --finalize"
    )
    assert "reusing receipt-bound external Mir CLI" in completed.stdout


def test_receipt_cli_reuse_restores_external_storage_environment(tmp_path):
    project = tmp_path / "product"
    project.mkdir()
    shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
    storage = tmp_path / "storage"
    source_url = "https://github.com/example/mir-yoke.git"
    source_commit = "a" * 40
    runtime_id = _runtime_id(project, source_url, source_commit)
    external = storage / "mir" / "cli" / runtime_id / "bin" / "mir"
    external.parent.mkdir(parents=True)
    log = tmp_path / "external.log"
    external.write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2" = "runtime-manifest verify" ]; then exit 0; fi\n'
        "printf '%s|%s|%s|%s|%s|%s\\n' \"$UV_CACHE_DIR\" \"$UV_PYTHON_INSTALL_DIR\" "
        "\"$UV_TOOL_DIR\" \"$UV_TOOL_BIN_DIR\" \"$MIR_CAPABILITY_HOME\" "
        "\"$UV_PROJECT_ENVIRONMENT\" > \"$MIR_TEST_LOG\"\n",
        encoding="utf-8",
    )
    external.chmod(0o755)
    constraints = "pyyaml==6.0.3\n"
    receipt = project / ".mir/bootstrap-receipt.json"
    receipt.parent.mkdir()
    (project / ".mir/capability-lock.json").write_text(
        json.dumps(
            {
                "source": {
                    "url": source_url,
                    "commit": source_commit,
                }
            }
        ),
        encoding="utf-8",
    )
    (project / "config").mkdir()
    (project / "config/capability-sources.json").write_text(
        json.dumps({"source": {"url": "https://github.com/example/mir-yoke.git"}}),
        encoding="utf-8",
    )
    (project / "config/cli-runtime-constraints.txt").write_text(
        constraints, encoding="utf-8"
    )
    runtime_manifest, runtime_manifest_hash = _write_fake_runtime_manifest(
        external.parents[1]
    )
    receipt.write_text(
        json.dumps(
            {
                "cli": {
                    "executable": str(external),
                    "sha256": sha256(external.read_bytes()).hexdigest(),
                    "runtime_id": runtime_id,
                    "source_url": source_url,
                    "source_commit": source_commit,
                    "source_lock_sha256": "b" * 64,
                    "constraints_sha256": sha256(constraints.encode()).hexdigest(),
                    "runtime_manifest": str(runtime_manifest),
                    "runtime_manifest_sha256": runtime_manifest_hash,
                }
            }
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "MIR_TEST_LOG": str(log),
        }
    )

    completed = subprocess.run(
        ["bash", str(project / "setup.sh"), "--storage-root", str(storage), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert log.read_text(encoding="utf-8").strip().split("|") == [
        str(storage / "uv/cache"),
        str(storage / "uv/python"),
        str(storage / "mir/cli" / runtime_id / "tools"),
        str(storage / "mir/cli" / runtime_id / "bin"),
        str(storage / "mir/capabilities"),
        str(project / ".venv"),
    ]


def test_copied_receipt_cannot_reuse_another_projects_runtime(tmp_path):
    source_url = "https://github.com/example/mir-yoke.git"
    source_commit = "a" * 40
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    shutil.copy2(ROOT / "setup.sh", second / "setup.sh")
    first_runtime = _runtime_id(first, source_url, source_commit)
    data_home = tmp_path / "data"
    old_cli = data_home / "mir-yoke/cli" / first_runtime / "bin/mir"
    old_cli.parent.mkdir(parents=True)
    old_marker = tmp_path / "old-called"
    old_cli.write_text(f"#!/bin/sh\ntouch '{old_marker}'\n", encoding="utf-8")
    old_cli.chmod(0o755)
    (second / ".mir").mkdir()
    (second / ".mir/capability-lock.json").write_text(
        json.dumps({"source": {"url": source_url, "commit": source_commit}}), encoding="utf-8"
    )
    (second / "config").mkdir()
    (second / "config/capability-sources.json").write_text(
        json.dumps({"source": {"url": source_url}}), encoding="utf-8"
    )
    constraints = "pyyaml==6.0.3\n"
    (second / "config/cli-runtime-constraints.txt").write_text(constraints, encoding="utf-8")
    (second / ".mir/bootstrap-receipt.json").write_text(
        json.dumps({"cli": {
            "executable": str(old_cli),
            "sha256": sha256(old_cli.read_bytes()).hexdigest(),
            "runtime_id": first_runtime,
            "source_url": source_url,
            "source_commit": source_commit,
            "source_lock_sha256": "b" * 64,
            "constraints_sha256": sha256(constraints.encode()).hexdigest(),
        }}),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_marker = tmp_path / "uv-called"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(f"#!/bin/sh\ntouch '{uv_marker}'\nexit 99\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    env = os.environ.copy()
    env.update({"PATH": f"{fake_bin}{os.pathsep}{env['PATH']}", "XDG_DATA_HOME": str(data_home)})

    completed = subprocess.run(
        ["bash", str(second / "setup.sh"), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode != 0
    assert uv_marker.exists()
    assert not old_marker.exists()


def test_receipt_cli_is_not_reused_after_locked_source_changes(tmp_path):
    project = tmp_path / "product"
    project.mkdir()
    shutil.copy2(ROOT / "setup.sh", project / "setup.sh")
    old_cli = tmp_path / "old-mir"
    old_marker = tmp_path / "old-called"
    old_cli.write_text(f"#!/bin/sh\ntouch '{old_marker}'\n", encoding="utf-8")
    old_cli.chmod(0o755)
    receipt = project / ".mir/bootstrap-receipt.json"
    receipt.parent.mkdir()
    (project / ".mir/capability-lock.json").write_text(
        json.dumps(
            {
                "source": {
                    "url": "https://github.com/example/mir-yoke.git",
                    "commit": "b" * 40,
                }
            }
        ),
        encoding="utf-8",
    )
    (project / "config").mkdir()
    (project / "config/capability-sources.json").write_text(
        json.dumps({"source": {"url": "https://github.com/example/mir-yoke.git"}}),
        encoding="utf-8",
    )
    constraints = "pyyaml==6.0.3\n"
    (project / "config/cli-runtime-constraints.txt").write_text(
        constraints, encoding="utf-8"
    )
    receipt.write_text(
        json.dumps(
            {
                "cli": {
                    "executable": str(old_cli),
                    "sha256": sha256(old_cli.read_bytes()).hexdigest(),
                    "runtime_id": "old-runtime",
                    "source_url": "https://github.com/example/mir-yoke.git",
                    "source_commit": "a" * 40,
                    "source_lock_sha256": "c" * 64,
                    "constraints_sha256": sha256(constraints.encode()).hexdigest(),
                }
            }
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_marker = tmp_path / "uv-called"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(f"#!/bin/sh\ntouch '{uv_marker}'\nexit 99\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    completed = subprocess.run(
        ["bash", str(project / "setup.sh"), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode != 0
    assert uv_marker.exists()
    assert not old_marker.exists()


def test_cli_runtime_constraints_match_frozen_production_lock() -> None:
    completed = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--no-annotate",
            "--no-header",
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (ROOT / "config/cli-runtime-constraints.txt").read_text(encoding="utf-8") == (
        completed.stdout
    )


def test_hook_launcher_prefers_receipt_cli_over_product_virtualenv(tmp_path):
    project = tmp_path / "product"
    launcher = project / ".claude/hooks/_lib/run-python.sh"
    launcher.parent.mkdir(parents=True)
    shutil.copy2(ROOT / ".claude/hooks/_lib/run-python.sh", launcher)
    local_python = project / ".venv/bin/python"
    local_python.parent.mkdir(parents=True)
    local_python.write_text("#!/bin/sh\necho local-python\n", encoding="utf-8")
    local_python.chmod(0o755)
    external = tmp_path / "external-mir"
    external.write_text("#!/bin/sh\necho external-mir \"$@\"\n", encoding="utf-8")
    external.chmod(0o755)
    receipt = project / ".mir/bootstrap-receipt.json"
    receipt.parent.mkdir()
    receipt.write_text(
        json.dumps(
            {
                "cli": {
                    "executable": str(external),
                    "sha256": sha256(external.read_bytes()).hexdigest(),
                }
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project)

    completed = subprocess.run(
        ["bash", str(launcher), "-c", "print('probe')"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith(
        f"external-mir run-python --project-root {project} -- -c"
    )
    assert "local-python" not in completed.stdout
