"""Dispatch checks Python result attributes before JSON erases their types."""

import pytest
from test_executor_dispatch_stage_d import SUPPORT, binary, oracle  # noqa: F401

SHAPES = [
    ("set()", "set"), ("()", "tuple"), ("[]", "list"), ("{}", "dict"),
    ("7", "int"), ("2.5", "float"), ("False", "bool"), ("None", None),
    ("'offline'", "str"), ("b'offline'", "bytes"), ("Custom()", "Custom"),
]


@pytest.mark.parametrize(("expression", "typename"), SHAPES)
@pytest.mark.parametrize("route", ["binary", "module"])
def test_dispatch_provider_result_type(binary, oracle, tmp_path, expression, typename, route):  # noqa: F811
    reference, database = oracle
    observations = []
    for label, selected in (("reference", "reference"), ("native", route)):
        home = (tmp_path / label / "home").resolve()
        case = {"name": "success"}
        setup = SUPPORT["seed"](home, case, reference, database, binary)
        with (home / "tools/mir_executor/local.py").open("a") as stream:
            stream.write("\nclass Custom:\n    pass\n"
                         f"def after_provider_call(*args):\n    return {expression}\n")
        actual, _ = SUPPORT["capture"](home, case, setup, selected, binary)
        if selected == "reference" and typename is not None:
            assert actual["exit"] == 1
            assert bytes.fromhex(actual["stderr_hex"]).decode() == (
                f"[mir_executor] dispatch failed: '{typename}' object has no attribute "
                "'exit_code'\n"
            )
        observations.append(actual)
    assert SUPPORT["first_difference"](*observations) is None


@pytest.mark.parametrize("route", ["binary", "module"])
def test_direct_opaque_provider_diagnostic_stays_compatible(binary, oracle, tmp_path, route):  # noqa: F811
    reference, database = oracle
    home = (tmp_path / "home").resolve()
    case = {"name": "success"}
    setup = SUPPORT["seed"](home, case, reference, database, binary)
    with (home / "tools/mir_executor/local.py").open("a") as stream:
        stream.write("\ndef after_provider_call(*args):\n    return set()\n")
    setup[2][:] = ["execute", "--change-id=fixture", "--category=unit",
                   "--codex-args=exec offline"]
    (home / "tasks/tdd.json").write_text(
        '{"changes":[{"id":"fixture","categories":{"unit":{"status":"planned"}}}]}')
    actual, _ = SUPPORT["capture"](home, case, setup, route, binary)
    assert actual["exit"] == 1
    assert actual["stdout_hex"] == ""
    # Binary retained its unsupported-object guard; the module forwards to Python.
    expected = ("TypeError: after_provider_call returned an unsupported object\n"
                if route == "binary" else
                "AttributeError: 'set' object has no attribute 'exit_code'\n")
    assert bytes.fromhex(actual["stderr_hex"]).decode() == expected
