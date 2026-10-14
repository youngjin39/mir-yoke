# Plan

## Active task: Yoke ontology adoption, phase D (2026-10-15)

Authority: the current phase-D owner request recorded in `tasks/intent.json`; this is the single
active cursor and design authority. Superseded phase-B1 detail remains in `tasks/change_log.md`.
Baseline: `996e9fa21ef953950daa0a6f21d4617a42ea1680`; clean initial worktree.

Outcome: a project-owned mapping of Yoke's supplier model to contract 1.0.0, two selective
usage entrypoints, three evidenced domain comparisons and honest E01–E10 coverage.
Design: reference current supported-surface definitions first; label retained spec and maintainer
contracts explicitly. Keep local identities, vocabularies and state machines. Installation,
declaration, byte integrity, runtime observation and write authority remain separate.

- [x] Re-read authority, Profile, canonical definitions and existing checks; answer cold questions.
- [x] Add mapping and selective pointers; review endpoints and public relative refs.
- [x] Run mapping, context-path, instruction/parity and scoped invariant checks.
- [x] Record question comparisons, coverage, results and Main-owned regeneration pending.

Constraints: repository-only writes; no commits, push, version bumps, lock binding, release,
services, live DB or sensitive bodies. Do not write generated `.codex/**`. The documented generator
writes that scope, so regeneration is deferred to Main. Checker success is format evidence only.

Repository-local mapping and evidence work are complete. Harness Main regenerated the derivatives,
trimmed CLAUDE.md back to its 3600-byte budget (ontology pointer merged into the Sources line), refreshed
`config/adopter-payload.json`; codex sync OK; full suite 1833 passed, 1 expected failure (capability lock
not bound until release). Evidence and remaining semantic coverage are recorded in
`tasks/change_log.md` under "Ontology phase D adoption evidence (2026-10-15)". Memory Keeper binding is deferred.
