"""Package two pinned, isolated Windows probes; never derive records from Rust."""

from __future__ import annotations

import argparse
import io
import subprocess
import tarfile
import zipfile
from pathlib import Path

PINS = {
    "b30": ("a61c3013", "test_w2_b30_capability_frozen.py"),
    "b14": ("6b8796fa", "test_w2_b14_gc_doctor_frozen.py"),
}
RUNNER = r'''
import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--case', choices=['b30', 'b14'], required=True)
p.add_argument('--scratch', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--dependencies', type=Path)
p.add_argument('--all-records', action='store_true')
a = p.parse_args()
assert sys.version_info[:3] == (3, 12, 13), sys.version
bundle = Path(__file__).resolve().parent
root = a.scratch.resolve()
root.mkdir(parents=True, exist_ok=False)
os.environ['HOME'] = str(root / 'home')
os.environ['USERPROFILE'] = str(root / 'home')
(root / 'home').mkdir()
os.chdir(root)
shutil.copytree(bundle / a.case, root / 'reference')
source = root / 'reference'
deps = root / 'deps'
deps.mkdir()
if a.dependencies:
    for pattern in ['pydantic*', 'annotated_types*', 'typing_extensions*', 'typing_inspection*',
                    'httpx*', 'httpcore*', 'anyio*', 'certifi*', 'h11*', 'idna*',
                    'sniffio*', 'yaml*',
                    'jsonschema*', 'referencing*', 'rpds*', 'attrs*', 'attr']:
        for item in a.dependencies.glob(pattern):
            if item.is_dir():
                shutil.copytree(item, deps / item.name)
            else:
                shutil.copy2(item, deps / item.name)
sys.path[:] = [str(source / 'src'), str(deps)] + [
    x for x in sys.path if x and 'site-packages' not in x and Path(x).resolve() != bundle
]
def provenance():
    for name, module in list(sys.modules.items()):
        if name == 'mir' or name.startswith('mir.'):
            path = getattr(module, '__file__', None)
            assert path and Path(path).resolve().is_relative_to(root), (name, path)
probe = 'oracle-all.py' if a.all_records else 'oracle.py'
spec = importlib.util.spec_from_file_location('oracle', source / probe)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
provenance()
case = 'hooks.check.uninstalled' if a.case == 'b30' else 'doctor.missing.True'
# Keep the original single-record capture byte-compatible. Add every unobserved
# non-privileged route; the existing replayers already identify these exemptions.
exempt = {'changes.snapshot_and_diff', 'native.project_hooks.linked',
          'native.project_hooks.linked-parent', 'hooks.path.normal',
          'hooks.check.not-executable'} if a.case == 'b30' else {'doctor.relative_link.True'}
names = sorted(set(oracle.CASES) - exempt) if a.all_records else [case]
records = {}
for index, name in enumerate(names):
    tmp = root / ('case-' + str(index) if a.all_records else 'case')
    tmp.mkdir()
    assert not (tmp / '.mir' / 'db').exists()
    provenance()
    record = oracle.observe(oracle.CASES[name], tmp)
    provenance()
    if name == 'hooks.check.uninstalled':
        assert record['value'][0] == 1 and 'project-hooks.json' in record['value'][1]
        assert record['value'][3:] == [{}, []]
    elif name == 'doctor.missing.True':
        assert record['value']['before'] == record['value']['after'] == {'exists': False}
        assert record['value']['command']['exit'] == 1
        assert 'memory database is missing:' in record['value']['command']['stdout']
    text = json.dumps(record, ensure_ascii=True, sort_keys=True)
    # Redact at each JSON/repr nesting level; never alter suffixes.
    for path, token in [(str(tmp), '{ROOT}'), (str(root), '{SCRATCH}')]:
        plain = path.removeprefix(chr(92) * 2 + '?' + chr(92))
        spellings = {path, plain, plain.replace(chr(92), '/')}
        for _ in range(4):
            spellings |= {json.dumps(x)[1:-1] for x in spellings}
        for spelling in sorted(spellings, key=len, reverse=True):
            text = text.replace(spelling, token)
    if root.drive:
        text = text.replace(root.drive, '{DRIVE}')
    assert str(Path.home()) not in text
    records[name] = json.loads(text)
if a.all_records:
    text = json.dumps({'records': records, 'exempt': sorted(exempt)},
                      ensure_ascii=True, sort_keys=True)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(text + '\n', encoding='utf-8')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("capture.py", RUNNER)
        for case, (pin, test) in PINS.items():
            archive = subprocess.check_output(
                ["git", "archive", pin, "src/mir"], cwd=repo
            )
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                for member in tar:
                    if member.isfile():
                        out.writestr(f"{case}/{member.name}", tar.extractfile(member).read())
            source = subprocess.check_output(
                ["git", "show", f"{pin}:tests/{test}"], cwd=repo, text=True
            )
            # Preserve original case/observe bodies; omit only pytest registration.
            source = source.split("\nRECORDS =", 1)[0].replace("import pytest\n", "")
            out.writestr(f"{case}/oracle.py", source)
            out.writestr(f"{case}/pin.txt", pin + "\n")
            # The source pins predate additive native-switch cases (B14:9, B30:1).
            # Keep their package pins and separately pin the extended probe body.
            probe_pin = "aa4fdbdb" if case == "b14" else "9497f2b0"
            extended = subprocess.check_output(
                ["git", "show", f"{probe_pin}:tests/{test}"], cwd=repo, text=True
            )
            extended = extended.split("\nRECORDS =", 1)[0].replace("import pytest\n", "")
            out.writestr(f"{case}/oracle-all.py", extended)
            out.writestr(f"{case}/oracle-all-pin.txt", probe_pin + "\n")


if __name__ == "__main__":
    main()
