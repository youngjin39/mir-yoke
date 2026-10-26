# Plan

## Active task: B3 slice-2 review fixes (2026-10-26)

Intent/design authority: the current owner request and parent-supplied
`b3-s2-review-result.md`, scoped by ADR-91 section 4.8 and ADR-88 section 2.2.
Preserve consumer-local MCP approval across updates, bind prior approval to the
rollback receipt, and validate successful call receipts against shared package
schemas. Hook updates must retain their existing behavior.

Scenarios / request matrix (6/6 checked):
1. Provider bytes plus provider approval cannot replace local MCP approval;
   exact local renewal admits the new bytes, and missing approval blocks.
2. Hook bytes plus provider approval still update as before.
3. Consumer-only approval survives failed activation; missing/stale rollback
   approval fails closed.
4. Required fields, closed keys, types and bounds apply to each tool's receipt;
   missing/false success or an error result cannot attain READY.
5. Adopter payload regeneration, requested boundary/template tests and Ruff.
6. One full suite, preserving only the expected release-bind lock failure.

Design: overlay only mcp-stdio approvals from pre-update local configuration;
bind effective MCP approval into the active receipt for rollback. Declare literal
input schemas in the existing package and read them as data for receipt checks.
No commits, branch changes, sub-agents, generated Codex writes, real-runtime
activation or release binding. Record fail-first and final evidence in
`tasks/change_log.md`. The prior cursor is preserved in
change_log.md#cursor-before-b3-slice-2-review-fixes-2026-10-26.

Observed: 78 MCP admission/regression tests passed. Requested boundary/template
run: 987 passed; expected release lock mismatch plus one new log sanitation
failure. The sanitation fix and regenerated payload passed all 31 affected
public/payload checks. Ruff, strict ontology impact and mapping passed. Claude writer
review kept all three fixes, added exact-int receipt checking, and ran one full
suite: 3452 passed, only the expected release-bind lock failed. Matrix 6/6; no
live-runtime or release readiness claim. Open: provider-only fallback approval
(see change_log.md, Claude writer review entry).

Main acceptance, slice 2 (2026-10-27, Harness Main):
- An independent review reproduced two P1s and one P2: a remote acknowledgement
  replaced the local one; a consumer-only acknowledgement was lost on rollback; MCP
  call receipts were not schema-checked. All three are fixed with fail-first tests.
- Also fixed: provider-only first sync accepting a provider acknowledgement, and
  receipts accepting integral floats.
- The `mcp-stdio` acknowledgement must come from a consumer-owned
  `config/capability-sources.json`. Hook behaviour is unchanged and pinned by tests.
- Main re-ran:
  - Ruff, three-copy equality and the Python 3.9 parse all pass.
  - Full suite: 3456 passed. The two payload failures came from Main reverting a
    hook-written handoff snapshot; the payload was regenerated and they pass (21).
  - The expected pre-release lock failure remains.
- Writers: Codex, then headless Claude per the owner's session instruction
  (Discord 1564282799035523227).
- Next: B4, the owner-approved local acknowledgement and dual-runtime attestation.
