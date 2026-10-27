# Plan

## Active task: release 0.13.36 (Codex 0.164 legacy MCP interoperability) (2026-10-27)

Intent authority: the owner's choice of option 1 for the Codex protocol defect (Discord
1564465079863484509), the release-chain approvals (Discord 1564297975755448493,
1564320227062186065) and the session instruction to use Claude writers (Discord
1564282799035523227), relayed by Mir Harness Main (parent-supplied). Design authority: this
cursor and the 2026-10-27 legacy-negotiation amendment to
[ADR-91](../docs/decisions/adr-91-stdio-mcp-package-admission.md). Baseline: 9b0548a on
`main` (v0.13.35).

Prior cursor preserved verbatim:
[cursor before release 0.13.36](change_log.md#cursor-before-release-01336-2026-10-27).

Evidence (Main, 2026-10-27, parent-supplied): a byte-exact stdio tap shows Codex CLI 0.164.0
sends a legacy `initialize` requesting `2025-06-18`, then `_meta.progressToken` on
`tools/list` and Codex `_meta` keys on `tools/call`. Main validated the fix below against real
Codex 0.164 in a scratch session.

Rule (`plugins/mir-mcp/mir_mcp.py`):
1. A legacy `initialize` requesting any string version negotiates `2025-11-25`; every other
   `initialize` check stays.
2. After legacy initialization, `_meta` without `io.modelcontextprotocol/protocolVersion` is
   ordinary request metadata. A `_meta` with that key keeps the modern path and checks;
   before initialization such a request is still refused.

Request matrix (initially open):
1. Fail-first tests: Codex's exact session, legacy metadata alone, an unsupported legacy
   version negotiating, versioned metadata after legacy initialization, unversioned metadata
   before initialization.
2. Server change; existing malformed-metadata and nested-version tests stay green.
3. ADR-91 §4.7 amendment.
4. Version surfaces, this checkout's lifecycle acknowledgement, CHANGELOG, MIGRATION,
   README, this cursor; adopter payload regenerated last.
5. Focused tests, ruff, `git diff --check`.

Constraints: no commits, tags, pushes, sub-agents, capability-lock edits, real runtime
homes or host `mir capability` operations. Scratch stays under the owner-specified
external cache directory. Main runs the full suite at acceptance.

Observed (2026-10-27, Claude writer): items 1-5 checked; the payload regeneration
follows this note. Before the fix, 8 of the 12 selected protocol tests failed: Codex's
`2025-06-18` initialize and the `1900-01-01` legacy initialize returned `E_VERSION`, and
`tools/list` with `_meta.progressToken` after a `2025-11-25` initialize returned
`E_SCHEMA`. The 4 that passed are the unchanged-behaviour guards (modern unsupported version,
unversioned metadata before initialization). After the fix, focused `mir-mcp`, capability,
plugin-package and payload/template tests: 409 passed; the bumped hook-version test passes.
`test_repository_lock_is_portable_and_matches_managed_trees` fails because the version bump
changes tree digests that `.mir/capability-lock.json` binds; that is the separate bind
commit. Ruff and `git diff --check` pass. New tree digests: `mir-lifecycle-hooks`
555ac29c1b3b81a55972b2fa3c87cd71ebda03f3460e2a4998dc94d3d7cc8cf2, `mir-mcp`
02fc33c01eca29d0c7a0803955da2378477c9eacb3efa96ddc14eda3d9a64390. No release, binding,
full-suite or runtime readiness is claimed.

Release and host install (Main, 2026-10-27): source a0fff20, bind 1b4a963 (v0.13.36);
`verify_release_readiness.py --current-clean-tree` ready (3511 passed); CI validate and
release succeeded. This host updated 0.13.35 → 0.13.36 from the enrolled 0.13.35 lock with
`mir capability update --mcp --apply`; `config/capability-sources.json` now carries this
checkout's own consumer approval for `mir-mcp` (02fc33c0…) beside the hook approval, so
later release preparation renews both. Codex plugin hooks were re-trusted with
`mir codex-trust --apply` after the hook digest changed.

Attestation (fresh sessions, both `attested`, then `finalize --apply --after-restart`;
`mir capability status` ready at 1b4a963):
- Claude Code 2.1.310, session 517178e9: five `mir-mcp` tools `ok: true`, negotiated
  2026-07-28, 23 skills, four lifecycle hooks. `tools/list` 12,551 bytes, sha256 a9a072c4…;
  schema load 1,768 tokens (initial 26,044, after calls 30,317), deferred loading observed.
- Codex CLI 0.164.0, session 01a17b61: five tools `ok: true`, negotiated 2025-11-25, 23
  skills; SessionStart line, UserPromptSubmit packet, PreToolUse denial and Stop
  `hook_prompt` under 0.13.36. Same `tools/list` sha256 and bytes; schema load 1,559 tokens
  (initial 25,633, after calls 32,438), deferred loading observed (`ALL_TOOLS` discovery).

Open (not fixed here): `handoff_pins` returned `ok: false` with `dirty: E_TIMEOUT` in three
earlier fresh-session probes (Claude twice, Codex once): the first `git status` exceeded the
5-second limit and the later git calls were skipped. It did not reproduce in about 30 direct
calls, including runs after 7 minutes idle; the trigger is unknown. On failure the server's
`content: []` makes Claude show only "Unknown error".
