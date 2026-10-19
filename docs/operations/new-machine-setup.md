# New-machine global setup

Use this check before an AI forms a project from Mir Yoke on another computer.
Global adoption is a separate user decision: the four-file Starter has no runtime
prerequisite, and the Project Agent Kit does not require a host-global Mir CLI
([ADR-81](../decisions/adr-81-minimal-starter-support-boundary.md),
[ADR-83](../decisions/adr-83-project-agent-kit-recipe-and-supported-surfaces.md)).
Cloning Yoke installs nothing. Never copy the maintainer's home configuration.

## 1. Select the OS and inspect prerequisites

| OS | Prerequisites for the optional global layer | Execution boundary |
| --- | --- | --- |
| macOS | Git, Python 3.12+, uv, Bash, Claude Code CLI and Codex CLI/desktop with plugin support | Primary automation lane. |
| Linux | The same tools, installed for the Linux user | Separate compatibility lane; not executed by the maintainer on that OS for this guide. |
| WSL | The same Linux tools inside WSL | Separate Linux lane; use its own homes, caches, trust and receipts, never native Windows state. Not executed by the maintainer on that OS for this guide. |
| Native Windows | Git and native Claude/Codex tools for selected workflows; Python/uv only for adapted Python tooling | AI-guided reference adaptation only; no ready receipt. PowerShell steps below were not executed by the maintainer on that OS. |

Python version: [pyproject.toml](../../pyproject.toml); automation dependencies:
[ADR-74](../decisions/adr-74-portable-bootstrap-capability-sources-and-memory.md#consequences).
The lifecycle plugin invokes `python3` through POSIX shell expansion. Native Windows
must adapt that launcher rather than assume it works. Node is not a Yoke runtime
requirement: install it only if the chosen CLI distribution or an approved MCP
server requires it. Obtain Git, Python/uv and the CLIs from their official installers;
complete their own authentication without copying credentials into Yoke.

| Surface | macOS / Linux / WSL default | Native Windows PowerShell default |
| --- | --- | --- |
| Claude global instructions | `~/.claude/CLAUDE.md` | `$HOME\.claude\CLAUDE.md` |
| Claude global settings | `~/.claude/settings.json` | `$HOME\.claude\settings.json` |
| Codex global instructions | `~/.codex/AGENTS.md` | `$HOME\.codex\AGENTS.md` |
| Codex global settings / MCP | `~/.codex/config.toml` | `$HOME\.codex\config.toml` |
| Claude user MCP | CLI-managed user configuration; not `settings.json` or project `.mcp.json` | Native CLI-managed user configuration |

Detect explicit `CLAUDE_CONFIG_DIR` / `CODEX_HOME` overrides before choosing paths.
Ask the user to supply the reviewed Yoke tag/commit and checkout path, runtime homes,
selected Profile/role pack, storage/cache root if customized, and any MCP binding.
Do not infer these from another machine.

## 2. Show changes, back up, and obtain confirmation

Before **any** host installation, registration or write, the AI must show the user:

| Planned change | Required review |
| --- | --- |
| Tool installation, marketplace and plugin registration | Exact source revision, selected packages, runtime scopes and destinations; inventory existing providers and same-name raw skills first. |
| Global instructions/settings/MCP | Existing effective values and proposed merged diff; preserve unrelated rules, policies and bindings. Never blindly overwrite. |
| Backup and recovery | A user-approved local backup location for each existing file and affected CLI-managed registration; keep secrets out of transcripts and repositories. Record absent files as absent. |
| Optional agents/commands or managed canary integration | Exact files and receipts written; distinguish home changes from project changes. |

Get the user's confirmation for that concrete plan before writing. Then make the
backups before applying the approved merge or invoking a mutating CLI. Stop on
collisions or conflicting policy. Restore only affected approved changes if a
check fails; retain incomplete evidence. Existing hosts must first follow the
[global plugin migration inventory](global-plugin-migration.md#1-establish-the-host-inventory).

## 3. Install user-scope capabilities in both CLIs

Choose **one** path. Commands in this section are for macOS/Linux/WSL, run from a
reviewed, immutable Yoke checkout. Linux and WSL commands were not executed by the
maintainer on those OSes. These examples document command syntax; this guide's
maintenance did not install anything into a real user home.

| Path | Use and ownership |
| --- | --- |
| Managed provider (fleet / existing enrolled projects) | Follow [migration steps 1–4](global-plugin-migration.md). A named, owner-approved canary must have valid target-owned capability configuration/Profile and generator inputs. `sync` can write its lock, agents, commands and Codex derivatives as well as user-scope plugin state. It is not a global-only dry run. |
| Explicit global-only install | Register a reviewed pinned local marketplace with the native CLIs as below. This does not enroll a consumer or create managed capability readiness receipts. Do not replace an existing managed provider with this path. |

Managed commands (replace `<canary-root>` with the explicitly authorized project):

```bash
uv run mir capability status --project-root '<canary-root>' --json
uv run mir capability sync --project-root '<canary-root>' --json
# Only after reviewing the proposal, backups and user confirmation:
uv run mir capability sync --project-root '<canary-root>' --apply --json
```

Global-only commands (replace `<pinned-yoke-checkout>`; retain that checkout at its
reviewed revision for the local marketplace, without automatic branch updates):

```bash
claude plugin marketplace add '<pinned-yoke-checkout>' --scope user
codex plugin marketplace add '<pinned-yoke-checkout>' --json
claude plugin install mir-core@mir-yoke --scope user
codex plugin add mir-core@mir-yoke --json
claude plugin install mir-lifecycle-hooks@mir-yoke --scope user
codex plugin add mir-lifecycle-hooks@mir-yoke --json
```

For a code Profile, also install `mir-code@mir-yoke` with the same two install
commands; for content, `mir-content@mir-yoke`; hybrid work may select both.
Use [capability-sources.json](../../config/capability-sources.json) for the exact
Profile selection. Do not copy common skills into `.claude/skills` or `.agents/skills`.
The reviewed lifecycle package delivers the common `SessionStart` hook; do not
paste its hook registration into settings. Repository-coupled hooks remain local
([ADR-90](../decisions/adr-90-role-plugins-and-common-hooks.md)).

Optional host-wide agents and Claude commands use the separate dry-run installer:

```bash
python3 scripts/install_user_runtime_agents.py \
  --claude-home "$HOME/.claude" --codex-home "$HOME/.codex"
```

Review its JSON and repeat with `--apply` only after confirmation and backup.
Use actual overridden homes when applicable. It installs the Profile-selected
union, refuses unmanaged divergence, and supplies generated Codex agents; Codex
command intent uses existing plugin skills. Its receipt is separate from plugin
activation ([ADR-89 §2.1](../decisions/adr-89-dual-runtime-capability-management.md#21-one-management-contract-runtime-native-delivery)).

## 4. Merge global rules and settings

| File / setting | Action |
| --- | --- |
| `global-rules/CLAUDE.global.md` | Review and merge applicable sections into Claude global instructions. |
| `global-rules/AGENTS.global.md` | Merge the equivalent rules into Codex global instructions. Keep both runtimes' intent consistent. |
| Claude `enabledPlugins`, `extraKnownMarketplaces`; Codex `[marketplaces]`, `[plugins]` | Let the user-scope installation own these records. Do not redeclare them in a settings template, project/local settings or generated global settings merge. Preserve installer-owned state. |
| Codex `[features] hooks = true` | Yoke's current generator enables hooks. If needed by the selected runtime, merge this one key into the existing table; also review/trust the exact plugin hook in a fresh session. Enablement alone is not execution evidence. |
| Claude `hooks`; Codex hook files | Do not duplicate the plugin hook. Keep target enforcement and stateful hooks in the target's canonical generation path. |
| MCP bindings | Optional owner-selected entries only; see §5. No server is required by Yoke. |
| Model, reasoning effort, approvals, permissions/sandbox, collaboration limits, language, UI and storage preferences | Operator policy or personal choice; leave to the user. Do not transplant Yoke maintainer defaults or weaken policy to pass setup. |

The global baselines are optional and project instructions remain self-sufficient
([global-rules](../../global-rules/README.md)). Global policy ownership follows
[ADR-85](../decisions/adr-85-global-policy-inheritance-and-agent-contracts.md).
There is no universal global settings file supplied by Yoke.

## 5. Optional global MCP and Memory Keeper

Yoke owns/registers **no MCP server**, and publishes no `mir-mcp` package. Global
MCP here means an operator-approved host binding, separate from Yoke packages.
Project-specific endpoints and policy remain target-owned. Do not activate the
stale `codex mcp-server` example; that transport was removed (ADR-85 amendment).

**Parity rule: both CLIs must reach the same MCP bindings.** For each binding,
record its name, transport, endpoint or executable/args, environment-variable
names, tool scope and authentication method. The user supplies all real values;
review each server independently. Keep credentials in the runtime's approved
local credential mechanism, never in this repository or command transcript.

Example for a user-approved Streamable HTTP service, after §2 approval:

```bash
claude mcp add --scope user --transport http shared-service '<shared-services-url>'
codex mcp add shared-service --url '<shared-services-url>'
```

Codex's equivalent merged `config.toml` entry is:

```toml
[mcp_servers.shared-service]
url = "<shared-services-url>"
```

Choose the CLI or the merged entry, not duplicate registrations. For an approved
stdio server, both `claude mcp add --scope user <name> -- <command> <args...>` and
`codex mcp add <name> -- <command> <args...>` accept the same executable/arguments;
Codex uses `command` and `args` under `[mcp_servers.<name>]`. Use the server's
verified local launch command, not an invented Yoke server. See the
[official Codex MCP reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Memory Keeper is an independent **opt-in**, same-host on-demand stdio supply.
Use the existing host environment and the [knowledge-supply schema and client](../../plugins/mir-core/skills/ontology/references/knowledge-supply.md).
The user supplies `<mk-supply-config>` outside the repository, with an approved
server command/args, working directory and timeout. The host-local schema template
below contains only placeholders; replace them with a separately verified server
launch configuration (the server is not shipped by Yoke):

```json
{"memory_keeper":{"command":["<mk-server-executable>","<mk-server-argument>"],"cwd":"<mk-server-working-directory>","timeout_sec":30}}
```

Select it using
`MIR_KNOWLEDGE_SUPPLY_CONFIG=<mk-supply-config>` or the documented
`~/.mir/knowledge-supply.json` default. Do not add that host file to Git. Remote
MK supply is unsupported; the HTTP example above is not an MK configuration.
The consumer client owns its on-demand child, so do not add a second resident MK
server merely to imitate plugin installation. Context packs are evidence, not
authority; missing supply does not block local work.

## 6. Restart and verify

| Check in fresh Claude **and** Codex sessions | Pass evidence |
| --- | --- |
| Global instructions | The runtime can identify the merged global rule and distinguish it from project instructions. |
| Plugins / skills | Exactly one enabled installed copy per selected package; Claude scope is `user`; actual session catalog exposes all selected namespaced skills. Files or plugin listing alone do not prove discovery. |
| Lifecycle hook | Review/trust the current definition and observe its fixed continuity line at `SessionStart` in each runtime. Record `mir-lifecycle-hooks:SessionStart` only after observation. |
| MCP, if selected | Compare effective bindings and connect in each runtime; inspect advertised tools and perform an approved read-only probe. A configured list alone does not prove a live connection. With no selected servers, record intentionally empty for both. |

Inventory commands (macOS/Linux/WSL; Linux/WSL not executed by the maintainer on
those OSes):

```bash
claude plugin list --json
codex plugin list --json
claude mcp list
codex mcp list --json
```

For the managed path only, use [migration step 4](global-plugin-migration.md#4-restart-and-prove-activation):
`uv run mir capability attest --project-root '<canary-root>' --runtime <runtime> --observed-skill <name> --observed-hook mir-lifecycle-hooks:SessionStart --apply --json`.
Run inside each restarted runtime (`claude-code`, `codex-cli-desktop`) with its
runtime-exported session ID; repeat `--observed-skill` for **every** actually
observed selected skill. Never manufacture a session ID or infer the catalog from
source files. Then run:

```bash
uv run mir capability finalize --project-root '<canary-root>' --apply --after-restart --json
uv run mir capability status --project-root '<canary-root>' --json
```

Current ADR-89 requires both runtime receipts; ADR-76's older Codex-only policy
is historical. Capability readiness does not verify optional MCP connections or
complete a project's bootstrap. The maintainer-only
`scripts/verify_plugin_cli_activation.py` installs isolated fixtures and verifies
inventory/digests across two consumer directories; it is not a home setup command
or a substitute for live-session discovery.

## 7. Native Windows: AI-guided steps

1. Inspect the actual native CLI versions and `$HOME\.claude`, `$HOME\.codex`
   (or explicit overrides), existing instructions, settings and MCP bindings.
2. Show a merged plan and backup locations; obtain confirmation before writes.
   Merge the two `global-rules/` baselines into the PowerShell paths in §1.
3. Assess native plugin support and adapt only the needed components using the
   [Windows reference procedure](windows-wsl-reference-adaptation.md). Replace
   POSIX launchers with reviewed target-owned Windows equivalents. Do not run the
   Bash commands above as a claim of native Windows installation readiness.
4. Merge approved MCP entries into native CLI-owned configuration and
   `$HOME\.codex\config.toml`, preserving the same binding semantics in both CLIs.
   Verify native discovery, hook execution and MCP connection locally.
5. Report adapted, omitted and untested surfaces. `setup.ps1` exits 1 without
   installation; native Windows has **no ready receipt**. If the user selects
   WSL instead, return to the separate Linux lane and its own homes.

## For an AI forming a project from this repository

- Detect the OS/lane and read the target contract before any mutation.
- Check global instructions, settings, selected plugin/skill/hook state and
  approved MCP parity in both CLIs. Record missing or intentionally omitted items.
- If the requested global layer is missing, propose this guide's exact steps,
  merged changes and backups to the user; obtain confirmation before writing.
- Keep optional global adoption separate from Starter/Kit completion. If the
  user declines, report that choice and continue the authorized project flow
  under its existing requirements. Never silently install into a user home.
