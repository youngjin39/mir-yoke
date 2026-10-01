"""Generate, explicitly sync and verify the independently versioned executor base."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import pathlib
import re
import subprocess
import sys

SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = 'config/mir-executor-common.json'
CONSUMER_MANIFEST = 'tools/mir_executor/COMMON_MANIFEST.json'
PACKAGE = pathlib.PurePosixPath('tools/mir_executor')


def _hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _common_path(value: str) -> pathlib.PurePosixPath:
    path = pathlib.PurePosixPath(value)
    if (path.is_absolute() or '..' in path.parts or '\\' in value
            or not path.is_relative_to(PACKAGE) or path.suffix != '.py'
            or path == PACKAGE / 'local.py' or path.is_relative_to(PACKAGE / 'tests/local')):
        raise ValueError(f'Invalid common path: {value}')
    return path


def _read_manifest(path: pathlib.Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError(f'Invalid executor manifest: {path}')
    files = data.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError(f'Invalid executor manifest file map: {path}')
    for name, digest in files.items():
        _common_path(name)
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError(f'Invalid sha256 for {name}')
    return data


def _no_symlink(root: pathlib.Path, relative: str) -> pathlib.Path:
    path = root
    for part in pathlib.PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Refusing symlink common path: {path}')
    return path


def _write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def generate_manifest(source_root: pathlib.Path = SOURCE_ROOT) -> dict:
    """Generate hashes, excluding optional local code and local tests."""
    source_root = pathlib.Path(source_root).resolve()
    files = {}
    package = source_root / PACKAGE
    paths = list(package.glob('*.py'))
    tiny_test = package / 'tests/test_common_manifest.py'
    if tiny_test.is_file():
        paths.append(tiny_test)
    for path in sorted(paths):
        relative = path.relative_to(source_root).as_posix()
        if path.name == 'local.py' or 'tests/local' in relative or '__pycache__' in path.parts:
            continue
        _common_path(relative)
        files[relative] = _hash(_no_symlink(source_root, relative))
    manifest = {'version': 1, 'source_commit': 'SOURCE_COMMIT', 'files': files}
    _write_json(source_root / SOURCE_MANIFEST, manifest)
    _write_json(source_root / CONSUMER_MANIFEST, manifest)
    return manifest


def _git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ['git', '--no-optional-locks', '-C', str(root), *args], capture_output=True, text=True
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f'git failed in {root}')
    return result.stdout.strip()


def sync(target: pathlib.Path, *, source_root: pathlib.Path = SOURCE_ROOT,
         apply: bool = False) -> str:
    """Report common file changes; copy only when explicitly requested and clean."""
    target, source_root = pathlib.Path(target).resolve(), pathlib.Path(source_root).resolve()
    manifest = _read_manifest(source_root / SOURCE_MANIFEST)
    deployed = dict(manifest, source_commit=_git(source_root, 'rev-parse', 'HEAD'))
    payloads = {}
    for name, digest in manifest['files'].items():
        source = _no_symlink(source_root, name)
        if _hash(source) != digest:
            raise ValueError(f'Stale source manifest: {name}; run --generate')
        payloads[name] = source.read_bytes()
    payloads[CONSUMER_MANIFEST] = (json.dumps(deployed, indent=2, sort_keys=True) + '\n').encode()
    paths = {name: _no_symlink(target, name) for name in payloads}
    dirty = _git(target, 'status', '--porcelain', '--untracked-files=all', '--', *payloads)
    if dirty:
        raise ValueError(f'Refusing dirty common files in {target}:\n{dirty}')
    lines = [f'{"APPLY" if apply else "DRY-RUN"} {target}',
             f'Source commit: {deployed["source_commit"]}']
    for name, content in payloads.items():
        path = paths[name]
        before = path.read_bytes() if path.exists() else None
        status = 'added' if before is None else 'unchanged' if before == content else 'changed'
        additions = deletions = 0
        if before != content:
            diff = difflib.unified_diff(
                (before or b'').decode('utf-8').splitlines(),
                content.decode('utf-8').splitlines(),
            )
            for line in diff:
                additions += line.startswith('+') and not line.startswith('+++')
                deletions += line.startswith('-') and not line.startswith('---')
        lines.append(f'{name}: {status} (+{additions}/-{deletions})')
    if apply:
        for name, content in payloads.items():
            if paths[name].exists() and paths[name].read_bytes() == content:
                continue
            paths[name].parent.mkdir(parents=True, exist_ok=True)
            paths[name].write_bytes(content)
    return '\n'.join(lines)


def check(target: pathlib.Path, *, source_root: pathlib.Path | None = SOURCE_ROOT) -> list[str]:
    """Return target-manifest and optional current-source discrepancies."""
    target = pathlib.Path(target).resolve()
    errors = []
    try:
        manifest = _read_manifest(_no_symlink(target, CONSUMER_MANIFEST))
    except (ValueError, OSError) as exc:
        return [str(exc)]
    for name, digest in manifest['files'].items():
        try:
            path = _no_symlink(target, name)
            if not path.is_file() or _hash(path) != digest:
                errors.append(f'target drift: {name}')
        except ValueError as exc:
            errors.append(str(exc))
    if source_root is not None and (pathlib.Path(source_root) / SOURCE_MANIFEST).exists():
        source_root = pathlib.Path(source_root).resolve()
        source = _read_manifest(source_root / SOURCE_MANIFEST)
        for name in sorted(set(source['files']) | set(manifest['files'])):
            path = source_root / name
            digest = _hash(path) if path.is_file() else None
            if source['files'].get(name) != digest:
                errors.append(f'stale source manifest: {name}')
            if name not in manifest['files'] or manifest['files'].get(name) != digest:
                errors.append(f'source drift: {name}')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=pathlib.Path)
    parser.add_argument('--source-root', type=pathlib.Path, default=SOURCE_ROOT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--generate', action='store_true')
    action.add_argument('--apply', action='store_true')
    action.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    if not args.generate and args.target is None:
        parser.error('--target is required for sync/check')
    try:
        if args.generate:
            manifest = generate_manifest(args.source_root)
            print(f'Generated {SOURCE_MANIFEST}: {len(manifest["files"])} files')
        elif args.check:
            errors = check(args.target, source_root=args.source_root)
            print('\n'.join(errors) if errors else 'Common manifest: PASS')
            return int(bool(errors))
        else:
            print(sync(args.target, source_root=args.source_root, apply=args.apply))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
