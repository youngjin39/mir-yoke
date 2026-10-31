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
NAMES = ('handoff-packet', 'runtime-continuity')
TAG = 'native-' + 'a' * 12
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
    release = {'tag_name': TAG, 'prerelease': True, 'assets': records}
    (directory / 'release.json').write_text(json.dumps(release))
    lock = tmp_path / 'lock.json'
    lock.write_text(json.dumps({'source': {'commit': 'a' * 40},
                                'plugins': {'mir-lifecycle-hooks': {}}, 'preserve': [1]}))
    return directory, lock


def run_tool(directory, lock):
    return subprocess.run([sys.executable, '-m', 'tools.native_release', '--directory',
                           str(directory), '--lock', str(lock)], cwd=ROOT, capture_output=True)


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
        assert records[name]['plugin'] == 'mir-lifecycle-hooks'
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
        release['assets'][2]['size'] += 1
    elif failure == 'checksum-name':
        path = directory / release['assets'][2]['name']
        data = path.read_bytes().replace(first['name'].encode(), b'../outside')
        path.write_bytes(data)
        release['assets'][2]['size'] = len(data)
    elif failure == 'not-prerelease':
        release['prerelease'] = False
    elif failure == 'tag':
        release['tag_name'] = 'v1.0'
    elif failure == 'source':
        data = json.loads(lock.read_text())
        data['source']['commit'] = 'b' * 40
        lock.write_text(json.dumps(data))
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


def test_workflow_publication_is_opt_in_and_collects_both_binaries():
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
    assert 'runtime-continuity' in build
    assert 'handoff-packet' in build
    assert len(workflow['jobs']['build']['strategy']['matrix']['include']) == 5


@pytest.mark.parametrize('index', range(15))
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
        release = crate / 'target' / target / 'release'
        release.mkdir(parents=True)
        for name in NAMES:
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
