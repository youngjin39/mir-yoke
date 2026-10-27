# Plan

## Active task: release 0.13.37 (MCP caching hints, failure text and host-local approvals) (2026-10-27)

Intent authority: the owner's decisions on the Harness items 10 and 11 preparation (Discord
1564607534323732632) and on where consumer approvals live (Discord 1564633173516755045), with
the release-chain approvals (Discord 1564297975755448493, 1564320227062186065), relayed by Mir
Harness Main (parent-supplied). Design authority: this cursor and the two newest 2026-10-27
amendments to [ADR-91](../docs/decisions/adr-91-stdio-mcp-package-admission.md) ("Caching
hints, failure text and per-pin Git failures" and "Host-local consumer acknowledgements").
Baseline: 9ad4354 on `main` (v0.13.36).

Release note (Main): the `v0.13.37` tag (99afe63) failed its release workflow on a README path
that names the git-ignored approval file; the fix ships as 0.13.38 with the same behavior.

Prior cursor preserved verbatim:
[cursor before release 0.13.37](change_log.md#cursor-before-release-01337-2026-10-27).

Rule (`plugins/mir-mcp/mir_mcp.py`):
1. Modern `tools/list` and `server/discover` results carry `ttlMs: 3600000` and
   `cacheScope: "public"`; legacy results are unchanged.
2. An `isError` result carries exactly one TextContent: compact JSON with `code`, the result's
   `unknowns` when present, and `omitted` when unknowns were dropped to stay within 512 bytes.
   Successful results keep `content: []`.
3. A failed or timed-out Git query marks only its own pin unknown as
   `<label>: <code> after <seconds> s`; a Git child may use the call deadline minus a 1 s
   reserve; the call is `ok: false` only when Git never answered. This addresses the open
   `handoff_pins` `E_TIMEOUT` item of the prior cursor; its trigger remains unknown.

Rule (`src/mir/core/capabilities/`):
4. The only consumer approval source is the git-ignored
   `<project root>/config/capability-acknowledgements.local.json`; a missing file approves
   nothing, a malformed one or a symlink fails closed, and no sync, update or rollback writes it.
5. `active_package_digest_acknowledgements` in any `capability-sources.json` is validated but
   never approves; Yoke's committed config carries `{}`. A `mir` older than 0.13.37 cannot load
   this release's provider config.

Request matrix (initially open):
1. Fail-first tests and server change for rules 1-3.
2. Fail-first tests and manager/config change for rules 4-5; `.gitignore` entry.
3. ADR-91 amendments and the plugin migration guide.
4. Version surfaces 0.13.37, CHANGELOG, MIGRATION consumer steps, README, this cursor.
5. This checkout's own approvals moved into its local file; adopter payload regenerated last.
6. Focused tests, ruff, `git diff --check`; Main runs the full suite at acceptance.

Constraints: no commits, tags, pushes, capability-lock edits, real runtime homes or host
`mir capability` operations by writers. Scratch stays under the owner-specified external cache
directory.

Observed (2026-10-27, Claude writer, item 4 only): the three current-version assertions in
`tests/test_plugin_skill_packages.py` and `tests/test_capability_security.py` were bumped first
and failed only on `0.13.36` versus `0.13.37` (3 failed, 146 passed). Items 1-3, 5 and 6 belong
to other slices and are not claimed here; no release, binding, digest, full-suite or runtime
readiness is claimed.
