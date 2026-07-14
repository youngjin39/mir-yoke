"""CLI parser regression tests."""

from __future__ import annotations

import pathlib

from tools.mir_executor.cli import _build_parser


def _base_execute_args(tmp_path: pathlib.Path) -> list[str]:
    return [
        "execute",
        "--change-id",
        "X",
        "--category",
        "unit",
        "--codex-args",
        "noop",
        "--repo-root",
        str(tmp_path),
    ]


def test_execute_parser_accepts_arbitrary_model_id(tmp_path: pathlib.Path) -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            *_base_execute_args(tmp_path),
            "--model",
            "gpt-x.y-codex-arbitrary",
        ]
    )

    assert args.model == "gpt-x.y-codex-arbitrary"


def test_execute_parser_accepts_arbitrary_reasoning_effort(
    tmp_path: pathlib.Path,
) -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            *_base_execute_args(tmp_path),
            "--reasoning-effort",
            "ultra-turbo",
        ]
    )

    assert args.reasoning_effort == "ultra-turbo"


def test_execute_parser_defaults_runtime_options_to_none(
    tmp_path: pathlib.Path,
) -> None:
    parser = _build_parser()

    args = parser.parse_args(_base_execute_args(tmp_path))

    assert args.model is None
    assert args.reasoning_effort is None


def test_dispatch_parser_defaults_to_one_attempt_and_short_finalize_lock(
    tmp_path: pathlib.Path,
) -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            "execute",
            "--dispatch",
            "--codex-args",
            "noop",
            "--repo-root",
            str(tmp_path),
        ]
    )

    assert args.change_id is None
    assert args.category is None
    assert args.max_codex_attempts == 1
    assert args.finalize_lock_timeout == 30


def test_dispatch_parser_accepts_explicit_attempt_and_finalize_lock_budgets(
    tmp_path: pathlib.Path,
) -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            "execute",
            "--dispatch",
            "--max-codex-attempts",
            "4",
            "--finalize-lock-timeout",
            "0",
            "--codex-args",
            "noop",
            "--repo-root",
            str(tmp_path),
        ]
    )

    assert args.max_codex_attempts == 4
    assert args.finalize_lock_timeout == 0
