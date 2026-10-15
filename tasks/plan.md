# Plan

## Active task: covered-check resolution and MK consumer guide (2026-10-15)

Authority: current Harness central-run owner request (Discord decision "1, 2"), recorded in
`tasks/intent.json`. This is the single active cursor and design authority.

Outcome: covered checks resolve real repository-local files, lines and names; the public MK
consumer guide matches the implemented stdio tools and ContextPack fields.
Design: reuse safe ref resolution, tighten only covered checks, preserve the owner contract,
and follow MK code over the stale lifetime-reader statement in its consumer contract.

- [x] Prove new covered-ref regressions fail before implementation.
- [x] Implement checks and compact interface-based consumer guidance.
- [x] Refresh adopter payload; run focused tests, parity and all 16 read-only map checks.
- [x] Record results, changed files and Main-owned work remaining.

Constraints: repository-only writes; no commits, installs, services, database access, credentials,
or generated `.codex/**` writes. Other repositories are read-only evidence sources.

Completed: fail-first 8 failed / 60 passed; checker 68 passed; affected package, asset/payload
and reference checks 91 passed. Codex parity is current; no regeneration was needed.
All 16 read-only map checks ran: 15 clean, quietleaf E10 has 1 error and 1 warning.
The consumer correction is out of scope. Evidence: `tasks/change_log.md`,
"Covered-check resolution and MK guide (2026-10-15)".
