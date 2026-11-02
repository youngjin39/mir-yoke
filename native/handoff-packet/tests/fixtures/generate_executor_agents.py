"""Capture agent definition routes from the common Python resolver."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import dispatch, policy  # noqa: E402

root = pathlib.Path(os.environ["E2B_SCRATCH"]) / "agents-oracle"
(root / ".claude/agents").mkdir(parents=True, exist_ok=True)
(root / ".codex/agents").mkdir(parents=True, exist_ok=True)
(root / "config").mkdir(exist_ok=True)
data = {
    "mode": "select",
    "routing": {"default": {"model": "gpt-fixture", "reasoning_effort": "medium"}},
}
resolved = policy._resolve_policy(data)
cases = []
for backend in ("codex", "claude", "invalid"):
    for readonly in (False, True):
        for sandbox in (None, "read-only", "workspace-write", "danger-full-access", "invalid"):
            name = "reviewer"
            source = f"---\nexecution_backend: {backend}\nmodel: opus\neffort: high\n"
            if readonly:
                source += 'disallowedTools: "[Write, Edit]"\n'
            source += "---\nDo the bounded work.\n"
            codex = (
                None
                if sandbox is None
                else (
                    f'sandbox_mode = "{sandbox}"\ndeveloper_instructions = "Native instructions."\n'
                )
            )
            (root / ".claude/agents/reviewer.md").write_text(source)
            codex_path = root / ".codex/agents/reviewer.toml"
            if codex is None:
                codex_path.unlink(missing_ok=True)
            else:
                codex_path.write_text(codex)
            warning = io.StringIO()
            with (
                patch.object(dispatch, "invoke_hook", return_value=None),
                patch.object(policy, "load_sub_agent_policy", return_value=resolved),
                contextlib.redirect_stderr(warning),
            ):
                try:
                    route = dispatch.resolve_agent_route(root, name)
                    expected = {"route": dataclasses.asdict(route), "warning": warning.getvalue()}
                except ValueError as exc:
                    expected = {"error": str(exc)}
            cases.append({"source": source, "codex": codex, "policy": data, "expected": expected})
pathlib.Path(__file__).with_name("executor_agents.json").write_text(
    json.dumps(cases, ensure_ascii=True, indent=2) + "\n"
)
print(f"captured {len(cases)} agent route cases")
