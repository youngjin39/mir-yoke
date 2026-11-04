"""Offline publication-to-lock contract; no real lock or GitHub writes."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    'aarch64-apple-darwin', 'x86_64-apple-darwin',
    'x86_64-unknown-linux-gnu', 'aarch64-unknown-linux-gnu', 'x86_64-pc-windows-msvc',
)
NAMES = (
    'handoff-packet', 'runtime-continuity', 'bootstrap-gate', 'runtime-verify', 'executor-query',
    'mir-mcp',
)
SOURCE = 'a' * 40
TAG = 'native-' + SOURCE[:12]
BASE = f'https://github.com/example/provider/releases/download/{TAG}'


@pytest.fixture
def assets(tmp_path):
    directory = tmp_path / 'assets'
    directory.mkdir()
    records = []

    def add(name, data):
        (directory / name).write_bytes(data)
        records.append({'name': name, 'size': len(data), 'browser_download_url': f'{BASE}/{name}'})

    for target in TARGETS:
        checksums = []
        for name in NAMES:
            filename = f'{name}-{target}' + ('.exe' if 'windows' in target else '')
            data = filename.encode() + b'\x00\xff'
            add(filename, data)
            checksums.append(f'{hashlib.sha256(data).hexdigest()}  {filename}\n')
        add(f'SHA256-{target}.txt', ''.join(checksums).encode())
    release = {'tag_name': TAG, 'target_commitish': SOURCE, 'prerelease': True,
               'assets': records}
    (directory / 'release.json').write_text(json.dumps(release))
    lock = tmp_path / 'lock.json'
    lock.write_text(json.dumps({'source': {'commit': 'c' * 40},
                                'plugins': {'mir-lifecycle-hooks': {}, 'mir-mcp': {}},
                                'preserve': [1]}))
    return directory, lock


def run_tool(directory, lock, source=None):
    return subprocess.run([sys.executable, '-m', 'tools.native_release', '--directory',
                           str(directory), '--lock', str(lock), '--source', source or SOURCE],
                          cwd=ROOT, capture_output=True)


def test_pins_published_bytes_and_preserves_lock(assets):
    from mir.core.capabilities.native import validate_artifacts

    directory, lock = assets
    result = run_tool(directory, lock)
    assert result.returncode == 0, result.stderr
    document = json.loads(lock.read_text())
    assert document['preserve'] == [1]
    records = document['native_artifacts']
    assert set(records) == set(NAMES)
    assert validate_artifacts(records, document['plugins'], portable=True) == records
    for name in NAMES:
        assert records[name]['install_path'] == f'bin/{name}'
        assert records[name]['plugin'] == ('mir-mcp' if name == 'mir-mcp'
                                            else 'mir-lifecycle-hooks')
        assert set(records[name]['targets']) == set(TARGETS)
        for pin in records[name]['targets'].values():
            path = directory / pin['url'].rsplit('/', 1)[1]
            assert pin['url'].startswith(BASE + '/')
            assert pin['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
            assert pin['size'] == path.stat().st_size


@pytest.mark.parametrize('failure', [
    'digest', 'size', 'missing', 'duplicate', 'url', 'checksum-size', 'checksum-name',
    'not-prerelease', 'tag', 'source', 'symlink',
])
def test_rejects_bad_assets_without_lock_writes(assets, failure):
    directory, lock = assets
    release_path = directory / 'release.json'
    release = json.loads(release_path.read_text())
    first = release['assets'][0]
    if failure == 'digest':
        (directory / first['name']).write_bytes(b'x' * first['size'])
    elif failure == 'size':
        first['size'] += 1
    elif failure == 'missing':
        release['assets'].pop()
    elif failure == 'duplicate':
        release['assets'].append(first)
    elif failure == 'url':
        first['browser_download_url'] = 'http://example.com/binary'
    elif failure == 'checksum-size':
        release['assets'][len(NAMES)]['size'] += 1
    elif failure == 'checksum-name':
        path = directory / release['assets'][len(NAMES)]['name']
        data = path.read_bytes().replace(first['name'].encode(), b'../outside')
        path.write_bytes(data)
        release['assets'][len(NAMES)]['size'] = len(data)
    elif failure == 'not-prerelease':
        release['prerelease'] = False
    elif failure == 'tag':
        release['tag_name'] = 'v1.0'
    elif failure == 'source':
        release['target_commitish'] = 'b' * 40
    else:
        path = directory / first['name']
        saved = directory / 'saved'
        path.rename(saved)
        path.symlink_to(saved)
    release_path.write_text(json.dumps(release))
    before = lock.read_bytes()
    result = run_tool(directory, lock)
    assert result.returncode != 0
    assert lock.read_bytes() == before


def test_workflow_publication_is_opt_in_and_collects_all_binaries():
    workflow = yaml.safe_load((ROOT / '.github/workflows/native-artifacts.yml').read_text())
    trigger = workflow.get('on', workflow.get(True))
    publish = trigger['workflow_dispatch']['inputs']['publish']
    assert publish['type'] == 'boolean' and publish['default'] is False
    job = workflow['jobs']['publish']
    assert job['if'] == '${{ inputs.publish }}'
    assert job['needs'] == 'build'
    assert job['permissions'] == {'contents': 'write'}
    steps = '\n'.join(step.get('run', '') for step in job['steps'])
    assert 'gh release create' in steps and '--prerelease' in steps
    assert 'gh release upload' in steps and '--clobber' in steps
    build = '\n'.join(step.get('run', '') for step in workflow['jobs']['build']['steps'])
    for name in NAMES:
        assert name in build
    assert 'for name in ' + ' '.join(NAMES) + '; do' in build
    assert f'-eq {len(TARGETS) * (len(NAMES) + 1)}' in steps
    matrix = workflow['jobs']['build']['strategy']['matrix']['include']
    assert {row['target'] for row in matrix} == set(TARGETS)
    assert len(matrix) == len(TARGETS)


@pytest.mark.parametrize('index', range(len(TARGETS) * (len(NAMES) + 1)))
def test_checks_every_asset_size(assets, index):
    directory, lock = assets
    release_path = directory / 'release.json'
    release = json.loads(release_path.read_text())
    release['assets'][index]['size'] += 1
    release_path.write_text(json.dumps(release))
    before = lock.read_bytes()
    result = run_tool(directory, lock)
    assert result.returncode == 1 and b'size mismatch' in result.stderr
    assert lock.read_bytes() == before


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('target', TARGETS)
def test_checks_every_binary_digest(assets, name, target):
    directory, lock = assets
    filename = f'{name}-{target}' + ('.exe' if 'windows' in target else '')
    path = directory / filename
    path.write_bytes(b'x' * path.stat().st_size)
    before = lock.read_bytes()
    result = run_tool(directory, lock)
    assert result.returncode == 1 and b'SHA256 mismatch' in result.stderr
    assert lock.read_bytes() == before


def test_workflow_digest_step_agrees_with_release_tool(assets, tmp_path):
    directory, lock = assets
    workflow = yaml.safe_load((ROOT / '.github/workflows/native-artifacts.yml').read_text())
    steps = workflow['jobs']['build']['steps']
    digest = next(step['run'] for step in steps if step.get('name') == 'digest')
    crate = tmp_path / 'build/native/handoff-packet'
    crate.mkdir(parents=True)
    output = tmp_path / 'build/dist-native'
    for target in TARGETS:
        for name in NAMES:
            source_crate = crate.parent / ('mir-mcp' if name == 'mir-mcp' else 'handoff-packet')
            release = source_crate / 'target' / target / 'release'
            release.mkdir(parents=True, exist_ok=True)
            suffix = '.exe' if 'windows' in target else ''
            (release / (name + suffix)).write_bytes(
                (directory / f'{name}-{target}{suffix}').read_bytes())
        command = digest.replace('${{ matrix.target }}', target).replace(
            '${{ matrix.exe }}', '.exe' if 'windows' in target else '')
        subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', command], cwd=crate,
                       check=True, capture_output=True)
        for name in [f'SHA256-{target}.txt', *(f'{n}-{target}{suffix}' for n in NAMES)]:
            assert (output / name).read_bytes() == (directory / name).read_bytes()
    (output / 'release.json').write_bytes((directory / 'release.json').read_bytes())
    assert run_tool(output, lock).returncode == 0


def test_source_argument_must_match_the_tag(assets):
    directory, lock = assets
    before = lock.read_bytes()
    result = run_tool(directory, lock, source='b' * 40)
    assert result.returncode != 0
    assert lock.read_bytes() == before


def test_online_download_collects_every_binary(monkeypatch, tmp_path):
    from tools import native_release

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=b'{}')

    monkeypatch.setattr(native_release.subprocess, 'run', fake_run)
    monkeypatch.setattr(native_release, 'pin_release', lambda *args: None)
    assert native_release.main([
        '--repo', 'example/provider', '--tag', TAG, '--lock', str(tmp_path / 'lock.json'),
        '--source', SOURCE,
    ]) == 0
    download = calls[1]
    patterns = [download[index + 1] for index, value in enumerate(download) if value == '--pattern']
    assert set(patterns) == {*(f'{name}-*' for name in NAMES), 'SHA256-*'}


def test_preserves_unrelated_native_records(assets):
    directory, lock = assets
    document = json.loads(lock.read_text())
    preserved = {'plugin': 'mir-mcp', 'install_path': 'bin/another-tool', 'targets': {}}
    document['native_artifacts'] = {'another-tool': preserved}
    lock.write_text(json.dumps(document))
    result = run_tool(directory, lock)
    assert result.returncode == 0, result.stderr
    records = json.loads(lock.read_text())['native_artifacts']
    assert records['another-tool'] == preserved
    assert set(records) == {*NAMES, 'another-tool'}


def test_validate_workflow_checks_native_mcp_on_all_platforms():
    workflow = yaml.safe_load((ROOT / '.github/workflows/validate.yml').read_text())
    for job_name in ('native_handoff', 'windows_native'):
        steps = workflow['jobs'][job_name]['steps']
        commands = [step['run'] for step in steps
                    if step.get('working-directory') == 'native/mir-mcp']
        for command in ('cargo fmt --check', 'cargo clippy --all-targets --locked -- -D warnings',
                        'cargo test --locked --no-fail-fast', 'cargo build --release --locked'):
            assert command in commands
        oracle = next(step for step in steps
                      if 'tests/test_mir_mcp_native_core.py' in step.get('run', ''))
        assert 'tests/test_mir_mcp_native_io.py' in oracle['run']
        assert 'MIR_MCP_NATIVE_BINARY' in oracle['env']


def test_native_workflow_smokes_mcp():
    workflow = yaml.safe_load((ROOT / '.github/workflows/native-artifacts.yml').read_text())
    steps = workflow['jobs']['build']['steps']
    assert any('cargo build --release --locked --target' in step.get('run', '')
               and step.get('working-directory') == 'native/mir-mcp' for step in steps)
    smoke = next(step['run'] for step in steps if step.get('name') == 'smoke run')
    assert 'mir-mcp${{ matrix.exe }}' in smoke
    assert 'tools/list' in smoke and 'io.modelcontextprotocol/protocolVersion' in smoke
    assert '--reference-python "$python"' in smoke
    assert '--reference-script ../../plugins/mir-mcp/mir_mcp.py' in smoke
    assert "sys.executable" in smoke
