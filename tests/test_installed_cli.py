from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import struct
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from select import select

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SUBCOMMANDS = (
    "bootstrap",
    "bootstrap-adoption",
    "capability",
    "context",
    "executor",
    "loop",
    "memory",
    "migrate",
    "policy",
    "project-hooks",
    "relations",
    "run-python",
    "runtime-manifest",
)


@pytest.fixture(scope="module")
def mac_asset():
    if sys.platform != "darwin":
        pytest.skip("requires a Darwin console asset")
    crate = ROOT / "native/handoff-packet"
    subprocess.run(["cargo", "build", "--locked", "--bin", "mir"], cwd=crate, check=True)
    return crate / os.environ.get("CARGO_TARGET_DIR", "target") / "debug/mir"


@pytest.fixture
def mac_setup(tmp_path, monkeypatch, mac_asset):
    asset = mac_asset
    project = tmp_path / "product with spaces"
    runtime_home = tmp_path / "runtime with spaces"
    for path in (project / ".mir", project / "config", tmp_path / "bin"):
        path.mkdir(parents=True)
    for name in ("setup.sh", "config/cli-runtime-constraints.txt"):
        shutil.copy2(ROOT / name, project / name)
    (project / "provider").symlink_to(ROOT, target_is_directory=True)
    url, commit = "https://example.invalid/mir-yoke.git", "a" * 40
    source = json.dumps({"source": {"url": url, "commit": commit}})
    for name in (".mir/capability-lock.json", "config/capability-sources.json"):
        (project / name).write_text(source)
    arch = {"arm64": "aarch64", "x86_64": "x86_64"}[platform.machine()]
    pin = project / "config/cli-native-artifacts.json"
    pin.write_text(json.dumps({"source_commit": commit, "targets": {
        f"{arch}-apple-darwin": {"url": "https://example.invalid/mir", "size": asset.stat().st_size,
                                 "sha256": sha256(asset.read_bytes()).hexdigest()},
    }}))

    def shim(name, body):
        path = tmp_path / "bin" / name
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)

    uv = shlex.quote(shutil.which("uv"))
    shim("uv", 'printf "%s|%s\\n" "$*" "${UV_CACHE_DIR:-}" >> "$UV_TEST_LOG"\n'
         'if [[ "$2" == install ]]; then\n'
         '  if [[ "${UV_TEST_OLD_SETUP:-}" == 1 ]]; then\n'
         f'    cd {shlex.quote(str(project))} || exit 99\n'
         '    [[ "$7" == "$PWD/config/cli-runtime-constraints.txt" ]] || exit 99\n'
         '    set -- "${@:1:6}" config/cli-runtime-constraints.txt "${!#}"\n'
         '  fi\n'
         f'  [[ "$PWD" == {shlex.quote(str(project))} && "$6" == --constraints '
         '&& "$7" == config/cli-runtime-constraints.txt ]] || exit 99\n'
         '  [[ "${!#}" == git+https://example.invalid/mir-yoke.git@* ]] || exit 99\n'
         '  set -- "${@:1:$#-1}" ./provider\n'
         '  if [[ -n "${UV_TEST_BUILD_CACHE:-}" ]]; then\n'
         '    export UV_CACHE_DIR="$UV_TEST_BUILD_CACHE"\n'
         '  fi\nfi\n'
         f'exec {uv} "$@"\n')
    shim("curl", '[[ "${!#}" == https://example.invalid/mir ]] || exit 99\n'
         'if [[ "${DELAY_DOWNLOAD:-}" == 1 ]]; then\n'
         '  echo download-ready >&2\n'
         '  read -r -t 120 _\n'
         '  exit 42\n'
         'fi\ncat "$STAGED_MIR"\n')
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    for name, value in {"XDG_DATA_HOME": runtime_home, "UV_TEST_LOG": tmp_path / "uv.log",
                        "STAGED_MIR": asset, "UV_OFFLINE": "1",
                        "UV_PYTHON": Path(sys.executable).resolve()}.items():
        monkeypatch.setenv(name, str(value))
    runtime_id = sha256(f"{project}\n{url}\n{commit}\n".encode()).hexdigest()[:24]
    cli = runtime_home / "mir-yoke/cli" / runtime_id / "bin/mir"
    return project, pin, cli, asset, shim


def _setup(project, *args):
    return subprocess.run(["bash", str(project / "setup.sh"), *args],
                          capture_output=True, text=True, timeout=90)


def test_macos_setup_installs_native_mir_at_public_path(mac_setup):
    project, _, cli, asset, shim = mac_setup
    result = _setup(project, "--help")
    assert result.returncode == 0, result.stderr
    assert cli.is_symlink()
    assert cli.resolve() == cli.parent.parent / "tools/mir-harness/bin/mir"
    assert cli.read_bytes() == asset.read_bytes()
    manager = [str(cli), "run-python", "--project-root", str(project), "--",
               "-m", "mir.cli.capability_manager_bridge"]
    response = subprocess.run(manager, input='{"op":"import"}\n', capture_output=True,
                              text=True, timeout=20, check=True)
    assert json.loads(response.stdout) == {"value": None, "error": None, "events": []}
    bootstrap = _setup(project, "--profile", "code_app", "--json")
    assert bootstrap.returncode != 0  # The fixture lacks project identity and active surfaces.
    assert json.loads(bootstrap.stdout[bootstrap.stdout.index("{"):])["platform"]["python"]

    cli.resolve().with_name("python").unlink()
    subprocess.run([cli, "relations", "--help"], env={"PATH": ""},
                   capture_output=True, timeout=10, check=True)
    failed_manager = subprocess.run(manager, capture_output=True, text=True, timeout=10)
    assert failed_manager.returncode == 127
    assert "Python unavailable" in failed_manager.stderr
    shim("uv", 'if [[ "$2" == dir ]]; then printf "%s\\n" "$UV_TOOL_BIN_DIR"; fi\n')
    failed_setup = _setup(project, "--help")
    assert failed_setup.returncode == 1
    assert "its sibling Python is unavailable" in failed_setup.stderr
    assert not list(cli.parents[2].glob(".mir-native.*"))


def test_macos_setup_selects_external_storage_for_install_and_reuse(mac_setup, monkeypatch):
    project, pin, default_cli, asset, shim = mac_setup
    storage = project.parent / "external storage"
    args = ("--storage-root", str(storage), "--help")
    receipt = project / ".mir/bootstrap-receipt.json"
    log = Path(os.environ["UV_TEST_LOG"])
    pin_text = pin.read_text()
    pin.unlink()
    refused = _setup(project, *args)
    assert refused.returncode == 1
    assert "no valid native Mir CLI pin" in refused.stderr
    assert not storage.exists()
    assert not receipt.exists()
    assert not log.exists()
    pin.write_text(pin_text)

    # Keep dependency resolution offline using the warmed cache after recording
    # the cache path selected by setup.
    cache = subprocess.check_output(["uv", "cache", "dir"], text=True).strip()
    monkeypatch.setenv("UV_TEST_BUILD_CACHE", cache)
    shim("uname", "echo Linux\n")
    with monkeypatch.context() as old_setup:
        old_setup.setenv("UV_TEST_OLD_SETUP", "1")
        assert (old := _setup(project, *args)).returncode == 0, old.stderr
    (project.parent / "bin/uname").unlink()
    runtime = storage / "mir/cli" / default_cli.parents[1].name
    cli = runtime / "bin/mir"
    manifest = runtime / "runtime-manifest.json"

    def bind_receipt():
        metadata = json.loads(manifest.read_text())
        receipt.write_text(json.dumps({"cli": {
            "executable": str(cli), "sha256": sha256(cli.read_bytes()).hexdigest(),
            "runtime_id": runtime.name, "runtime_manifest": str(manifest),
            "runtime_manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
            **{key: metadata[key] for key in ("source_url", "source_commit", "constraints_sha256")},
        }}))

    bind_receipt()
    log.unlink()
    assert (upgrade := _setup(project, *args)).returncode == 0, upgrade.stderr
    assert f"external-first storage ▸ root={storage}" in upgrade.stdout
    install, cache_dir = log.read_text().splitlines()[0].split("|")
    assert install.startswith("tool install --force")
    assert Path(cache_dir) == storage / "uv/cache"
    assert cli.read_bytes() == asset.read_bytes()
    bind_receipt()
    log.unlink()
    monkeypatch.setenv("STAGED_MIR", "/nonexistent")
    assert (reused := _setup(project, *args)).returncode == 0, reused.stderr
    assert f"external-first storage ▸ root={storage}" in reused.stdout
    assert "reusing receipt-bound external Mir CLI" in reused.stdout
    assert not log.exists()
    assert not Path(os.environ["XDG_DATA_HOME"]).exists()


def test_macos_setup_manifest_survives_concurrent_failed_download(mac_setup):
    project, _, cli, _, _ = mac_setup
    runtime = cli.parents[1]
    with subprocess.Popen(
        ["bash", str(project / "setup.sh"), "--help"],
        env=os.environ | {"DELAY_DOWNLOAD": "1"},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as downloading:
        try:
            assert select([downloading.stderr], [], [], 20)[0], "download did not start"
            assert downloading.stderr.readline().strip() == "download-ready"
            result = _setup(project, "--help")
            assert result.returncode == 0, result.stderr
            assert downloading.poll() is None
        finally:
            _, stderr = downloading.communicate(input="\n", timeout=15)
    assert downloading.returncode == 1
    assert "could not download the pinned native Mir CLI" in stderr

    manifest = runtime / "runtime-manifest.json"
    metadata = json.loads(manifest.read_text())
    verified = subprocess.run(
        [cli, "runtime-manifest", "verify", "--runtime-root", runtime, "--manifest", manifest,
         "--source-url", metadata["source_url"], "--source-commit", metadata["source_commit"],
         "--constraints-sha256", metadata["constraints_sha256"]],
        capture_output=True, text=True, timeout=20,
    )
    assert verified.returncode == 0, verified.stderr
    assert not list(runtime.parent.glob(".mir-native.*"))


def test_macos_setup_refuses_misdirected_public_link_before_replacing_mir(mac_setup):
    project, _, cli, _, shim = mac_setup
    installed_mir = cli.parents[1] / "tools/mir-harness/bin/mir"
    detour = project.parent / "detour"
    other_mir = detour / "tools/mir-harness/bin/mir"
    for path in (installed_mir, other_mir):
        path.parent.mkdir(parents=True)
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    installed_mir.with_name("python").symlink_to(sys.executable)
    (detour / "bin").mkdir()
    cli.parent.symlink_to(detour / "bin")
    cli.symlink_to("../tools/mir-harness/bin/mir")
    shim("uv", 'if [[ "$2" == dir ]]; then printf "%s\\n" "$UV_TOOL_BIN_DIR"; fi\n')

    result = _setup(project, "--help")
    assert result.returncode == 1
    assert installed_mir.read_bytes() == other_mir.read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert "uv public Mir CLI link does not point to the installed tool" in result.stderr
    assert not (cli.parents[1] / "runtime-manifest.json").exists()


@pytest.mark.parametrize(("case", "diagnostic"), [
    ("missing", "no valid native Mir CLI pin"), ("commit", "no valid native Mir CLI pin"),
    ("corrupt", "SHA-256 mismatch"), ("oversize", "size mismatch"),
    ("wrong-arch", "not a Mach-O executable"), ("not-executable", "not a Mach-O executable"),
])
def test_macos_setup_refuses_invalid_native_asset(mac_setup, monkeypatch, case, diagnostic):
    project, pin, cli, asset, _ = mac_setup
    data = json.loads(pin.read_text())
    target = next(iter(data["targets"].values()))
    if case == "missing":
        data["targets"].clear()
    elif case == "commit":
        data["source_commit"] = "b" * 40
    elif case == "corrupt":
        target["sha256"] = "0" * 64
    elif case == "oversize":
        target["size"] -= 1
    else:
        content = bytearray(asset.read_bytes())
        if case == "not-executable":
            struct.pack_into("<I", content, 12, 1)  # MH_OBJECT
        else:
            cpu = 0x01000007 if platform.machine() == "arm64" else 0x0100000C
            struct.pack_into("<I", content, 4, cpu)
        staged = project.parent / "invalid-mir"
        staged.write_bytes(content)
        monkeypatch.setenv("STAGED_MIR", str(staged))
        target["sha256"] = sha256(content).hexdigest()
    pin.write_text(json.dumps(data))
    result = _setup(project, "--help")
    assert result.returncode == 1
    assert diagnostic in result.stderr
    assert not Path(os.environ["UV_TEST_LOG"]).exists()
    assert not cli.exists()
    assert not list(cli.parents[2].glob(".mir-native.*"))
    if case in {"missing", "commit"}:
        assert not Path(os.environ["XDG_DATA_HOME"]).exists()
    else:
        assert "rerun setup.sh" in result.stderr


# @spec FR-001 FR-004
def test_should_run_copied_tool_when_repository_python_is_not_on_path(tmp_path: Path) -> None:
    tool_dir = tmp_path / "tools"
    bin_dir = tmp_path / "bin"
    env = os.environ.copy()
    env.update(
        {
            "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(tmp_path / "uv-cache")),
            "UV_TOOL_DIR": str(tool_dir),
            "UV_TOOL_BIN_DIR": str(bin_dir),
        }
    )

    installed = subprocess.run(
        ["uv", "tool", "install", "--force", "--link-mode", "copy", "."],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert installed.returncode == 0, installed.stderr

    cli = bin_dir / ("mir.exe" if os.name == "nt" else "mir")
    if os.name != "nt":
        assert cli.is_symlink()
        assert cli.resolve().is_relative_to(tool_dir)
    clean_env = env.copy()
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        clean_env.pop(name, None)
    root_help = subprocess.run(
        [str(cli), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert root_help.returncode == 0, root_help.stderr
    assert root_help.stdout.splitlines() == [
        "usage: mir <subcommand> [args]",
        f"subcommands: {', '.join(PUBLIC_SUBCOMMANDS)}",
    ]

    for command in PUBLIC_SUBCOMMANDS:
        completed = subprocess.run(
            [str(cli), command, "--help"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            env=clean_env,
        )
        assert completed.returncode == 0, completed.stderr

    command_probe = subprocess.run(
        [
            str(cli),
            "run-python",
            "--project-root",
            str(tmp_path),
            "--",
            "-c",
            "from pathlib import Path; Path('command-probe.txt').write_text('ready')",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert command_probe.returncode == 0, command_probe.stderr
    assert (tmp_path / "command-probe.txt").read_text(encoding="utf-8") == "ready"

    stdin_probe = subprocess.run(
        [str(cli), "run-python", "--project-root", str(tmp_path), "--", "-"],
        cwd=tmp_path,
        input="print('stdin-ready')\n",
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert stdin_probe.returncode == 0, stdin_probe.stderr
    assert stdin_probe.stdout.strip() == "stdin-ready"

    resource_probe = subprocess.run(
        [
            str(cli),
            "run-python",
            "--project-root",
            str(ROOT),
            "--",
            "-c",
            (
                "from pathlib import Path; "
                "from mir.cli.bootstrap_adoption import _validate_canonical_applied_helper; "
                "errors, _ = _validate_canonical_applied_helper("
                "Path('.'), '.claude/hooks/_lib/run-python.sh', label='installed'); "
                "assert not errors, errors"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert resource_probe.returncode == 0, resource_probe.stderr

    consumer = tmp_path / "consumer root"
    graph = consumer / "relations/declared graph.yaml"
    graph.parent.mkdir(parents=True)
    graph.write_text("edges:\n  - [APP, depends_on, LIB]\n", encoding="utf-8")
    relations_probe = subprocess.run(
        [
            str(cli),
            "relations",
            "query",
            "APP",
            "--purpose",
            "dependencies",
            "--root",
            str(consumer),
            "--graph",
            "relations/declared graph.yaml",
            "--json",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert relations_probe.returncode == 0, relations_probe.stderr
    relations = json.loads(relations_probe.stdout)
    assert relations["source"]["graph"] == "relations/declared graph.yaml"
    assert relations["edges"][0]["target"] == "LIB"
