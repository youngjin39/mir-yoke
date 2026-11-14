"""Acquire console codec facts from the pinned stdlib, with no project imports."""
import sys
import sysconfig
from pathlib import Path

assert sys.flags.isolated and sys.flags.no_site, "run with python -I -S"
assert sys.version_info[:3] == (3, 12, 13), sys.version
stdlib = Path(sysconfig.get_path("stdlib")).resolve()
sys.path[:] = [str(stdlib), str(stdlib / "lib-dynload")]

import argparse  # noqa: E402
import codecs  # noqa: E402
import encodings.aliases  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import unicodedata  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scratch", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--records-output", type=Path, required=True)
args = parser.parse_args()
assert args.scratch.is_absolute(), "--scratch must be absolute"
scratch = args.scratch.resolve()
assert args.output.is_absolute(), "--output must be absolute"
assert args.records_output.is_absolute(), "--records-output must be absolute"
scratch.mkdir(parents=True, exist_ok=True)
(scratch / "home").mkdir(exist_ok=True)
os.chdir(scratch)
for module in (codecs, encodings, encodings.aliases, unicodedata):
    assert Path(module.__file__).resolve().is_relative_to(stdlib), module.__file__


def normalized(name):
    return encodings.normalize_encoding(name.lower())


candidates = set(encodings.aliases.aliases) | set(encodings.aliases.aliases.values())
candidates.update(path.stem for path in Path(encodings.__file__).parent.glob("*.py"))
aliases, compatible, non_text = {}, set(), set()
ascii_text = "".join(map(chr, range(128)))
for candidate in sorted(candidates):
    try:
        info = codecs.lookup(candidate)
    except LookupError:
        continue
    aliases[normalized(candidate)] = info.name
    if not info._is_text_encoding:
        non_text.add(info.name)
    else:
        try:
            if ascii_text.encode(info.name) == bytes(range(128)):
                compatible.add(info.name)
        except (UnicodeError, TypeError):
            pass

# -I ignores PYTHONIOENCODING, so probe startup with -S and synthetic HOME/cwd.
# os.write proves startup succeeded without invoking the chosen text encoder.
probes, startup_unknown = [], []
for name in sorted(aliases):
    proc = subprocess.run(
        [sys.executable, "-S", "-c", "import os; os.write(1, b'STARTED\\n')"],
        cwd=scratch, env={"HOME": str(scratch / "home"), "PYTHONIOENCODING": name},
        capture_output=True, check=False,
    )
    probes.append({"codec": name, "exit": proc.returncode,
                   "stdout": proc.stdout.hex(), "stderr": proc.stderr.hex()})
    if b"LookupError: unknown encoding:" in proc.stderr:
        startup_unknown.append(name)
    elif aliases[name] in non_text:
        assert proc.returncode == 1 and b"is not a text encoding" in proc.stderr, name
    else:
        assert proc.returncode == 0 and proc.stdout == b"STARTED\n", (name, proc.stderr)
for name, module in tuple(sys.modules.items()):
    if name == "__main__":
        continue  # This acquisition script is the sole non-stdlib module.
    location = getattr(module, "__file__", None)
    if location:
        assert Path(location).resolve().is_relative_to(stdlib), (name, location)
table = {
    "python_version": sys.version,
    "unicode_version": unicodedata.unidata_version,
    "aliases": dict(sorted(aliases.items())),
    "ascii_compatible": sorted(compatible),
    "non_text": sorted(non_text),
    "startup_unknown": startup_unknown,
    "names": {str(ord(char)): unicodedata.name(char) for char in "áé€😀"},
}
records = []
for codec in ("utf-8", "utf-8-sig", "utf-16", "utf-32", "utf-16-le", "utf-16-be",
              "utf-32-le", "utf-32-be", "ascii", "latin-1", "cp1252"):
    for handler in ("strict", "ignore", "replace", "backslashreplace", "xmlcharrefreplace",
                    "namereplace", "surrogateescape", "surrogatepass"):
        for points in ([65, 233, 8364, 0x1f600, 66], [65, 0xdc80, 0xdcff, 0xd800, 66], [0x1fae8]):
            record = {"codec": codec, "handler": handler, "points": points,
                      "bom": codec in {"utf-8-sig", "utf-16", "utf-32"}}
            try:
                record["bytes"] = "".join(map(chr, points)).encode(codec, handler).hex()
            except UnicodeError as exc:
                record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            records.append(record)
args.output.write_text(json.dumps(table, separators=(",", ":"), ensure_ascii=True) + "\n")
args.records_output.write_text(json.dumps(records, separators=(",", ":")) + "\n")
(scratch / "startup-probes.json").write_text(json.dumps(probes, indent=2) + "\n")
print(json.dumps({"python": sys.version, "aliases": len(aliases),
                  "canonical": len(set(aliases.values())),
                  "ascii_compatible": len(compatible), "non_text": sorted(non_text)}))
