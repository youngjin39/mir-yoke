# Plan

## Active task: B3 mir-mcp slice 1 (2026-10-26)

Intent authority: the current owner-relayed B3 slice-1 request (Discord
1564229077840302156, parent-supplied). Design authority: this cursor and
`docs/decisions/adr-91-stdio-mcp-package-admission.md` sections 4.2–4.7 and
section 9 bullets 2–6, at d05919f0e927c8c11f11c85417d76324d0026bca.
Implement canonical guarded checker interfaces, the standalone YAML relation
adapter, the exact eight-file package, and hermetic fail-first tests. Do not
change admission, marketplaces, capability configuration, runtime registration,
acknowledgements, generated Codex files, or existing tests. No commits or branch
switching. Stop if existing tests/validators reject the new package directory.
The previous cursor is preserved in
[the evidence log](change_log.md#cursor-before-b3-mir-mcp-slice-1-2026-10-26).

Design: all target reads pass a per-call bounded, root-confined guard; canonical
checker callbacks cover indirect references and Git. Fixed package module loads
and exact Git commands are the only dynamic loading/subprocess exceptions.
Python 3.9 and 3.12 share tool semantics, with explicit Profile unavailability
where tomllib is absent. YAML supports only documented flow triples.

Request matrix and behaviour scenarios (all initially open):
1. Package: exact files, declarations and rejection cases; no executable bits.
2. Canonical sources: guarded indirect reads/Git, unchanged CLI, byte equality,
   admitted-YAML differential traversal and independent package copy.
3. Security on both interpreters: safe success, direct/indirect path refusals,
   protected sentinels, races, all caps, stale cursors, static/runtime no writes,
   no environment input and no network.
4. Git: only guarded metadata, fixed argv/environment, bounded capture/time.
5. Protocol on both interpreters: modern direct/discovery, legacy handshake,
   invalid era/frame/feature rejection, ordered closed schemas, pure stdout.
6. Existing ontology/relations/plugin tests, Ruff and one final full suite.

Validation: use UV_CACHE_DIR on T7, PYTHONDONTWRITEBYTECODE=1, pytest
-p no:cacheprovider and the owner-specified external --basetemp. Record a failing
new-test run before implementation. Main owns generated-file regeneration.

Initial recorded status: implementation not started; matrix 0/6 checked.

Hardening continuation (2026-10-26): the current owner request authorizes fixing
the parent-reproduced Git gitlink/filter and malformed-protocol-type defects,
a protocol-wide field-type sweep, the public wording, adopter payload and any
minimal provider classification needed for slim. This supersedes the earlier
stop-on-existing-test-failure restriction for these named checks. This cursor
remains the intent/design authority; ADR-91's working-tree version is the spec.
Do not commit, switch branches, spawn children, or write generated Codex files.
Scenarios: gitlink-only nested filter must never create its sentinel; every
malformed request-field type must produce a bounded error and allow the next
valid stdio request, on both Python interpreters. Check all MCP tests, the five
reported integration failures, three-copy byte parity, Ruff, forbidden tokens,
and one final full suite. Only the pre-release managed-tree lock mismatch is
expected to remain. Fail-first and passing output goes in tasks/change_log.md.

Continuation (2026-10-26): the current parent decision retains Git and narrows
the child-read guarantee to ADR-91 section 4.5's fixed pre-spawn checks. Git's
internal metadata/worktree reads are not individually guarded; concurrent
same-user replacement during a child read is excluded. Other guarded reads
retain their replacement checks. ADR-91 section 4.5 and the section 9 Git bullet
have been amended accordingly. This continuation supersedes the initial Git
confinement interpretation, not the original implementation scope.

Current observed state: the eight-file package and canonical helpers are present;
Git is implemented. Existing targeted tests passed (423 tests), both interpreter
versions were observed (3.9.6 and 3.12.13), and the read-only Codex parity check
passed with the required UV cache. New-test integration and the final full suite
remain in progress. Detailed fail-first and final execution evidence belongs in
`tasks/change_log.md`. No commit or generated-file write has been performed.

Hardening observed state (2026-10-26): all 493 MCP cases and 21 affected
integration cases pass; the only targeted failure is the expected pre-release
mir-core lock digest mismatch, independently confirmed against every lock-test
assertion. Git gitlink and nested-version regressions have fail-first evidence
on both interpreters. The 48-field type sweep, exact argv, three-copy equality,
Ruff, public scan and regenerated-payload slim checks pass. Evidence is in
change_log.md#b3-slice-1-hardening-fixes-2026-10-26. The final full suite returned
3348 passed and one expected lock failure in 470.75s; no other failures or skips.
All 13 recorded hashes stayed unchanged during the run. Hardening matrix: 6/6
checked, including the expected and preserved pre-release lock mismatch. Release
binding and broader slice admission remain Main-owned.

Main acceptance (2026-10-26, Harness Main): this supersedes the "in progress" lines
above. An independent review reproduced two defects (gitlink nested filter;
non-string `protocolVersion` crash), both fixed with fail-first regressions. A
mutation review then killed 64 of 82 mutants; the 18 survivors were test gaps,
not server defects. 16 gained killing tests and four stayed covered by later
checks (#33, #40, #42, #43). Main re-ran in the host environment:
- MCP tests: 518 passed.
- Ruff: passed.
- Three-copy byte equality: confirmed.
- Adopter payload: regenerated after the test additions.
- Full suite: 3373 passed, plus the expected pre-release mir-core lock failure.

Slice 1 is committed on `feat/mir-mcp`, not pushed. Next is slice 2: schema 5,
validator and manager admission, then the release bind that clears the lock failure.
