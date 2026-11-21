"""Argparse records captured only from the pinned Python parser."""

import argparse
import ast
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "4343aba88e811f14f6147a9a9b818b6fb346bec8"
FIXTURE = ROOT / "tests/fixtures/runtime_manifest_args_e02a.json"
OPTIONS = [
    "--runtime-root",
    "--manifest",
    "--source-url",
    "--source-commit",
    "--constraints-sha256",
]
BASE = [part for name in OPTIONS for part in (name, "value")]


def cases():
    result = [
        [],
        ["--help"],
        ["-h"],
        ["--h"],
        ["create", "--help"],
        ["verify", "-h"],
        ["bogus"],
        ["--"],
        ["--unknown"],
        ["--unknown", "create"],
        ["--help", "bogus"],
        ["create"],
        ["verify"],
        ["create", "--"],
        ["--=x"],
        ["-hello"],
        ["create", "--=x"],
        ["create", "--help=x"],
        ["create", "-hello"],
        ["create", "--help", "--source=x"],
        ["create", "--source=x", "--help"],
        ["create", "--source", "x"],
        ["create", "--runtime-root", "--help"],
        ["create", "--runtime-root", "-"],
        ["--unknown", "create", *BASE],
        ["create", *BASE],
        ["verify", *BASE],
        ["create", *BASE, "extra"],
        ["create", *BASE, "--", "extra"],
        ["create", *BASE, "--unknown=x"],
        ["create", *BASE, "--", "--help"],
        ["create", *BASE, "--runtime-root", "./a//b/"],
        ["create", *BASE, "--manifest", "//a//./b/"],
        ["create", *BASE, "--manifest="],
        ["create", *BASE, "--source-url", "\uac00"],
        ["create", *BASE, "--source-url", "a\nb"],
    ]
    for token in [
        "--runtime",
        "--r",
        "--m",
        "--s",
        "--source",
        "--source-",
        "--source-u",
        "--source-c",
        "--constraints",
        "--",
        "-x",
        "-h=x",
        "--=",
        "--h=x",
    ]:
        result.extend([["create", token], ["create", *BASE, token, "tail"]])
    for value in [
        "-1",
        "-.5",
        "-1.5",
        "-1.",
        "-1e3",
        "--bad",
        "--source-url=x",
        "-x y",
        "",
        "-",
        "--",
    ]:
        for name in OPTIONS:
            result.append(["create", *BASE, name, value])
            result.append(["create", *BASE, name + "=" + value])
    for token in [
        "-hh=x",
        "-hh-",
        "-hhh=",
        "-h-h",
        "-hhh",
        "\u2028",
        "\u200b",
        "\ue000",
        "\u1c89",
        "-\u0661",
        "-\u0661.\u0662",
        "-1\n",
        "\udcff",
        "--bad\udcff",
        "--help=\udcff",
        "-hh=\udcff",
        "-hh-\udcff",
    ]:
        result.extend([[token], ["create", token], ["create", *BASE, "--source-url", token]])
    for name in OPTIONS:
        result.extend(
            [
                ["create", *BASE, name + "=\udcff"],
                ["create", name],
                ["create", name + "=first", name + "=last"],
                ["create", *BASE, name, "replacement"],
                ["create", *BASE, name + "=replacement"],
            ]
        )
    return result


def capture():
    source = subprocess.check_output(
        ["git", "show", f"{SOURCE_REVISION}:src/mir/cli/runtime_manifest.py"],
        cwd=ROOT,
        text=True,
    )
    function = next(
        n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_parse"
    )
    scope = {"argparse": argparse, "Path": Path}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<pinned-parser>", "exec"), scope)
    records = []
    for argv in cases():
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                ns = vars(scope["_parse"](argv))
                command = ns.pop("command")
                record = {
                    "command": command,
                    "options": {"--" + k.replace("_", "-"): str(v) for k, v in ns.items()},
                }
            except SystemExit as exc:
                record = {
                    "code": exc.code,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                }
        records.append({"argv": argv, "result": record})
    FIXTURE.write_text(
        json.dumps({"pin": "1324a3c", "records": records}, ensure_ascii=True, indent=2) + "\n"
    )


if __name__ == "__main__" and sys.argv[1:] == ["--capture"]:
    capture()
    sys.exit(0)


@pytest.fixture(scope="module")
def parser_binary():
    with tempfile.TemporaryDirectory(prefix="manifest-parser-") as tmp:
        yield build_parser(Path(tmp))


def build_parser(directory):
    wrapper = directory / "parser.rs"
    module = ROOT / "native/handoff-packet/src/runtime_manifest_args.rs"
    wrapper.write_text(
        """#[path = MODULE]
mod parser;
fn hex(s: &[u8]) -> String { s.iter().map(|b| format!("{b:02x}")).collect() }
fn main() {
    match parser::parse(std::env::args_os().skip(1).collect()) {
        parser::Parsed::Run {command, options} => {
            println!("run\\n{}", hex(command.as_bytes()));
            for (k,v) in options {
                println!("{} {}", hex(k.as_bytes()), hex(v.as_encoded_bytes()));
            }
        }
        parser::Parsed::Exit {code, stdout, stderr} => {
            println!("exit\\n{}\\n{}\\n{}", code,
                hex(stdout.as_bytes()), hex(stderr.as_bytes()));
        }
    }
}
""".replace("MODULE", json.dumps(str(module)))
    )
    binary = directory / "parser"
    crate = ROOT / "native/handoff-packet"
    subprocess.run(["cargo", "build", "--offline", "--locked", "--lib"], cwd=crate, check=True)
    deps = crate / "target/debug/deps"
    library = crate / "target/debug/libhandoff_packet.rlib"
    subprocess.run(
        [
            "rustc",
            "--edition=2024",
            str(wrapper),
            "-L",
            "dependency=" + str(deps),
            "--extern",
            "handoff_packet=" + str(library),
            "-o",
            str(binary),
        ],
        cwd=crate,
        check=True,
    )
    return binary


@pytest.mark.parametrize("record", json.loads(FIXTURE.read_text())["records"])
def test_parser_reference(parser_binary, record):
    result = subprocess.run(
        [str(parser_binary), *record["argv"]], capture_output=True, text=True, check=True
    )
    lines = result.stdout.splitlines()
    def decode(s):
        return bytes.fromhex(s).decode("utf-8", "surrogateescape")
    if lines[0] == "run":
        actual = {
            "command": decode(lines[1]),
            "options": {
                decode(k): decode(v) for k, v in (line.split(" ", 1) for line in lines[2:])
            },
        }
    else:
        actual = {"code": int(lines[1]), "stdout": decode(lines[2]), "stderr": decode(lines[3])}
    assert actual == record["result"], record["argv"]
