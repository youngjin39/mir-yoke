---
title: Windows and WSL Reference Adaptation
keywords: [windows, wsl, reference, agent, plugin, hook, portability]
created: 2026-09-04
type: operations
status: reference-only
---

# Windows and WSL Reference Adaptation

This guide is for an AI agent that opens a Windows-hosted project and uses Mir Yoke as versioned
Git reference material. It is not a native Windows installer, a parity claim, or permission to copy
the maintainer checkout into the target.

## Platform lanes

| Lane | Contract | Evidence boundary |
| --- | --- | --- |
| macOS | Primary central-provider and release lane | Current Yoke checks and runtime receipts may establish readiness. |
| Linux | Separate Bash compatibility lane | Its result describes Linux only and does not gate macOS. |
| WSL | Separate Linux/Bash compatibility lane | Use WSL-owned homes, caches, receipts, and storage; do not share native Windows state. |
| Native Windows | AI-guided reference adaptation | The target owns every generated file and must prove its own behavior. Yoke issues no ready receipt. |

A Git clone proves only that reference sources are available. It does not install a user-scoped
plugin, write an agent home, trust a hook, select a project Profile, or authorize target mutation.

## Source map for an adapting agent

| Needed capability | Read from Yoke | Target action |
| --- | --- | --- |
| Role selection | `config/capability-sources.json` | Select the smallest matching Profile pack; do not take the union automatically. |
| Common skills | `plugins/mir-core/skills/`, `plugins/mir-code/skills/`, `plugins/mir-content/skills/` | Prefer a supported host plugin install. If that is unavailable, adapt only the needed workflow under a target-unique name. |
| Lifecycle intent | `plugins/mir-lifecycle-hooks/` | Preserve the bounded continuity message, but replace the POSIX command with a reviewed target-owned Windows launcher. |
| Claude agents | `.claude/agents/*.md` | Select only roles applicable to the target and remove assumptions about unavailable scripts or tools. |
| Codex agents | `.codex/agents/*.toml` | Use the generated counterpart of each selected Claude agent; keep target-local model and permission policy authoritative. |
| Claude commands | `.claude/commands/*.md` | Treat as workflow examples. Codex uses the mapped `mir-core:design` or `mir-core:verify` skill intent instead of command aliases. |
| Hooks | `docs/decisions/adr-90-role-plugins-and-common-hooks.md` and the lifecycle package | Keep target-coupled enforcement local. Never infer protected paths, family identity, or trust from Yoke. |
| MCP | `.mcp.json.example` | Reference only. Yoke currently owns and registers no MCP server. |

## Known non-portable assumptions

Review these before taking any file into a native Windows project:

- The lifecycle plugin command uses `python3` and `${CLAUDE_PLUGIN_ROOT}` shell expansion.
- Capability agent integration invokes Bash and `scripts/generate_codex_derivatives.sh`.
- Some agents refer to `scripts/mir.sh`, `scripts/loop_driver.sh`, Unix pipelines, or Bash-based
  verification.
- macOS host examples may use `<macOS-user-home>` and `<external-volume>` locations; they are
  evidence from one machine, not portable configuration defaults.
- WSL paths and user homes belong to the Linux environment. A plugin installed inside WSL is not an
  installation for a native Windows Claude or Codex process.

Do not translate these mechanically. First determine whether the target needs the behavior. If it
does, implement the smallest Windows-native equivalent in the target repository and record that
choice in the target's own instructions or ADR.

## AI-agent adaptation procedure

1. Read the target's `CLAUDE.md`, `AGENTS.md`, Profile, protected paths, existing hooks, and runtime
   settings. Target policy wins.
2. Record the Yoke Git commit used as reference and the selected Profile role. Do not claim an
   installation merely because the source tree is present.
3. Inventory existing target skills, agents, command names, hooks, and MCP servers. Stop on a name
   or behavior collision instead of overwriting it.
4. Select only the required role plugin and agent material. Preserve repository-unique components.
5. Replace every POSIX path, launcher, environment-variable expression, and shell command with a
   target-owned Windows implementation. Do not edit Yoke's macOS provider to add conditional paths.
6. Keep the common read-only continuity reminder separate from repository-coupled enforcement.
   Review and trust the exact target hook before execution.
7. Generate Claude and Codex surfaces through a target-owned Windows script. If the target has no
   generator, keep the number of files minimal and document their source relationship explicitly.
8. Run the target's native lint, test, hook, plugin-discovery, and restart checks. Report the result
   as target evidence, never as Yoke Windows readiness.

## Prompt for a Windows project agent

```text
Target: <absolute Windows project path>
Reference: https://github.com/youngjin39/mir-yoke at commit <40-character SHA>

Use Mir Yoke as read-only reference material, not as an installer or fixed payload.
Read this project's instructions and platform definition first. Select only the necessary role
plugins, skills, agents, command intent, hook semantics, and structure. Preserve all project-owned
components and stop on collisions. Replace POSIX paths, Bash scripts, python3 launchers, and Unix
environment expansion with the smallest target-owned Windows equivalents. Do not run Yoke
bootstrap or claim Yoke readiness. Verify the resulting project with its native Windows checks and
record exactly what was adapted, omitted, and tested.
```

## WSL separation rule

If the operator chooses WSL, configure it as a separate Linux host. Clone or pin Yoke inside the
WSL-visible filesystem, use WSL-local Claude and Codex configuration homes, and assign a WSL-local
`MIR_CAPABILITY_HOME`. Keep its plugin cache, trust decisions, and receipts distinct from native
Windows. A future WSL package may automate that lane, but its absence or failure does not alter the
macOS central provider.
