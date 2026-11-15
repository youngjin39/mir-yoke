"""Package pinned B07 sources and pure Python YAML for offline isolated capture."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import yaml
from capture_wt_core_b07_paths import PIN, SCENARIO_PIN


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--commands', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    package = args.scratch.resolve()
    assert not package.is_relative_to(repo)
    package.mkdir(parents=True, exist_ok=False)
    reference = package / 'reference'
    paths = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', PIN, 'src/mir', 'tests'], cwd=repo,
        text=True).splitlines()
    for relative in paths:
        if not (relative in {
            'src/mir/__init__.py', 'src/mir/core/__init__.py',
            'src/mir/core/engine/__init__.py', 'src/mir/core/relations.py',
            'src/mir/core/memory_relations.py',
            'tests/test_w2_b07_relations_query_frozen.py',
        } or relative.startswith('src/mir/core/engine/memory/')
                and relative.endswith(('.py', '.sql'))):
            continue
        target = reference / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(['git', 'show', f'{PIN}:{relative}'], cwd=repo))
    (reference / 'tests/query-all-scenarios.py').write_bytes(subprocess.check_output(
        ['git', 'show', f'{SCENARIO_PIN}:tests/test_w2_b07_relations_query_frozen.py'], cwd=repo))
    # Production reference files are unchanged between the two pins.
    subprocess.run(['git', 'diff', '--exit-code', PIN, SCENARIO_PIN, '--',
                    'src/mir/core/memory_relations.py', 'src/mir/core/relations.py',
                    'src/mir/core/engine/memory'], cwd=repo, check=True)
    # Pure Python loader is portable across hosts; no compiled extension or install.
    for source in Path(yaml.__file__).parent.glob('*.py'):
        target = reference / 'vendor/yaml' / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    manifest = {'reference_pin': PIN, 'scenario_pin': SCENARIO_PIN,
                'yaml_version': yaml.__version__, 'sha256': {
        p.relative_to(reference).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(reference.rglob('*')) if p.is_file()}}
    (reference / 'manifest.json').write_text(
        json.dumps(manifest, indent=2) + '\n', encoding='ascii')
    (package / 'capture_wt_core_b07_paths.py').write_bytes(
        (repo / 'tests/capture_wt_core_b07_paths.py').read_bytes())
    (package / 'pc-capture-commands.txt').write_bytes(args.commands.read_bytes())
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(package.rglob('*')):
            if source.is_file():
                bundle.write(source, source.relative_to(package))


if __name__ == '__main__':
    main()
