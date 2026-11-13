"""Admission callbacks retain their module and argparse process semantics."""

import pytest
from test_executor_dispatch_stage_d import GOLDEN, SUPPORT, binary, oracle  # noqa: F401


@pytest.mark.parametrize("mode",
                         ["state", "help", "unknown", "refusal", "denied", "redirect", "timeout"])
@pytest.mark.parametrize("route", ["binary", "module"])
def test_dispatch_parser_callback(binary, oracle, tmp_path, mode, route):  # noqa: F811
    reference, database = oracle
    name = "crossroot-deny" if mode == "denied" else "success"
    case = next(c for c in GOLDEN["cases"] if c["name"] == name)
    observations = []
    for label, selected in (("reference", "reference"), ("native", route)):
        home = (tmp_path / label / "home").resolve()
        setup = SUPPORT["seed"](home, case, reference, database, binary)
        local = home / "tools/mir_executor/local.py"
        if mode == "denied":
            local = home / "target/tools/mir_executor/local.py"
            local.parent.mkdir(parents=True)
            local.write_text("from pathlib import Path\n"
                             "Path(__file__).parents[2].joinpath('imported').touch()\n")
        else:
            with local.open("a") as stream:
                stream.write("\nROOT.joinpath('parser-imports').open('a').write('import\\n')\n"
                    "_parsed = False\ndef register_execute_options(parser):\n"
                    "    global _parsed\n    print('parser stdout')\n"
                    "    print('parser stderr', file=__import__('sys').stderr)\n"
                    "    _parsed = True\n    parser.add_argument('--offline-option')\n"
                    "    parser.add_argument('--offline-target', dest='repo_root', type=Path)\n"
                    "_original_pre_execute = pre_execute\n"
                    "def pre_execute(args, root):\n"
                    "    assert _parsed, 'parser module state lost'\n"
                    "    return _original_pre_execute(args, root)\n")
                if mode == "refusal":
                    stream.write("def register_execute_options(parser):\n"
                                 "    raise ValueError('offline parser')\n")
            if mode == "redirect":
                target = home / "target/config"
                target.mkdir(parents=True)
                (target / "mir-executor.local.json").write_text('{"native_policy":{"version":1}}')
                setup[2].append("--offline-target=" + str(target.parent))
            setup[2].extend({"state": ["--offline-option=value"], "help": ["--help"],
                             "unknown": ["--offline-unknown"],
                             "timeout": ["--timeout=not allowed with argument"]}.get(mode, []))
        actual, _ = SUPPORT["capture"](home, case, setup, selected, binary)
        assert (not (home / "target/imported").exists() if mode == "denied"
                else not (home / "parser-imports").exists() if mode == "timeout"
                else (home / "parser-imports").read_text() == "import\n")
        observations.append(actual)
    assert SUPPORT["first_difference"](*observations) is None


@pytest.mark.parametrize(("expression", "code", "stderr"), [
    ("", 0, ""),
    ("None", 0, ""),
    ("0", 0, ""),
    ("1", 1, ""),
    ("7", 7, ""),
    ("-7", 249, ""),
    ("2**32 + 7", 7, ""),
    ("2**100", 255, ""),
    ("-(2**100)", 255, ""),
    ("False", 0, ""),
    ("True", 1, ""),
    ("''", 1, "\n"),
    ("'offline parser stop'", 1, "offline parser stop\n"),
    ("('offline', 42)", 1, "('offline', 42)\n"),
    ("{'offline': 42}", 1, "{'offline': 42}\n"),
    ("2.5", 1, "2.5\n"),
])
@pytest.mark.parametrize("route", ["binary", "module"])
def test_dispatch_parser_system_exit(binary, oracle, tmp_path, expression, code, stderr, route):  # noqa: F811
    reference, database = oracle
    case = {"name": "success"}
    observations = []
    for label, selected in (("reference", "reference"), ("native", route)):
        home = (tmp_path / label / "home").resolve()
        setup = SUPPORT["seed"](home, case, reference, database, binary)
        with (home / "tools/mir_executor/local.py").open("a") as stream:
            stream.write("\ndef register_execute_options(parser):\n"
                         f"    raise SystemExit({expression})\n")
        actual, _ = SUPPORT["capture"](home, case, setup, selected, binary)
        if selected == "reference":
            assert actual["exit"] == code
            assert actual["stdout_hex"] == ""
            assert bytes.fromhex(actual["stderr_hex"]).decode() == stderr
        observations.append(actual)
    assert SUPPORT["first_difference"](*observations) is None
