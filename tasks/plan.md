# Plan

## Active task: P2 ontology executable consumer paths (2026-10-15)

Authority: the current P2 owner request recorded in `tasks/intent.json`; this is the single
active cursor and design authority. The prior completed cursor is preserved in `tasks/change_log.md`.

Outcome: version-gated endpoint validation; bounded impact/check selection and lookup; an
on-demand stdlib MCP client with failure independence, fake-server lifecycle evidence and public docs.
Design: extend the existing checker without full-tree scans; select checks but never execute them;
load host-local MK configuration explicitly and bound/reap every child. Preserve 1.0.0 mappings.

- [x] Add regressions and record fail-first evidence for endpoints, impact, lookup and MK.
- [x] Implement consumer commands and update supported public guidance.
- [x] Refresh adopter payload; run focused/package/asset checks, lint and read-only parity.
- [x] Exercise Yoke impact/lookup and read-only Harness lookup; record output and remaining Main work.

Constraints: write only here; no commits, push, release, installation, real MK or databases;
never read credentials or edit `.codex/**` or the owner-distributed common contract. Main owns
the contract copy, generated derivatives and version bump. Use the external uv cache.

Bounded P2 implementation and requested checks are complete. Evidence and exact impact/lookup
receipts: `tasks/change_log.md`, "P2 ontology executable consumer paths (2026-10-15)".
The ontology tests have 124 passes and one pending owner-contract byte-parity failure;
package/common tests have 21 passes and asset tests have 6 passes. Codex parity and lint pass.
Main still owns the 1.1.0 contract copy/SOURCE digest, any required derivative regeneration,
version choice and consumer rollout. Read-only Harness lookup exposed four wildcard-array
endpoint errors; its writer must resolve them. No real MK or database was opened.
