# Plan

## Active task: release 0.13.39 (cloud-synced roots and byte-stable checkouts) (2026-10-28)

Intent authority: the owner's answers on the native Windows lane (Discord 1564632417304838205:
refuse OneDrive-like synced storage with a warning; the same behaviour on every OS), the Python
floor decision (Discord 1564633173516755045) and the start of 0.13.39 (Discord
1564710844560969759), with the release-chain approvals (Discord 1564297975755448493,
1564320227062186065), relayed by Mir Harness Main (parent-supplied). Design authority: this
cursor and the 2026-10-28 amendment to
[ADR-91](../docs/decisions/adr-91-stdio-mcp-package-admission.md). Baseline: 8aff20d on `main`
(v0.13.38 installed and attested on the maintainer host).

Prior cursor preserved verbatim:
[cursor before release 0.13.39](change_log.md#cursor-before-release-01339-2026-10-28).

Release split (Main): 0.13.39 portable foundations (this cursor); 0.13.40 the `mir` manager and
lifecycle hooks native on Windows with a Windows CI job; 0.13.41 the `mir-mcp` Windows lane,
`windows` receipts and the Python 3.11 floor for everything launched as bare `python3` (after
this host's agent bridges launch a 3.11+ `python3`).

Rules:
1. A resolved root inside cloud-synced storage is refused: `mir-mcp` with `E_CLOUD_SYNC` and the
   warning in `data.unknowns`; the manager with the same warning after the real-directory check
   and before reading consumer state.
2. `.gitattributes` `* -text` keeps checkouts byte-identical to blobs on every OS.
3. Tree digests sort by relative path parts; derivative paths use `/`; `pwd` is optional in the
   ontology runner and the Memory Keeper client.

Request matrix: (1) fail-first tests and code for rules 1-3; (2) ADR-91 amendment, CHANGELOG,
MIGRATION, README, version surfaces; (3) Main full suite, fresh-clone readiness and a Windows
rerun of the in-scope test files; (4) release chain and host re-attestation.

Observed (Main, 2026-10-28): writers F2-F4 and Main slice F1 each failed first and pass; the only
failing check before binding is `test_repository_lock_is_portable_and_matches_managed_trees`
(the lock still holds 0.13.38 digests, rebound at release).

Live install (Main, 2026-10-28): v0.13.39 (2df3c21) published after fresh-clone readiness (3591
passed) and CI validate/release. This checkout's provider moved from 0.13.38 with the new hook
and mir-mcp digests in its local approval file. Attested `claude-code` (session 9ab249ba) and
`codex-cli-desktop` (session 01a17ee9), each with five `ok: true` mir-mcp calls, four hooks and
23 skills; `tools/list` is 13,481 bytes (was 12,551: the new code and the `unknowns` branch);
`finalize --after-restart` applied; `mir capability status` ready with both runtimes verified.
A live call with a `Library/CloudStorage` root returned `E_CLOUD_SYNC` with the warning text.
On the owner's Windows PC the in-scope test files went from 814 failed / 641 passed to 763 / 748
(the CRLF reviewed-handler class is gone); the rest is 0.13.40/0.13.41 work.
