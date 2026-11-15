"""Isolated, stdlib-only capture of the pinned B07 query path.* scenarios.

Run with python -I -X utf8. AST selection executes the exact pinned definitions,
not the unrelated database/query branches or their third-party imports. Original
package initializers accompany the sources; no live mir package is imported.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import sysconfig
import types
from dataclasses import asdict
from pathlib import Path, PurePath
from unittest import mock

PIN = 'f2a9dbf942585e0e02ed095db492d031c682d0e9'
SCENARIO_PIN = '5abaf8bb3e5382be5e189b8d250e97f60718d115'
CASES = ('missing', 'directory', 'symlink', 'regular', 'parent')


def tokenize(text: str, root: PurePath) -> str:
    """Tokenize only the synthetic root and its drive, preserving suffix bytes."""
    escaped = json.dumps(str(root))[1:-1]
    text = text.replace(escaped, '{ROOT}').replace(str(root), '{ROOT}')
    return text.replace(root.drive, '{DRIVE}') if root.drive else text


def selected(reference: Path, relative: str, names: set[str], namespace: dict) -> None:
    source = reference / relative
    tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
    nodes = [node for node in tree.body if (
        isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ) or (
        isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
    )]
    found = {node.name for node in nodes if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    found.update(t.id for node in nodes if isinstance(node, ast.Assign)
                 for t in node.targets if isinstance(t, ast.Name))
    assert found == names, (relative, found, names)
    assert source.resolve().is_relative_to(reference)
    namespace['__file__'] = str(source)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)


def all_records(reference: Path, scratch: Path) -> dict:
    """Replay every pinned scenario, including platform-sensitive raw byte counts."""
    from mir.core import memory_relations as m
    from mir.core.engine.memory import relation_facts as f
    from mir.core.engine.memory import store

    def compact(value):
        if isinstance(value, str) and len(value) > 256:
            return {'len': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest()}
        if isinstance(value, list):
            return [compact(v) for v in value]
        if isinstance(value, dict):
            return {k: compact(v) for k, v in value.items()}
        return value

    def normalize(value, root):
        if isinstance(value, str):
            try:
                metadata = json.loads(value)
            except ValueError:
                return value
            if isinstance(metadata, dict) and metadata.get('relation_project_path') == str(root):
                return re.sub(r'("relation_project_path"\s*:\s*)"(?:\\.|[^"\\])*"',
                              r'\1"<tmp>"', value)
        elif isinstance(value, list):
            return [normalize(v, root) for v in value]
        elif isinstance(value, dict):
            return {k: '<tmp>' if k == 'relation_project_path' and v == str(root)
                    else normalize(v, root) for k, v in value.items()}
        return value

    namespace = {'__name__': 'pinned_all_scenarios', 'm': m, 'f': f, 'store': store,
                 'json': json, 'hashlib': hashlib, 'sqlite3': sqlite3, 'asdict': asdict,
                 'mock': mock, 'CLOCK': '2001-02-03T04:05:06.000000+00:00',
                 'rows': lambda conn, sql: [list(row) for row in conn.execute(sql)]}
    source = reference / 'tests/query-all-scenarios.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    # Keep the exact scenario and CASES construction; exclude imports and fixture I/O.
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'scenario':
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {'DECLS', 'CASES'}
            or isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
            and t.value.id == 'CASES' for t in node.targets
        ):
            nodes.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value.func
            if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name) \
                    and call.value.id == 'CASES':
                nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    for name, module in sys.modules.copy().items():
        if name == 'mir' or name.startswith('mir.') or name == 'yaml' or name.startswith('yaml.'):
            assert Path(module.__file__).resolve().is_relative_to(reference), name
    assert len(namespace['CASES']) == 71
    records = {}
    for name, case in sorted(namespace['CASES'].items()):
        root = scratch / name
        root.mkdir()
        try:
            value = case(root)
        except Exception as exc:  # noqa: BLE001 - exact reference exception observer
            result = {'error': [type(exc).__name__, tokenize(str(exc), root)]}
        else:
            if name.startswith('path.'):
                value = tokenize(value, root)
            result = {'value': compact(normalize(value, root))}
        records[name] = result
    assert records['anchor.1'] == {'error': ['RelationError', 'unknown anchor']}
    assert records['source.missing']['value']['reason'] == 'unavailable relation source'
    return records


def capture(reference: Path, scratch: Path, output: Path, full: bool = False) -> None:
    manifest = json.loads((reference / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['reference_pin'] == PIN
    for relative, digest in manifest['sha256'].items():
        source = (reference / relative).resolve()
        assert source.is_relative_to(reference)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest, relative
    # Only this synthetic source root is eligible for repository imports.
    stdlib = Path(sysconfig.get_path('stdlib')).resolve()
    sys.path[:] = [str(reference / 'src'), *(
        p for p in sys.path if p and (
            Path(p).resolve().is_relative_to(stdlib)
            or Path(p).resolve().is_relative_to(Path(sys.base_prefix))
        ) and 'site-packages' not in Path(p).parts
    )]
    sys.path.insert(1, str(reference / 'vendor'))
    assert not any(n == 'mir' or n.startswith('mir.') for n in sys.modules)
    relation_ns = {'__name__': 'pinned_relations'}
    selected(reference, 'src/mir/core/relations.py', {'RelationError'}, relation_ns)
    memory_ns = {'__name__': 'pinned_memory_relations', 'Path': Path, 'stat': stat,
                 'RelationError': relation_ns['RelationError']}
    selected(reference, 'src/mir/core/memory_relations.py',
             {'_memory_db_path', '_MEMORY_RELATIONS_DB'}, memory_ns)
    scenario_ns = {'__name__': 'pinned_scenario', 'm': types.SimpleNamespace(**memory_ns)}
    selected(reference, 'tests/test_w2_b07_relations_query_frozen.py',
             {'scenario'}, scenario_ns)
    # Check every reference execution namespace before executing any scenario.
    for namespace in (relation_ns, memory_ns, scenario_ns):
        assert Path(namespace['__file__']).resolve().is_relative_to(reference)
    scratch.mkdir(parents=True, exist_ok=False)
    home = scratch / 'home'
    home.mkdir()
    os.environ.update(HOME=str(home), USERPROFILE=str(home))
    os.chdir(scratch)
    records = {}
    for mode in CASES:
        root = scratch / mode
        root.mkdir()
        root = root.resolve()
        try:
            value = scenario_ns['scenario']('path', mode)(root)
        except relation_ns['RelationError'] as exc:
            result = {'error': [type(exc).__name__, tokenize(str(exc), root)]}
        else:
            result = {'value': tokenize(value, root)}
        records[f'path.{mode}'] = result
    # Setup OSError (e.g. Windows symlink privilege) must abort, never freeze it
    # as a reference refusal. No SQLite connection is made in any path scenario.
    suffix = '\\' if os.name == 'nt' else '/'
    assert records['path.regular'] == {'value': f'{{ROOT}}{suffix}.mir{suffix}memory.db'}
    assert records['path.missing'] == {
        'error': ['RelationError', 'memory database is unavailable']}
    assert not any(n == 'mir' or n.startswith('mir.') for n in sys.modules)
    if full:
        assert manifest['scenario_pin'] == SCENARIO_PIN
        records = all_records(reference, scratch)
    payload = {'reference_pin': PIN, 'platform': sys.platform,
               'python': sys.version.split()[0], 'records': records,
               'source_sha256': manifest['sha256']}
    if full:
        payload['scenario_pin'] = SCENARIO_PIN
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + '\n', encoding='ascii')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unix-smoke', action='store_true')
    parser.add_argument('--all-records', action='store_true')
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.flags.utf8_mode:
        parser.error('use python -I -X utf8')
    if not args.unix_smoke and (sys.platform != 'win32' or sys.version_info[:3] != (3, 12, 13)):
        parser.error('Windows capture requires CPython 3.12.13; --unix-smoke is validation only')
    capture(args.reference_root.resolve(strict=True), args.scratch.resolve(), args.output.resolve(),
            args.all_records)


if __name__ == '__main__':
    main()
