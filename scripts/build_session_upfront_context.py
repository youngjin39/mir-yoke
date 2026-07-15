from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10 hook runtime
    import tomli as tomllib


def _project_dir(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1]).resolve()
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def _load_profile(project_dir: Path) -> dict[str, Any] | None:
    try:
        data = tomllib.loads(
            (project_dir / ".mir" / "repo-profile.toml").read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _intent_conflict_advisory(project_dir: Path) -> str | None:
    """Preserve ADR-61's one-line state-conflict signal without loading task history."""
    try:
        intent = json.loads(
            (project_dir / "tasks" / "intent.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(intent, dict):
        return None
    current = " ".join(str(intent.get("goal") or "").split())
    history = intent.get("history")
    if not current or not isinstance(history, list):
        return None
    prior = next((item for item in reversed(history) if isinstance(item, dict)), None)
    if prior is None or prior.get("completed") is True:
        return None
    if str(prior.get("status") or "").strip().lower() in {
        "complete",
        "completed",
        "done",
        "closed",
    }:
        return None
    prior_goal = " ".join(str(prior.get("goal") or "").split())
    if not prior_goal or prior_goal == current:
        return None

    def compact(goal: str) -> str:
        return goal if len(goal) <= 160 else f"{goal[:159]}…"

    return (
        f"intent_conflict_advisory: prior={compact(prior_goal)}; "
        f"current={compact(current)}; "
        "confirm supersede or merge"
    )


def _table(profile: dict[str, Any], key: str) -> dict[str, Any]:
    value = profile.get(key)
    return value if isinstance(value, dict) else {}


def _strings(table: dict[str, Any], key: str) -> list[str]:
    value = table.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _render_values(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _render_scalar(table: dict[str, Any], key: str) -> str:
    value = table.get(key)
    if value is None or isinstance(value, (dict, list)):
        return "unspecified"
    rendered = str(value).strip()
    return rendered or "unspecified"


def _render_preserve(profile: dict[str, Any]) -> str:
    preserve = _table(profile, "preserve")
    parts = [
        f"{key}={_render_values(values)}"
        for key in (
            "skills",
            "claude_sections",
            "agent_memory_paths",
            "commands",
            "extra_docs",
        )
        if (values := _strings(preserve, key))
    ]
    return "; ".join(parts) if parts else "none"


def build_upfront_context(project_dir: Path) -> str:
    """Render task-blind startup identity and mandatory safety boundaries only."""
    profile = _load_profile(project_dir)
    lines = ["=== REPOSITORY CONTEXT ==="]
    if profile is None:
        lines.extend(
            [
                "repository_profile: unavailable",
                "mandatory_safety: inspect repository-local instructions before mutation",
            ]
        )
    else:
        repo = _table(profile, "repo")
        paths = _table(profile, "paths")
        boundaries = _table(profile, "boundaries")
        gates = _table(profile, "gates")
        slug = str(repo.get("slug") or "unknown")
        name = str(repo.get("display_name") or slug)
        repository_type = str(repo.get("repository_type") or "unknown")
        required_gates = [
            str(key) for key, required in gates.items() if required is True
        ]
        lines.extend(
            [
                f"repository: {name} ({slug}, {repository_type})",
                f"protected_paths: {_render_values(_strings(paths, 'protected_paths'))}",
                f"generated_paths: {_render_values(_strings(paths, 'generated_paths'))}",
                f"preserve: {_render_preserve(profile)}",
                f"secret_paths: {_render_values(_strings(boundaries, 'secrets'))}",
                "live_runtime_boundaries: "
                f"{_render_values(_strings(boundaries, 'live_runtime'))}",
                "external_services: "
                f"{_render_values(_strings(boundaries, 'external_services'))}",
                f"data_sensitivity: {_render_scalar(boundaries, 'data_sensitivity')}",
                f"release_window: {_render_scalar(boundaries, 'release_window')}",
                f"required_gates: {_render_values(required_gates)}",
                "source: .mir/repo-profile.toml",
            ]
        )
    if advisory := _intent_conflict_advisory(project_dir):
        lines.append(advisory)
    lines.append("=== END REPOSITORY CONTEXT ===")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    sys.stdout.write(build_upfront_context(_project_dir(argv)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
