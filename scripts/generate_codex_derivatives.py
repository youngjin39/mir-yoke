#!/usr/bin/env python3
"""Generate the Claude-to-Codex mirrors using only the Python standard library.

Derived from the Mir harness reference implementation (Apache-2.0).
The historical shell generator's output format is intentionally preserved.
"""

import json
import os
import re
import runpy
import shutil
import sys
from pathlib import Path

GENERATOR = "scripts/generate_codex_derivatives.sh"


def read_raw(path):
    # awk/sed preserve CR bytes; frontmatter's Python reader normalizes them.
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.read()


def write_text(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(body)


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}
    result = {}
    current_key = None
    buffer = []
    for line in match.group(1).split("\n"):
        if current_key is not None:
            buffer.append(line)
            stripped = line.rstrip()
            if stripped.endswith('"') and not stripped.endswith('\\"'):
                result[current_key] = "\n".join(buffer).strip()[1:-1]
                current_key = None
            continue
        parsed = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if not parsed:
            continue
        key, value = parsed.groups()
        stripped = value.strip()
        if stripped.startswith('"') and not (stripped.endswith('"') and len(stripped) > 1):
            current_key, buffer = key, [value]
        else:
            result[key] = (
                stripped[1:-1]
                if (len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'))
                else stripped
            )
    for key, pattern in (
        ("name", r"[a-z][a-z0-9-]*"),
        ("disallowedTools", r"[A-Z][A-Za-z]+(?:,\s*[A-Z][A-Za-z]+)*"),
    ):
        value = result.get(key, "")
        if value and re.fullmatch(pattern, value) is None:
            print(f"ERROR: {path.as_posix()}: invalid {key} frontmatter value", file=sys.stderr)
            raise SystemExit(2)
    # Shell command substitution removes trailing LF bytes.
    return {key: value.rstrip("\n") for key, value in result.items()}


def agent_sources():
    profile = Path(".mir/repo-profile.toml")
    if profile.is_file() and 'overlay_archetype = "product_adopter"' in profile.read_text(
        encoding="utf-8"
    ).splitlines():
        try:
            agents = json.loads(
                Path("config/repo-agent-management.json").read_text(encoding="utf-8")
            )["catalog"]["agents"]
            if isinstance(agents, dict):
                return sorted(
                    (
                        Path(item["source_path"])
                        for item in agents.values()
                        if item.get("source_path")
                    ),
                    key=lambda path: path.as_posix().encode(),
                )
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return sorted(Path(".claude/agents").glob("*.md"), key=lambda path: path.as_posix().encode())


def nested_sources():
    sources = []
    for root in ("scripts", "src", "starter", "tests", "tools"):
        # os.walk, like find without -L, does not descend directory symlinks.
        for directory, _, files in os.walk(root):
            if "CLAUDE.md" in files:
                path = Path(directory) / "CLAUDE.md"
                if path.is_file() and not path.is_symlink():
                    sources.append(path)
    return sorted(sources, key=lambda path: path.as_posix().encode())


def lines(text):
    # awk emits a final LF even when the source's last record has none.
    records = text.split("\n")
    return records[:-1] if text.endswith("\n") else records if text else []


def body(path):
    records = lines(read_raw(path))
    if records and records[0] == "---":
        try:
            records = records[records.index("---", 1) + 1 :]
        except ValueError:
            records = []
    return "".join(line + "\n" for line in records)


def section(path, heading):
    selected = []
    in_fence = False
    in_section = False
    for line in lines(read_raw(path)):
        if line.startswith("```"):
            in_fence = not in_fence
        if line == heading:
            in_section = True
        if in_section:
            if not in_fence and (
                (line.startswith("## ") and line != heading) or line == "<Failure_Modes_To_Avoid>"
            ):
                break
            selected.append(line + "\n")
    return "".join(selected)


HEADINGS = {
    "main-orchestrator": [
        "## Startup Protocol",
        "## Ambiguity Gate",
        "## Task Classification",
        "## Task-Weight Model Routing (ADR-49, advisory)",
        "## Orchestration Presets",
        "## Simple Tasks (direct execution)",
        "## Complex Tasks (pipeline)",
        "## Codex Backend Dispatch Self-Check (ADR-18 §S2 Layer 1)",
        "## Active Agent Resolution (pre-dispatch)",
        "## Specialist Scope-Pattern Routing (catalog routing ADR)",
        "## Sub-agent dispatch policy",
        "## Post-Dispatch Evidence",
        "## Post-completion",
        "## Feedback → Learning",
        "## Reporting",
        "## Language",
    ],
    "executor-agent": [
        "## Protocol",
        '## Codex CLI invocation (ADR-09 round 4 — lessons from Phase 9A phantom "stdin issue")',
        "## State Checkpoint (externalize, don't trust memory — ADR-60 R5)",
        "## Report Format",
        "## Language",
    ],
    "quality-agent": [
        "## Adversarial Lens",
        "## Protocol",
        "## Report Format",
        "## Language",
    ],
}


def instructions(path, name):
    text = body(path)
    if name not in HEADINGS:
        return text
    preface = []
    for line in lines(text):
        if line.startswith("## "):
            break
        preface.append(line + "\n")
    result = "".join(preface)
    for heading in HEADINGS[name]:
        result += "\n" + section(path, heading)
    failure = []
    in_block = False
    for line in lines(text):
        if "<Failure_Modes_To_Avoid>" in line:
            in_block = True
        if in_block:
            failure.append(line + "\n")
        if "</Failure_Modes_To_Avoid>" in line:
            break
    block = "".join(failure).rstrip("\n")
    if block:
        result += "\n" + block + "\n"
    return result


def remove_tree(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def write_agent(output, source, metadata):
    name = metadata.get("name", "")
    if not name:
        return
    tools = metadata.get("disallowedTools", "")
    tokens = re.sub(r"\s", "", tools).split(",")
    text = f"# GENERATED FILE: edit {source.as_posix()} and rerun {GENERATOR}\n"
    text += f'name = "{name}"\ndescription = "{metadata.get("description", "")}"\n'
    if "Write" in tokens and "Edit" in tokens:
        text += 'sandbox_mode = "read-only"\n'
    text += (
        'developer_instructions = """\n'
        "Use `AGENTS.md` as the shared repository contract.\n"
        "Apply only the agent-specific behavior below; do not restate the root contract.\n"
    )
    if tools:
        text += f"Do not use these tools in this generated Codex mirror: {tools}.\n"
    text += "\n" + instructions(source, name).replace('"""', '\\"""').rstrip("\n") + '\n"""\n'
    write_text(output / ".codex/agents" / (name + ".toml"), text)


def write_config(output):
    text = (
        f"# GENERATED FILE: edit {GENERATOR} or .mcp.json and rerun the generator\n\n"
        'web_search = "cached"\npersonality = "pragmatic"\nproject_doc_max_bytes = 32768\n\n'
        "[features]\nhooks = true\nshell_snapshot = true\npersonality = true\n\n"
    )
    if Path(".mcp.json").is_file():
        servers = json.loads(Path(".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        for name, server in servers.items():
            args = ", ".join('"' + arg + '"' for arg in (server.get("args") or []))
            text += f'\n[mcp_servers."{name}"]\ncommand = "{server["command"]}"\nargs = [{args}]\n'
    write_text(output / ".codex/config.toml", text)


def write_hooks(output):
    renderer = Path("templates/common-harness/scripts/render-hook-configs.py")
    definition = Path("config/project-hooks.json")
    if not renderer.is_file() or not definition.is_file():
        return False
    # Reuse the stdlib renderer without uv, subprocesses or OS-dependent newlines.
    module = runpy.run_path(str(renderer))
    try:
        payload = module["_load_definition"](definition)
        outputs = {
            output / path: module["_serialized"](module["render_hooks"](payload, runtime))
            for runtime, path in module["OUTPUT_PATHS"].items()
        }
        for path, text in outputs.items():
            write_text(path, text)
    except (module["HookDefinitionError"], json.JSONDecodeError, OSError) as exc:
        print(f"hook config render failed: {exc}")
        raise SystemExit(1) from None
    print("hook configs rendered")
    return True


def write_manifest(output, nested, agents, hooks):
    mappings = []

    def append(source, targets, scope, notes):
        targets_json = "[" + ", ".join('"' + target + '"' for target in targets) + "]"
        mappings.append(
            "    {\n"
            f'      "source": "{source}",\n'
            f'      "targets": {targets_json},\n'
            f'      "change_scope": "{scope}",\n'
            '      "sync_policy": "regenerate",\n'
            '      "owner": "project-maintainer",\n'
            f'      "notes": "{notes}"\n'
            "    }"
        )

    append("CLAUDE.md", ["AGENTS.md"], "content", "Main Codex instructions")
    for source in nested:
        append(
            source.as_posix(),
            [source.with_name("AGENTS.md").as_posix()],
            "content",
            "Path-scoped Codex instructions",
        )
    for source, metadata in agents:
        if metadata.get("name"):
            append(
                source.as_posix(),
                [f".codex/agents/{metadata['name']}.toml"],
                "content",
                "Generated custom agent",
            )
    config_source = GENERATOR + (" + .mcp.json" if Path(".mcp.json").is_file() else "")
    append(
        config_source,
        [".codex/config.toml"],
        "config",
        "Generated project-owned Codex options and optional MCP settings",
    )
    if hooks:
        append(
            "config/project-hooks.json",
            [".claude/settings.json", ".codex/hooks.json"],
            "config",
            "Generated dual-runtime hook registrations",
        )
    append(
        GENERATOR, [".codex/README.md"], "content", "Generated Codex runtime and hook-trust guide"
    )
    if Path(".claude/hooks/lib").is_dir():
        append(
            ".claude/hooks/lib",
            [".codex/hooks/lib"],
            "directory",
            "Portable Codex hook library copy",
        )
    text = (
        '{\n  "version": 1,\n  "strategy": "one-way-claude-to-codex",\n'
        f'  "generated_by": "{GENERATOR}",\n'
        '  "notes": "Common skills are provided once through namespaced plugins; '
        'no repo-local skill derivatives.",\n  "mappings": [\n'
    )
    write_text(output / ".codex-sync/manifest.json", text + ",\n".join(mappings) + "\n  ]\n}\n")


def main():
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    output = Path(os.environ.get("CODEX_DERIVATION_OUTPUT_ROOT") or ".")
    if not output.is_absolute():
        output = root / output
    profile = os.environ.get("CODEX_DERIVATION_PROFILE") or "core"
    if not Path("CLAUDE.md").is_file():
        print("ERROR: CLAUDE.md not found in repository root.", file=sys.stderr)
        return 1
    # Validate the entire selected pack before replacing any existing output.
    agents = [(path, frontmatter(path)) for path in agent_sources()]
    nested = nested_sources()
    for path in (".codex/agents", ".codex/hooks", ".codex-sync"):
        (output / path).mkdir(parents=True, exist_ok=True)
    library = output / ".codex/hooks/lib"
    remove_tree(library)
    if Path(".claude/hooks/lib").is_dir():
        shutil.copytree(".claude/hooks/lib", library, symlinks=True)
    write_text(
        output / "AGENTS.md",
        f"<!-- GENERATED FILE: edit CLAUDE.md and rerun {GENERATOR} -->\n\n"
        + body(Path("CLAUDE.md")),
    )
    for source in nested:
        header = (
            "<!-- Mir Yoke publication derivative. After adoption, this repository owns this "
            "file and HARNESS.md remains canonical. -->"
            if source.as_posix() == "starter/CLAUDE.md"
            else f"<!-- GENERATED FILE: edit {source.as_posix()} and rerun {GENERATOR} -->"
        )
        write_text(
            output / source.with_name("AGENTS.md"),
            header + "\n\n" + body(source).replace("CLAUDE.md", "AGENTS.md"),
        )
    write_config(output)
    write_text(output / ".codex/README.md", CODEX_README)
    hooks = write_hooks(output)
    remove_tree(output / ".agents/skills")
    remove_tree(output / ".codex-sync/staging/.agents/skills")
    remove_tree(output / ".codex/agents")
    (output / ".codex/agents").mkdir(parents=True)
    for source, metadata in agents:
        write_agent(output, source, metadata)
    write_manifest(output, nested, agents, hooks)
    print("Generated Codex derivatives:")
    for suffix in (
        "AGENTS.md",
        "{scripts,src,tests,tools}/**/AGENTS.md",
        ".codex/config.toml",
        ".codex/README.md",
        "{.claude/settings.json,.codex/hooks.json} (generated from config/project-hooks.json)",
        ".codex/agents/*.toml",
        ".codex/hooks/lib (portable directory copy)",
        ".agents/skills (REMOVED — common skills are plugin-owned)",
        ".codex-sync/staging/.agents/skills (REMOVED)",
        ".codex-sync/manifest.json",
    ):
        print(f"  {output}/{suffix}")
    print(f"  profile={profile}")
    return 0


CODEX_README = (
    '<!-- GENERATED FILE: edit config/project-hooks.json or '
    'scripts/generate_codex_derivatives.sh and regenerate. -->\n'
    '\n'
    '# Codex runtime\n'
    '\n'
    '`.codex/hooks.json` is generated from `config/project-hooks.json`. The same '
    'definition renders\n'
    'Claude and Codex registrations, while runtime-specific events and timeout '
    'limits remain explicit.\n'
    '\n'
    '## Trust boundary\n'
    '\n'
    'Project-local Codex configuration loads only after the project is trusted. '
    'Non-managed hooks also\n'
    'require review of their current hash before they run. Use `/hooks` to inspect '
    'sources and trust or\n'
    'disable each hook. Until both trust steps are complete, hook-based safety and '
    'continuity behavior is\n'
    'inactive; repository instructions and explicit verification remain authoritative.\n'
    '\n'
    '## Permission boundary\n'
    '\n'
    'The generated root configuration does not select `approval_policy`.\n'
    'It does not select `sandbox_mode`, `sandbox_workspace_write`, '
    '`default_permissions`, or agent routing defaults.\n'
    'Operator-owned user or managed configuration remains authoritative for '
    'approval, permissions,\n'
    'default sub-agent models and effort, concurrency, and native collaboration enablement.\n'
    'Write-capable generated agents inherit that selection; mechanically read-only '
    'reviewers retain\n'
    '`sandbox_mode = "read-only"`.\n'
    '\n'
    '## Maintained events\n'
    '\n'
    '`PreToolUse`, `PermissionRequest`, `PostToolUse`, `SessionStart`, `PreCompact`,\n'
    '`PostCompact`, `Stop`, `SessionEnd`, and `UserPromptSubmit` are generated for Codex.\n'
    "Maintainer `SessionEnd` uses Codex's three-second limit. `UserPromptSubmit` emits the same\n"
    'advisory search-candidate hint as Claude; it never runs retrieval or blocks a prompt.\n'
    "`StopFailure` remains Claude-only because Codex has no such event. ADR-84's 2026-09-24\n"
    'amendment preserves the superseded exclusion policy. The compact-only Project Agent Kit\n'
    'template intentionally ships only its compact lifecycle.\n'
    '\n'
    '## Wire format\n'
    '\n'
    'Shared adapters parse `tool_name` and `tool_input`. Current Codex `apply_patch` sends the\n'
    'unified patch in `tool_input.command`; maintained adapters accept that field '
    'first and retain older\n'
    '`input`, `patch`, and `content` fallbacks for compatible runtimes.\n'
    '\n'
    'Regenerate with `scripts/generate_codex_derivatives.sh`. Do not edit generated '
    'Codex files directly.\n'
)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    raise SystemExit(main())
