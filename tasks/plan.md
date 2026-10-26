# Plan

## Active task: release 0.13.34 (`mir-mcp` Codex launcher fix) (2026-10-27)

Intent authority: the owner's release-chain and B4 approvals (Discord
1564297975755448493, 1564320227062186065) and session instruction to use Claude
writers (Discord 1564282799035523227), relayed by Mir Harness Main (parent-supplied).
Design authority: this cursor and the 2026-10-27 amendment to
[ADR-91](../docs/decisions/adr-91-stdio-mcp-package-admission.md). Baseline: f1f1fab
on `main` (tag v0.13.33, pushed, released).

Prior cursor preserved verbatim:
[cursor before release 0.13.34](change_log.md#cursor-before-release-01334-2026-10-27).

Defect (observed by Main on the host, 2026-10-27, parent-supplied log excerpt): after
installing 0.13.33, Codex passed `${PLUGIN_ROOT}/mir_mcp.py` literally, resolved it
against the session working directory, and the server never answered `initialize`.
Claude Code expands `${CLAUDE_PLUGIN_ROOT}` and called all five tools. A bundled Codex
plugin uses `"cwd": "."`, which Codex resolves to the installed plugin root.

Root cause: `plugins/mir-mcp/.mcp.codex.json` declared the script as
`${PLUGIN_ROOT}/mir_mcp.py`, and the closed validator
(`src/mir/core/capabilities/mcp.py` `validate_mcp_package`) required that form.

Design: the Codex declaration becomes
`{command:"python3",args:["-I","-B","-u","./mir_mcp.py"],cwd:".",env_vars:[]}`; `cwd`
is admitted only as `"."`. The server resolves bundled modules from its own resolved
file path, so loading is unchanged. The locked Codex launcher adds `cwd:"."`; Codex
attestation evidence must be
`{command:"python3",args:["-I","-B","-u","./mir_mcp.py"],cwd:"<installed-root>",env:{}}`.
Claude's declaration, locked launcher and evidence form are unchanged. The release
follows the 0.13.33 pattern: bump current surfaces without historical rewrites, renew
the `mir-lifecycle-hooks` acknowledgement (no `mir-mcp` provider acknowledgement), add
CHANGELOG, README and MIGRATION entries, and regenerate the adopter payload last.
`.mir/capability-lock.json` belongs to the separate bind commit.

Request matrix (initially open):
1. Fail-first test launching `.mcp.codex.json` as Codex does (verbatim args, `cwd:"."`
   resolved to an isolated package copy) with `initialize` and `tools/list`.
2. Codex declaration in cwd-relative form; `.mcp.claude.json` unchanged.
3. Closed validator, per-runtime attestation launcher, locked launchers, their tests and
   the operator table updated without loosening any check.
4. ADR-91 dated amendment.
5. Version surfaces, lifecycle acknowledgement, release notes, this cursor; adopter
   payload regenerated last.
6. Focused tests, ruff, `git diff --check`; no new bytecode under `plugins/mir-mcp`.

Constraints: no commits, tags, pushes, sub-agents, capability-lock edits, real
runtime homes or host `mir capability` operations. Scratch stays under the
owner-specified external cache directory. Main runs the full suite at acceptance.

Observed (2026-10-27, Claude writer): items 1-6 checked; the payload regeneration
follows this note. On the unfixed declaration,
`test_codex_declaration_launches_without_variable_expansion` failed under both host
interpreters with the host error (`can't open file '<session cwd>/${PLUGIN_ROOT}/mir_mcp.py'`).
After the fix it passes on system Python 3.9 and venv 3.12; `initialize`, `tools/list` and
an `ontology_validate` call that loads the bundled checker succeed from `cwd:"."` with
`-I`, and no bytecode is written. Focused `mir-mcp`, capability, plugin-package and
payload/template tests: `821 passed`. Ruff and `git diff --check` pass; no new `.pyc`
under `plugins/`. New tree digests: `mir-lifecycle-hooks`
2aace0403313189fce0c663783dfa5c6f314ce8efddc4599a6ffbd37e4f20a78, `mir-mcp`
935d6a872f84ddc42f24c8871366c0456d5179f0c5b337d76db6ddddcad8c4c8. No release, binding,
full-suite or runtime readiness is claimed.
