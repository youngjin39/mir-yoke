"""Freeze verifier records from 1324a3c, without importing the working tree."""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

SOURCE_REVISION = "4343aba88e811f14f6147a9a9b818b6fb346bec8"


def main():
    with tempfile.TemporaryDirectory() as temporary:
        capture(Path(temporary))


def capture(scratch):
    for name in [
        "mir",
        "mir.core",
        "mir.core.adoption",
        "mir.cli",
        "mir.core.adoption._filesystem",
    ]:
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    for name, source in [
        ("mir.core.adoption.runtime", "src/mir/core/adoption/runtime.py"),
        ("mir.cli.runtime_manifest", "src/mir/cli/runtime_manifest.py"),
        ("mir.cli.__main__", "src/mir/cli/__main__.py"),
    ]:
        output = scratch / (name.rsplit(".", 1)[-1] + ".py")
        output.write_bytes(subprocess.check_output(["git", "show", f"{SOURCE_REVISION}:{source}"]))
        spec = importlib.util.spec_from_file_location(name, output)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        if name == "mir.cli.__main__":
            sys.modules["mir.cli"].SUBCOMMANDS = {
                "runtime-manifest": sys.modules["mir.cli.runtime_manifest"].main
            }
        spec.loader.exec_module(module)
    cli = sys.modules["mir.cli.__main__"]
    root = scratch / "oracle-root"
    root.mkdir(exist_ok=True)
    manifest = root / "manifest.json"
    base = (
        '{"schema_version":1,"entries":[],"source_url":"url",'
        '"source_commit":"commit","constraints_sha256":"digest"'
    )
    cases = [
        ("nonfinite-extra", (base + ',"extra":NaN}').encode()),
        ("overflow-extra", (base + ',"extra":1e400}').encode()),
        ("surrogate-extra", (base + ',"extra":"\\ud800"}').encode()),
        ("numeric-schema", (base.replace(":1,", ":1.0,") + "}").encode()),
        ("boolean-schema", (base.replace(":1,", ":true,") + "}").encode()),
        ("source-drift", (base.replace('"commit"', '"wrong"') + "}").encode()),
        (
            "source-precedes-entries",
            (
                base.replace('"commit"', '"wrong"').replace('"entries":[]', '"entries":null') + "}"
            ).encode(),
        ),
        ("entries-null", (base.replace('"entries":[]', '"entries":null') + "}").encode()),
        ("nan-schema", (base.replace(":1,", ":NaN,") + "}").encode()),
        ("bad-utf8", b"\xff"),
        ("truncated-utf8", b"\xe2\x82"),
        ("utf8-bom", b"\xef\xbb\xbf{}"),
        ("utf16", b"\xff\xfe{\0}\0"),
        ("bad-escape", b'{"x":"\\uZZZZ"}'),
        ("integer-limit", (base + ',"extra":' + "9" * 4301 + "}").encode()),
        ("deep-extra", (base + ',"extra":' + "[" * 5000 + "0" + "]" * 5000 + "}").encode()),
        (
            "surrogate-path",
            (base.replace('"entries":[]', '"entries":[{"path":"\\udcff"}]') + "}").encode(),
        ),
    ]
    cases.extend(
        (f"depth-{depth}", ("[" * depth + "0" + "]" * depth).encode())
        for depth in range(9994, 9999)
    )
    records = []
    for name, body in cases:
        manifest.write_bytes(body)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(
                    [
                        "runtime-manifest",
                        "verify",
                        "--runtime-root",
                        str(root),
                        "--manifest",
                        str(manifest),
                        "--source-url",
                        "url",
                        "--source-commit",
                        "commit",
                        "--constraints-sha256",
                        "digest",
                    ]
                )
            except BaseException as exc:
                code = 1
                print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        records.append(
            dict(
                name=name,
                body_hex=body.hex(),
                stdout=out.getvalue(),
                stderr=err.getvalue(),
                code=code,
            )
        )
    destination = Path(__file__).parent / "fixtures/runtime_manifest_verify_1324a3c.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(dict(pin="1324a3c", records=records), indent=2) + "\n")
    print(f"captured {len(records)} records to {destination}")


if __name__ == "__main__":
    main()
