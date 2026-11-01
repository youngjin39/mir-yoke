"""B1 evaluator differential proof with its original isolated test dispatcher."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / '.claude/hooks/_lib/bootstrap-gate.sh'
NATIVE = ROOT / 'native/handoff-packet/target/release/bootstrap-gate'
CASES = (
    'ready', 'missing_evidence', 'duplicate_evidence', 'omitted_evidence',
    'hash_drift', 'source_drift', 'manifest_drift', 'traversal', 'absolute',
    'leaf_symlink', 'ancestor_symlink', 'empty_evidence', 'missing_manifest',
    'manifest_symlink', 'receipt_symlink', 'malformed_receipt', 'malformed_manifest',
    'exotic_path', 'control_path', 'unsupported_mode', 'missing_receipt',
    'duplicate_declaration', 'directory_evidence', 'unicode_path', 'space_path',
    'duplicate_json_keys', 'ready_other_mode', 'ready_omitted_mode',
    'bad_hash', 'missing_hash', 'missing_path', 'evidence_nonarray', 'greenfield_ready',
)
FALLBACK = {
    'malformed_receipt', 'malformed_manifest', 'exotic_path', 'control_path',
    'unsupported_mode', 'missing_receipt', 'missing_manifest', 'duplicate_json_keys',
    'missing_hash', 'missing_path', 'evidence_nonarray', 'greenfield_ready',
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(project: Path, case: str, count: int = 1) -> None:
    if case == 'omitted_evidence':
        count = 2
    (project / '.mir/bin').mkdir(parents=True)
    (project / 'config').mkdir()
    (project / 'spec').mkdir()
    paths = [f'spec/evidence-{i}.yaml' for i in range(count)]
    if case in {'unicode_path', 'space_path', 'control_path'}:
        paths = [{'unicode_path': 'spec/\u00e9.yaml', 'space_path': 'spec/a b.yaml',
                  'control_path': 'spec/a\tb.yaml'}[case]]
    for path in paths:
        (project / path).write_bytes(b'verified: true\n')
    if case == 'traversal':
        paths = ['spec/../spec/evidence-0.yaml']
    if case == 'absolute':
        paths = [str(project / paths[0])]
    if case == 'ancestor_symlink':
        (project / 'alias').symlink_to(project / 'spec', target_is_directory=True)
        paths = ['alias/evidence-0.yaml']
    evidence = [{'path': p, 'sha256': _hash(project / p)} for p in paths]
    manifest = {'mir_yoke_source_commit': 'a' * 40,
                'surfaces': {'phase2_spec': {'evidence_paths': paths}}}
    if case == 'duplicate_declaration':
        manifest['surfaces']['phase2_spec']['evidence_paths'] = paths * 2
    manifest_path = project / 'config/bootstrap-adoption.json'
    manifest_path.write_text(json.dumps(manifest) + '\n')
    receipt = {'status': 'ready', 'mode': 'existing_repository_adoption',
               'source': {'mir_yoke_commit': 'a' * 40},
               'manifest': {'sha256': _hash(manifest_path)}, 'evidence': evidence}
    if case == 'duplicate_evidence':
        receipt['evidence'] = evidence * 2
    elif case == 'omitted_evidence':
        receipt['evidence'] = evidence[:1]
    elif case == 'empty_evidence':
        receipt['evidence'] = []
    elif case == 'ready_other_mode':
        receipt['mode'] = 'greenfield'
    elif case == 'ready_omitted_mode':
        del receipt['mode']
    elif case == 'bad_hash':
        receipt['evidence'][0]['sha256'] = 'wrong'
    elif case == 'missing_hash':
        del receipt['evidence'][0]['sha256']
    elif case == 'missing_path':
        del receipt['evidence'][0]['path']
    elif case == 'evidence_nonarray':
        receipt['evidence'] = {}
    elif case == 'greenfield_ready':
        receipt['mode'] = 'greenfield'
    elif case == 'source_drift':
        receipt['source']['mir_yoke_commit'] = 'b' * 40
    elif case == 'exotic_path':
        receipt['evidence'][0]['path'] = 42
    elif case == 'unsupported_mode':
        receipt['status'] = 'invalid'
        receipt['mode'] = 'greenfield'
    receipt_path = project / '.mir/bootstrap-receipt.json'
    receipt_path.write_text(json.dumps(receipt) + '\n')
    evidence_path = project / paths[0]
    if case in {'missing_evidence', 'leaf_symlink', 'directory_evidence'}:
        evidence_path.unlink()
        if case == 'leaf_symlink':
            target = project / 'actual.yaml'
            target.write_bytes(b'verified: true\n')
            evidence_path.symlink_to(target)
        elif case == 'directory_evidence':
            evidence_path.mkdir()
    elif case == 'hash_drift':
        evidence_path.write_bytes(b'verified: false\n')
    elif case == 'manifest_drift':
        with manifest_path.open('a') as stream:
            stream.write(' ')
    elif case in {'missing_manifest', 'greenfield_ready'}:
        manifest_path.unlink()
    elif case == 'missing_receipt':
        receipt_path.unlink()
    elif case in {'manifest_symlink', 'receipt_symlink'}:
        path = manifest_path if case == 'manifest_symlink' else receipt_path
        target = path.with_suffix('.real')
        path.rename(target)
        path.symlink_to(target)
    elif case == 'duplicate_json_keys':
        receipt_path.write_text(receipt_path.read_text().replace(
            '"status": "ready"', '"status": "invalid", "status": "ready"'))
    elif case in {'malformed_receipt', 'malformed_manifest'}:
        (receipt_path if case == 'malformed_receipt' else manifest_path).write_text('{')


def _shell(project: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ['bash', '-c', 'source "$1"; mir_bootstrap_gate_state "$2"',
         'b1-baseline', str(HELPER), str(project)], capture_output=True, check=False,
    )


def _dispatch(project: Path) -> subprocess.CompletedProcess[bytes]:
    """Legacy B1 shim isolating the evaluator from the production caller."""
    return subprocess.run(
        ['bash', '-c', '''
source "$1"
native="$2/.mir/bin/bootstrap-gate"
if [ "${MIR_NATIVE_HOOKS:-1}" != 0 ] && [ -f "$native" ] &&
   [ -x "$native" ] && [ ! -L "$native" ] &&
   [ "$("$native" --version)" = 'bootstrap-gate 0.1.0' ]; then
  result="$("$native" "$2")"
  code=$?
  if [ "$code" != 64 ]; then printf '%s\\n' "$result"; exit "$code"; fi
fi
mir_bootstrap_gate_state "$2"
''', 'b1-dispatch', str(HELPER), str(project)], capture_output=True, check=False,
    )


def _signature(result: subprocess.CompletedProcess[bytes]) -> tuple[int, bytes, bytes]:
    return result.returncode, result.stdout, result.stderr


def _compare(left: subprocess.CompletedProcess[bytes],
             right: subprocess.CompletedProcess[bytes]) -> None:
    assert _signature(left) == _signature(right)


@pytest.fixture
def native() -> Path:
    path = Path(os.environ.get('MIR_B1_NATIVE', NATIVE))
    if not path.is_file():
        if os.environ.get('MIR_B1_REQUIRE_NATIVE') == '1':
            pytest.fail(f'Native B1 evaluator required: {path}')
        pytest.skip('B1 release evaluator has not been built')
    return path


@pytest.mark.parametrize('case', CASES)
def test_adoption_native_differential(tmp_path: Path, native: Path, case: str) -> None:
    _fixture(tmp_path, case)
    baseline = _shell(tmp_path)
    _compare(baseline, _dispatch(tmp_path))
    shutil.copy2(native, tmp_path / '.mir/bin/bootstrap-gate')
    evaluated = subprocess.run([str(native), str(tmp_path)], capture_output=True, check=False)
    if case not in FALLBACK:
        assert evaluated.returncode != 64, case
        _compare(baseline, evaluated)
    else:
        assert evaluated.returncode == 64, case
        assert evaluated.stdout == evaluated.stderr == b''
    _compare(baseline, _dispatch(tmp_path))


@pytest.mark.parametrize('case', CASES)
def test_each_family_rejects_mutated_native_verdict(tmp_path: Path, case: str) -> None:
    _fixture(tmp_path, case)
    baseline = _shell(tmp_path)
    # An actual executable mutation, routed through the same dispatcher.
    wrong = 'invalid' if baseline.stdout == b'ready\n' else 'ready'
    code = 1 if wrong == 'invalid' else 0
    executable = tmp_path / '.mir/bin/bootstrap-gate'
    executable.write_text(
        '#!/bin/sh\nif [ "$1" = --version ]; then '
        'printf "bootstrap-gate 0.1.0\\n"; exit 0; fi\n'
        f'printf "{wrong}\\n"\nexit {code}\n'
    )
    executable.chmod(0o755)
    with pytest.raises(AssertionError):
        _compare(baseline, _dispatch(tmp_path))


def test_native_version(native: Path) -> None:
    result = subprocess.run([str(native), '--version'], capture_output=True, check=False)
    assert _signature(result) == (0, b'bootstrap-gate 0.1.0\n', b'')


@pytest.mark.parametrize('probe', ('rollback', 'wrong_version', 'symlink', 'nonexecutable'))
def test_prospective_dispatch_rejects_unusable_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe: str,
) -> None:
    _fixture(tmp_path, 'ready')
    executable = tmp_path / '.mir/bin/bootstrap-gate'
    version = 'wrong' if probe == 'wrong_version' else 'bootstrap-gate 0.1.0'
    executable.write_text(
        '#!/bin/sh\nif [ "$1" = --version ]; then '
        f'printf "{version}\\n"; exit 0; fi\n'
        'printf "invalid\\n"\nexit 1\n'
    )
    executable.chmod(0o644 if probe == 'nonexecutable' else 0o755)
    if probe == 'symlink':
        target = executable.with_suffix('.real')
        executable.rename(target)
        executable.symlink_to(target)
    if probe == 'rollback':
        monkeypatch.setenv('MIR_NATIVE_HOOKS', '0')
    _compare(_shell(tmp_path), _dispatch(tmp_path))


@pytest.mark.parametrize('body,change,verdict,fallback', [
    ('{"hooks":{"Z":["run"],"A":["check"]},"theme":"light"}',
     '{"theme":"dark","hooks":{"A":["check"],"Z":["run"]}}', 'ready', False),
    ('{"hooks":{"A":["run"]}}', '{"hooks":{"A":["edited"]}}', 'invalid', False),
    ('{"hooks":{"A":["\\u00e9\\ud83d\\ude00\\u007f\\n\\t\\\\\\\""]}}', None, 'ready', False),
    ('{"hooks":{"A":[1.5]}}', None, 'ready', True),
    ('{"hooks":{"A":[0,-1,9007199254740991,-9007199254740991]}}', None, 'ready', False),
    ('{"hooks":{"\\ue000":0,"\\ud83d\\ude00":1}}', None, 'ready', False),
    ('{"hooks":{"A":[9223372036854775808]}}', None, 'ready', True),
    ('{"hooks":{"A":[9007199254740993]}}', None, 'ready', True),
    ('{"hooks":{"A":[1],"A":[2]}}', None, 'ready', True),
    ('{"hooks":{"A":["\\ud800"]}}', None, 'invalid', True),
    ('{"hooks":{}}', None, 'invalid', False),
    ('{"hooks":[]}', None, 'invalid', False),
    ('[]', None, 'invalid', False),
    ('{}', None, 'invalid', False),
    ('INVALID_UTF8', None, 'ready', True),
    ('{', None, 'invalid', True),
    ('{"hooks":{"A":["ok"]}}', '{"hooks":{"A":[]}}\n{"hooks":{"A":["ok"]}}',
     'invalid', True),
])
def test_settings_hook_digest_native_parity(
    tmp_path: Path, native: Path, body: str, change: str | None,
    verdict: str, fallback: bool,
) -> None:
    _fixture(tmp_path, 'ready')
    settings = tmp_path / '.claude/settings.json'
    settings.parent.mkdir()
    if body == 'INVALID_UTF8':
        settings.write_bytes(b'{"hooks":{"A":["\xff"]}}')
    else:
        settings.write_text(body)
    canonical = subprocess.run(
        ['jq', '-S', '-c', '{hooks: .hooks}', str(settings)],
        capture_output=True, check=False,
    ).stdout
    receipt_path = tmp_path / '.mir/bootstrap-receipt.json'
    receipt = json.loads(receipt_path.read_bytes())
    receipt['evidence'] = [{'path': '.claude/settings.json',
                            'sha256': hashlib.sha256(canonical).hexdigest()}]
    manifest_path = tmp_path / 'config/bootstrap-adoption.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['surfaces']['phase2_spec']['evidence_paths'] = ['.claude/settings.json']
    manifest_path.write_text(json.dumps(manifest))
    receipt['manifest']['sha256'] = _hash(manifest_path)
    receipt_path.write_text(json.dumps(receipt))
    if change:
        settings.write_text(change)
    baseline = _shell(tmp_path)
    assert baseline.stdout == (verdict + '\n').encode()
    evaluated = subprocess.run([str(native), str(tmp_path)], capture_output=True, check=False)
    if fallback:
        assert _signature(evaluated) == (64, b'', b'')
    else:
        _compare(baseline, evaluated)
    # Exercise the production receipt-pinned fallback, including unsupported numbers.
    shutil.copy2(native, tmp_path / '.mir/bin/bootstrap-gate')
    receipt['native_evaluator'] = {'path': '.mir/bin/bootstrap-gate', 'sha256': _hash(native)}
    receipt_path.write_text(json.dumps(receipt))
    _compare(baseline, _shell(tmp_path))


def test_settings_old_whole_file_receipt(tmp_path: Path, native: Path) -> None:
    _fixture(tmp_path, 'ready')
    settings = tmp_path / '.claude/settings.json'
    settings.parent.mkdir()
    settings.write_text('{"hooks":{"A":["run"]}}')
    manifest_path = tmp_path / 'config/bootstrap-adoption.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['surfaces']['phase2_spec']['evidence_paths'] = ['.claude/settings.json']
    manifest_path.write_text(json.dumps(manifest))
    receipt_path = tmp_path / '.mir/bootstrap-receipt.json'
    receipt = json.loads(receipt_path.read_bytes())
    receipt['manifest']['sha256'] = _hash(manifest_path)
    receipt['evidence'] = [{'path': '.claude/settings.json', 'sha256': _hash(settings)}]
    receipt_path.write_text(json.dumps(receipt))
    baseline = _shell(tmp_path)
    assert baseline.stdout == b'ready\n'
    evaluated = subprocess.run([str(native), str(tmp_path)], capture_output=True, check=False)
    _compare(baseline, evaluated)
