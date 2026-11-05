"""Capture read-only owner hooks. Intent authority: the external Y2b-3 brief."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import runpy
import sys
import unicodedata

import pydantic

BASE = runpy.run_path(str(pathlib.Path(__file__).with_name("generate_executor_hub_profile.py")))
PROFILE = ('[paths]\ncode_paths = ["code.txt", "src/"]\n'
           'protected_paths = [".env*", "src/private/"]\n[execution]\n'
           'codex_allowed_modes = ["bounded_review", "edit"]\n'
           'codex_blocked_modes = ["blocked"]\n')


def capture(owner, scratch):
    paths = {
        "local": owner / "tools/mir_executor/local.py",
        "contracts": owner / "src/mir/core/contracts/dispatch_brief.py",
        "loader": owner / "src/mir/core/conductor/dispatch_brief.py",
        "authority": owner / "tools/mir_executor/brief_policy.py",
    }
    sources = {key: path.read_text() for key, path in paths.items()}
    authority = (
        sources["authority"]
        .replace("from __future__ import annotations", "")
        .replace("from mir.core.contracts.dispatch_brief import DispatchBrief", "")
    )
    oracle = (
        "from __future__ import annotations\nimport argparse, json, pathlib, shlex\n"
        "from tools.mir_executor.local_hooks import local_config\n"
        + sources["contracts"].replace("from __future__ import annotations", "")
        + "\n"
        + BASE["functions"](
            sources["loader"], {"load_dispatch_brief", "render_dispatch_brief"}
        ).replace("path: Path", "path: pathlib.Path")
        + "\n"
        + authority
        + "\n"
        + BASE["functions"](
            sources["local"],
            {
                "_load_authorized_brief",
                "validate_brief",
                "render_brief",
                "_verifier_ids",
                "pre_execute",
                "job_identity",
            },
        )
        + "\nimport sys, types\n"
        '_loader = types.ModuleType("mir.core.conductor.dispatch_brief")\n'
        "_loader.load_dispatch_brief = load_dispatch_brief\n"
        "_loader.render_dispatch_brief = render_dispatch_brief\n"
        "sys.modules[_loader.__name__] = _loader\n"
        '_authority = types.ModuleType("tools.mir_executor.brief_policy")\n'
        "_authority.authorize_dispatch_brief = authorize_dispatch_brief\n"
        "sys.modules[_authority.__name__] = _authority\n"
    )
    # dataclasses require an importable module during class creation.
    import types

    module = types.ModuleType("_captured_brief")
    sys.modules[module.__name__] = module
    exec(oracle, module.__dict__)
    namespace = module.__dict__
    namespace["DispatchBrief"].model_rebuild(_types_namespace=namespace)
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / ".mir").mkdir(exist_ok=True)
    (scratch / "config").mkdir(exist_ok=True)
    verifiers = {"offline": ["check"], "last": ["check"], "other": ["other"]}
    (scratch / "config/mir-executor.local.json").write_text(json.dumps({"verifiers": verifiers}))
    variants = [
        ("default", {}, PROFILE),
        ("unicode", {"expanded_goal": "café 漢字 😀\nexact "}, PROFILE),
        ("empty_caps", {"capabilities": []}, PROFILE),
        *[
            (f"invalid_caps_{i}", {"capabilities": c}, PROFILE)
            for i, c in enumerate([["Bad"], [""], [" edit"], ["é"], [1], None, "edit"])
        ],
        ("blank_goal", {"expanded_goal": " \t\n"}, PROFILE),
        ("missing_profile", {}, None),
        ("bad_toml", {}, "["),
        ("missing_sections", {}, ""),
        ("missing_lists", {}, "[paths]\n[execution]\n"),
        ("bad_list", {}, PROFILE.replace('["code.txt", "src/"]', "[]")),
        ("bad_strings", {}, PROFILE.replace('["code.txt", "src/"]', '[""]')),
        ("basename", {"owned_scope": ["src/.env.local"]}, PROFILE),
        ("overlap", {"owned_scope": ["src/**"]}, PROFILE),
        ("outside", {"owned_scope": ["other/file"]}, PROFILE),
        ("unsafe", {"owned_scope": ["src/../x"]}, PROFILE),
        ("no_prefix", {"owned_scope": ["*/file"]}, PROFILE),
        ("blocked_first", {"capabilities": ["unknown", "blocked"]}, PROFILE),
        ("unknown", {"capabilities": ["unknown"]}, PROFILE),
        ("unicode_scope", {"owned_scope": ["code.txt", "src/café-漢字-😀"]}, PROFILE),
        ("unregistered", {"verification_commands": ["unregistered"]}, PROFILE),
        ("argv_mapping", {"verification_commands": ["check", "'check'"]}, PROFILE),
        ("bad_shlex", {"verification_commands": ["'check"]}, PROFILE),
        ("scope_order", {"owned_scope": ["src/b", "src/a"]}, PROFILE),
        ("verifier_order", {"verification_commands": ["last", "offline"]}, PROFILE),
    ]
    cases = []
    controls = []
    for name, changes, profile in variants:
        payload = BASE["brief_payload"]()
        payload.update(changes)
        path = scratch / "brief.json"
        path.write_text(json.dumps(payload))
        profile_path = scratch / ".mir/repo-profile.toml"
        profile_path.unlink(missing_ok=True)
        if profile is not None:
            profile_path.write_text(profile)
        outcome = {}
        try:
            brief = namespace["validate_brief"](path, scratch)
            outcome = dict(
                value=brief.model_dump(mode="json"),
                rendered=namespace["render_brief"](brief, scratch),
            )
        except Exception as error:
            outcome = dict(kind=type(error).__name__, message=str(error))
        cases.append(
            dict(name=name, payload=payload, raw=json.dumps(payload), profile=profile, **outcome)
        )
        for state, supplied in [
            ("absent", {}),
            ("empty", dict(allow_paths=[], verify_cmds=[])),
            (
                "exact",
                dict(
                    allow_paths=payload["owned_scope"], verify_cmds=payload["verification_commands"]
                ),
            ),
            (
                "reversed",
                dict(
                    allow_paths=list(reversed(payload["owned_scope"])),
                    verify_cmds=list(reversed(payload["verification_commands"])),
                ),
            ),
            ("mapped", dict(allow_paths=["code.txt"], verify_cmds=["check"])),
            ("scope_mismatch", dict(allow_paths=["src/a"], verify_cmds=["check"])),
            ("verifier_mismatch", dict(verify_cmds=["other"])),
        ]:
            for dispatch in (False, True):
                argument = argparse.Namespace(
                    dispatch=dispatch, dispatch_brief=str(path), **supplied
                )
                error = {}
                try:
                    namespace["pre_execute"](argument, scratch)
                except Exception as caught:
                    error = dict(kind=type(caught).__name__, message=str(caught))
                def normalized(value):
                    return json.loads(json.dumps(value).replace(str(scratch), "<root>"))
                controls.append(
                    dict(
                        name=f"{name}-{state}-{dispatch}",
                        payload=payload,
                        raw=json.dumps(payload),
                        profile=profile,
                        args=normalized(
                            dict(dispatch=dispatch, dispatch_brief=str(path), **supplied)
                        ),
                        patch=normalized(vars(argument)),
                        identity=namespace["job_identity"](argument, scratch, "", None),
                        **error,
                    )
                )
    return dict(
        runtime=dict(
            python=sys.version.split()[0],
            pydantic=pydantic.__version__,
            unicode=unicodedata.unidata_version,
        ),
        verifiers=verifiers,
        config_raw=json.dumps({"verifiers": verifiers}),
        controls=controls,
        sha256={key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
        oracle_source=oracle,
        cases=cases,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for field in ("owner", "scratch", "output"):
        parser.add_argument("--" + field, required=True, type=pathlib.Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(capture(args.owner, args.scratch), indent=2) + "\n")
