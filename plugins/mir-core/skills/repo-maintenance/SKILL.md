---
name: repo-maintenance
description: "Periodic maintenance checkup of an agent-operated repository across twenty fixed items: consistency, operating base, documents, archiving, context, memory, harness constraints, skills and agents, instruction docs, rules and lessons, architecture, delegation and routing, continuity, work-context retrieval, token efficiency, test health, code/security/dependencies, integrity evidence, runtime behavior, and open decisions.\n\nTrigger: repository maintenance, periodic check, repo checkup, fleet maintenance, clean up and improve the repository"
---

# Repository Maintenance

## Use When
- The owner asks for a full maintenance pass over one repository or every managed repository.
- A previous pass needs re-verification against actual files and command output.

## Bounds
- Read, review and status requests stay read-only. A fix request authorizes in-scope edits and relevant checks only.
- Commit, push, tag, release, protected paths, secrets and memory-store writes follow the repository's
  own authority rules. Use only documented commands for memory and generated files.
- Move stale or duplicate material verbatim to the repository's log or archive and leave a pointer.
  Never delete a rule, decision or lesson.
- Relaxing a constraint means removing duplication, dead checks or gates for removed features. It never weakens a safety guard.
- A change that contradicts an accepted decision record or recorded owner intent is listed for the owner, not applied.
- Use a concept (fleet registry, bootstrap receipt, memory store, provider lock) only when the repository declares it.

## Checklist
Apply each item proportionately. Mark it done, no change needed (with evidence), or skipped (with a reason).
1. Consistency: profile and declared paths and commands match reality; docs match code; references resolve; generator parity holds.
2. Operating base: scripts, configs and hooks for removed features; dead entries.
3. Documents: plans, checklists and decision records state current facts. History is not rewritten.
4. Archiving: stale explanations, detailed history and duplicates move to the log or archive.
5. Context: always-loaded files stay minimal and procedures load on demand. Keep a single active cursor.
6. Memory: memory-store integrity and size, stale or missing-source records, and relation-graph health, checked through the documented commands.
7. Harness: excessive, duplicated or dead constraints are relaxed; harness consistency is improved.
8. Skills and agents: unused or duplicate capabilities, stale model or tool references, broken frontmatter.
9. Instruction docs: CLAUDE.md and AGENTS.md stay within size limits and carry the same rules for both runtimes.
10. Rules and lessons: each rule has one home, and lessons live in the declared location.
11. Architecture: the overview matches the actual layout and lists no removed components.
12. Delegation: model routing, delegation lanes and sub-agent limits follow the governing policy.
13. Continuity: one cursor, one resume pointer, one status projection and one evidence log.
14. Work context: one retrieval smoke query returns relevant anchors when retrieval is supported.
15. Token efficiency: session-start and hook output size, always-loaded file sizes, oversized routine reads.
16. Test health: the whole suite runs by default, stays hermetic, is not flaky under load, and new regression tests fail without their fix.
17. Code, security, dependencies: real defects, secret exposure, vulnerable or outdated dependencies, licenses.
18. Integrity evidence: locks, ledgers, receipts, audit chains and profile baselines are rebound through their documented commands after edits. Never fabricate provenance.
19. Runtime behavior: hooks fire, plugins and skills load, tool servers connect, and CLI versions match. Static documentation is not proof.
20. Open decisions: every pending owner decision is listed once, with both sides and the item it blocks.

## Workflow
1. Record the request in the repository's active cursor, then read its contract and profile.
2. Start from a clean or snapshotted worktree so changes can be attributed.
3. Run the checklist. When available, use `mir-core:governance`, `mir-core:verify`, `mir-code:testing` and
   `mir-code:code-review` for item procedures. For many repositories, handle each one under its own contract.
4. Verify with the repository's documented tests and gates. Re-run them yourself before accepting delegated work.
5. Report per item, then list changed files, before/after instruction-doc sizes, checks with pass/fail counts,
   integrity evidence to rebind, owner decisions and residual risks.
