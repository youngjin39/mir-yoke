"""Offline publication-to-lock contract; no real lock or GitHub writes."""

import hashlib
import json
import re
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
    'delegation-gate', 'project-hooks', 'mir-mcp',
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


def run_tool(directory, lock, source=None, *, options=()):
    return subprocess.run([sys.executable, '-m', 'tools.native_release', '--directory',
                           str(directory), '--lock', str(lock), '--source', source or SOURCE,
                           *options],
                          cwd=ROOT, capture_output=True)


def add_console(directory):
    manifest = directory / 'release.json'
    release = json.loads(manifest.read_text())
    pins = {}
    for target in TARGETS[:2]:
        name = f'mir-{target}'
        data = name.encode()
        (directory / name).write_bytes(data)
        pin = {'url': f'{BASE}/{name}', 'sha256': hashlib.sha256(data).hexdigest(),
               'size': len(data)}
        pins[target] = pin
        release['assets'].append(
            {'name': name, 'size': pin['size'], 'browser_download_url': pin['url']})
        checksum = next(a for a in release['assets'] if a['name'] == f'SHA256-{target}.txt')
        digest = directory / checksum['name']
        digest.write_text(digest.read_text() + f"{pin['sha256']}  {name}\n")
        checksum['size'] = digest.stat().st_size
    manifest.write_text(json.dumps(release))
    return {'source_commit': SOURCE, 'targets': pins}


@pytest.mark.parametrize(('failure', 'message'), [
    (None, None), ('size', b'asset size mismatch: mir-'), ('hash', b'SHA256 mismatch: mir-'),
    ('commit', b'given source commit'), ('tag', b'given source commit'),
    ('url', b'expected HTTPS'), ('missing', b'incomplete release'),
])
def test_mac_cohort_pins_console_separately(assets, failure, message):
    directory, lock = assets
    assert run_tool(directory, lock).returncode == 0
    old = json.loads(lock.read_text())['native_artifacts']
    cli = lock.with_name('cli-native-artifacts.json')
    cli.write_text('{}')
    expected = add_console(directory)
    manifest = directory / 'release.json'
    release = json.loads(manifest.read_text())
    release['assets'] = [a for a in release['assets']
                         if a['name'].endswith(('-apple-darwin', '-apple-darwin.txt'))]
    console = release['assets'][-1]
    if failure == 'size':
        console['size'] += 1
    elif failure == 'hash':
        (directory / console['name']).write_bytes(b'x' * console['size'])
    elif failure == 'commit':
        release['target_commitish'] = SOURCE[:12] + 'b' * 28
    elif failure == 'tag':
        release['tag_name'] = 'native-' + 'b' * 12
        for asset in release['assets']:
            asset['browser_download_url'] = asset['browser_download_url'].replace(
                f'/{TAG}/', f"/{release['tag_name']}/")
    elif failure == 'url':
        console['browser_download_url'] += '?extra'
    elif failure == 'missing':
        release['assets'].pop()
    manifest.write_text(json.dumps(release))
    before = lock.read_bytes()
    result = run_tool(directory, lock, options=('--mac-only', '--cli-pin', str(cli)))
    if failure:
        assert result.returncode == 1 and message in result.stderr, result.stderr
        assert lock.read_bytes() == before and cli.read_text() == '{}'
        return
    assert result.returncode == 0, result.stderr
    assert json.loads(cli.read_text()) == expected
    records = json.loads(lock.read_text())['native_artifacts']
    assert set(records) == set(NAMES)
    for name in NAMES:
        for target in TARGETS[2:]:
            assert records[name]['targets'][target] == old[name]['targets'][target]


@pytest.mark.parametrize('alias', ['same-path', 'symlink', 'hardlink'])
def test_refuses_aliased_outputs(assets, alias):
    directory, lock = assets
    add_console(directory)
    cli = lock if alias == 'same-path' else lock.with_name('cli.json')
    if alias == 'symlink':
        cli.symlink_to(lock)
    elif alias == 'hardlink':
        cli.hardlink_to(lock)
    before = lock.read_bytes()
    result = run_tool(directory, lock, options=('--cli-pin', str(cli)))
    assert result.returncode == 1 and b'must be separate' in result.stderr, result.stderr
    assert lock.read_bytes() == cli.read_bytes() == before


@pytest.mark.parametrize('inside', ['release-json', 'release-dir'])
def test_refuses_outputs_inside_release_input(assets, inside):
    directory, lock = assets
    add_console(directory)
    cli = directory / ('release.json' if inside == 'release-json' else 'cli.json')
    release = (directory / 'release.json').read_bytes()
    before = lock.read_bytes()
    result = run_tool(directory, lock, options=('--cli-pin', str(cli)))
    assert result.returncode == 1, result.stderr
    assert b'outside the release directory' in result.stderr, result.stderr
    assert (directory / 'release.json').read_bytes() == release and lock.read_bytes() == before
    assert inside == 'release-json' or not cli.exists()


def test_read_only_lock_is_refused_before_updating_console(assets):
    directory, lock = assets
    add_console(directory)
    cli = lock.with_name('cli.json')
    cli.write_bytes(b'{}')
    before = lock.read_bytes()
    lock.chmod(0o444)
    result = run_tool(directory, lock, options=('--cli-pin', str(cli)))
    assert result.returncode == 1 and b'not writable' in result.stderr, result.stderr
    assert str(lock).encode() in result.stderr
    assert lock.read_bytes() == before and cli.read_bytes() == b'{}'


def test_second_replace_failure_names_updated_output_and_rerun_converges(
    assets, capsys, monkeypatch,
):
    import os

    from tools import native_release

    directory, lock = assets
    expected = add_console(directory)
    cli = lock.with_name('cli.json')
    before = lock.read_bytes()
    command = ['--directory', str(directory), '--lock', str(lock), '--source', SOURCE,
               '--cli-pin', str(cli)]
    real_replace = os.replace

    def fail_lock_replace(src, dst):
        if dst == lock:
            raise OSError('injected replace failure')
        real_replace(src, dst)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, 'replace', fail_lock_replace)
        with pytest.raises(SystemExit) as error:
            native_release.main(command)
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert f'updated {cli}' in message and f'could not replace {lock}' in message
    assert 'rerun the same command to converge' in message
    assert 'injected replace failure' in message
    assert lock.read_bytes() == before
    console = cli.read_bytes()
    assert json.loads(console) == expected
    assert set(lock.parent.iterdir()) == {directory, lock, cli}
    assert native_release.main(command) == 0
    assert cli.read_bytes() == console
    assert set(json.loads(lock.read_bytes())['native_artifacts']) == set(NAMES)


def test_undeletable_temporary_file_is_named_after_the_publish_error(
    assets, capsys, monkeypatch,
):
    import os
    from pathlib import Path

    from tools import native_release

    directory, lock = assets
    add_console(directory)
    cli = lock.with_name('cli.json')
    before = lock.read_bytes()
    real_replace, real_unlink = os.replace, Path.unlink

    def fail_lock_replace(src, dst):
        if dst == lock:
            raise OSError('injected replace failure')
        real_replace(src, dst)

    def fail_unlink(self, missing_ok=False):
        raise OSError('injected unlink failure')

    with monkeypatch.context() as scoped:
        scoped.setattr(os, 'replace', fail_lock_replace)
        scoped.setattr(Path, 'unlink', fail_unlink)
        with pytest.raises(SystemExit) as error:
            native_release.main(['--directory', str(directory), '--lock', str(lock),
                                 '--source', SOURCE, '--cli-pin', str(cli)])
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert 'injected replace failure' in message
    leftover = [p for p in lock.parent.iterdir() if p not in {directory, lock, cli}]
    assert len(leftover) == 1 and f'could not remove temporary file(s): {leftover[0]}' in message
    assert lock.read_bytes() == before
    real_unlink(leftover[0])


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
    assert 'for name in ' + ' '.join(NAMES) + ' $console; do' in build
    assert '*-apple-darwin' in job['steps'][0]['with']['pattern']
    assert '"$mir" --help' in build and '"$mir" runtime-manifest create' in build
    matrix = workflow['jobs']['build']['strategy']['matrix']['include']
    assert isinstance(matrix, str)
    assert '(!inputs.publish || !inputs.mac_only) &&' in matrix
    assert "|| ''" in matrix
    _, darwin, other, _ = re.findall(r"'([^']*)'", matrix)
    assert [row['target'] for row in json.loads(f'[{darwin}]')] == list(TARGETS[:2])
    other_rows = json.loads(f'[{other.removeprefix(",")}]')
    assert [row['target'] for row in other_rows] == list(TARGETS[2:])


@pytest.fixture
def staged_publish(assets, mac_only):
    directory, lock = assets
    add_console(directory)
    workflow = yaml.safe_load((ROOT / '.github/workflows/native-artifacts.yml').read_text())
    publish = next(step['run'] for step in workflow['jobs']['publish']['steps'] if 'run' in step)
    output = directory.with_name('dist-native')
    output.mkdir()
    release = json.loads((directory / 'release.json').read_text())
    for asset in release['assets']:
        name = asset['name']
        if not mac_only or name.endswith(('-apple-darwin', '-apple-darwin.txt')):
            (output / name).write_bytes((directory / name).read_bytes())
    calls = lock.with_name('gh-calls')

    def run(*, existing=None):
        fake_gh = '''
gh() {
  printf '%s\\n' "$2" >> "$CALLS"
  if [[ "$2" == view ]]; then
    [[ "$EXISTS" == true ]] || return 1
    if [[ "$#" -gt 3 ]]; then printf '%s\\n' "$EXISTING"; fi
  fi
}
'''
        return subprocess.run(
            ['bash', '-c', fake_gh + publish], cwd=output.parent,
            env={'PATH': '/usr/bin:/bin:/sbin', 'SOURCE_SHA': SOURCE,
                 'MAC_ONLY': str(mac_only).lower(),
                 'CALLS': str(calls), 'EXISTS': str(existing is not None).lower(),
                 'EXISTING': '\n'.join(existing or [])},
            capture_output=True,
        )

    return output, calls, run


@pytest.mark.parametrize(('mac_only', 'count'), [(False, 47), (True, 20)])
@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_publish_requires_exact_asset_count(staged_publish, count, delta):
    output, calls, run = staged_publish
    if delta < 0:
        (output / 'SHA256-aarch64-apple-darwin.txt').unlink()
    elif delta > 0:
        (output / 'extra-apple-darwin').touch()
    assert len(list(output.iterdir())) == count + delta
    result = run()
    if delta == 0:
        assert result.returncode == 0, result.stderr
        assert calls.read_text().splitlines() == ['view', 'create', 'upload']
    else:
        assert result.returncode != 0
        assert not calls.exists()


@pytest.mark.parametrize('mac_only', [False, True])
@pytest.mark.parametrize('unexpected', [False, True])
def test_republish_requires_existing_assets_in_publish_list(staged_publish, unexpected):
    _, calls, run = staged_publish
    existing = ['mir-x86_64-apple-darwin']
    if unexpected:
        existing.append('old-tool-x86_64-apple-darwin')
    result = run(existing=existing)
    if unexpected:
        assert result.returncode != 0
        assert b'old-tool-x86_64-apple-darwin' in result.stderr
        assert calls.read_text().splitlines() == ['view', 'view']
    else:
        assert result.returncode == 0, result.stderr
        assert calls.read_text().splitlines() == ['view', 'view', 'edit', 'upload']


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
    expected = add_console(directory)
    workflow = yaml.safe_load((ROOT / '.github/workflows/native-artifacts.yml').read_text())
    steps = workflow['jobs']['build']['steps']
    digest = next(step['run'] for step in steps if step.get('name') == 'digest')
    crate = tmp_path / 'build/native/handoff-packet'
    crate.mkdir(parents=True)
    output = tmp_path / 'build/dist-native'
    for target in TARGETS:
        names = (*NAMES, 'mir') if target in TARGETS[:2] else NAMES
        for name in names:
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
        for name in [f'SHA256-{target}.txt', *(f'{n}-{target}{suffix}' for n in names)]:
            assert (output / name).read_bytes() == (directory / name).read_bytes()
    (output / 'release.json').write_bytes((directory / 'release.json').read_bytes())
    cli = tmp_path / 'cli-native-artifacts.json'
    assert run_tool(output, lock, options=('--cli-pin', str(cli))).returncode == 0
    assert json.loads(cli.read_text()) == expected


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


def test_native_workflow_smokes_delegation_gate():
    workflow = yaml.safe_load((ROOT / '.github/workflows/native-artifacts.yml').read_text())
    smoke = next(step['run'] for step in workflow['jobs']['build']['steps']
                 if step.get('name') == 'smoke run')
    assert 'delegation-gate${{ matrix.exe }}' in smoke


def test_rejects_missing_project_hooks_windows_asset_without_lock_writes(assets):
    directory, lock = assets
    path = directory / 'release.json'
    release = json.loads(path.read_text())
    missing = 'project-hooks-x86_64-pc-windows-msvc.exe'
    release['assets'] = [asset for asset in release['assets'] if asset['name'] != missing]
    (directory / missing).unlink()
    path.write_text(json.dumps(release))
    before = lock.read_bytes()
    result = run_tool(directory, lock)
    assert result.returncode == 1 and b'incomplete release' in result.stderr
    assert lock.read_bytes() == before


def test_native_workflow_smokes_project_hooks():
    workflow = yaml.safe_load((ROOT / '.github/workflows/native-artifacts.yml').read_text())
    smoke = next(step['run'] for step in workflow['jobs']['build']['steps']
                 if step.get('name') == 'smoke run')
    assert 'project-hooks${{ matrix.exe }}' in smoke
    assert 'mir-project-hooks-v1' in smoke
    assert '--mir-warmup' in smoke
