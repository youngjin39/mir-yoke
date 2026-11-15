"""Select P4 captured rows under UNIFY2-S5's explicit A authority, not a recovered oracle."""

import argparse
import hashlib
import json
import re
from pathlib import Path

CANDIDATE = '4eb154b47a289cf6a628e9d8dda31fc3bc11b464'
FIELD = re.compile(r'("relation_project_path"\s*:\s*)("(?:\\.|[^"\\])*")')


def normalize(value, root):
    """Change only the synthetic metadata root, preserving all other row bytes."""
    if isinstance(value, list):
        return [normalize(item, root) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item, root) for key, item in value.items()}
    if isinstance(value, str):
        return FIELD.sub(
            lambda m: m[1] + '"<tmp>"' if json.loads(m[2]) == root else m[0], value,
        )
    return value


def select(path):
    capture = json.loads(path.read_bytes())
    probe = capture['probes']['ingest-candidate']
    assert capture['kind'] == 'WINDOWS_CAPTURE'
    assert probe['platform'] == 'win32' and probe['reference_pin'] == CANDIDATE
    records = {row['name']: row for row in probe['records']}
    assert len(records) == 6
    native = {row['mode']: row for row in capture['native_diagnostics']
              if row['route'] == 'ingest'}
    selected = {}
    for index in range(3):
        steps = []
        for step in ('first', 'repeat'):
            row = records[f'b11.ingest.paths.{index}.windows.{step}']
            assert row['oracle_authority'] == 'UNKNOWN; candidate diagnostics only'
            assert row['exit'] == 0 and row['exception'] is None
            assert row['stdout']['tokenized_hex'] == row['stderr']['tokenized_hex'] == ''
            steps.append(normalize(row['result'], rf'{{ROOT}}\ingest-{index}'))
        actual = native[f'paths.{index}']
        assert actual['exit'] == 0 and actual['stderr']['tokenized_hex'] == ''
        assert normalize(actual['value'], rf'\\?\{{ROOT}}\native-ingest-paths.{index}') == steps
        selected[f'paths.{index}'] = {'value': steps}
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_a', type=Path)
    parser.add_argument('run_b', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    records = select(args.run_a)
    assert records == select(args.run_b), 'P4 rows differ between captures'
    provenance = {
        'original_reference_pin': 'UNKNOWN', 'candidate_pin': CANDIDATE,
        'authority': 'unify2.md UNIFY2-S5: triage diagnosis plus candidate/native agreement => A',
        'capture_sha256': [hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (args.run_a, args.run_b)],
    }
    lines = [json.dumps({'provenance': provenance}, ensure_ascii=True)[:-1] + ', "records": {']
    lines.extend(json.dumps(key) + ': ' + json.dumps(value, ensure_ascii=True) + comma
                 for (key, value), comma in zip(records.items(), [',', ',', ''], strict=True))
    args.output.write_text('\n'.join(lines) + '\n}}\n', encoding='ascii')
    print('A: 6/6 full candidate/native rows agree in both PC captures; original pin UNKNOWN')


if __name__ == '__main__':
    main()
