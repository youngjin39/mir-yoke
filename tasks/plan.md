# Plan

## Active task: common semantic contract distribution, phase B1 (2026-10-14)

Authority: the current owner request recorded in `tasks/intent.json`; this is the single active
cursor and design authority. The superseded cursor and intent remain in `tasks/change_log.md`.

Outcome: ship `mir-core:ontology`, a byte-identical owner contract, generic mapping and knowledge
references, and a Python 3.9 standard-library checker. Prepare 0.11.0 without release binding.

Design: keep the project-owned mapping as JSON. Concepts are keyed by common concept id;
vocabularies, relations, questions, error cases and entrypoints are lists. References are repository
relative strings. Deterministic checks cover structure, declared compatibility and local references;
semantic interpretation, execution evidence and authority remain separate verification layers.
Package scripts are inert non-executable files, invoked explicitly with Python. No runtime hook,
automatic service connection or consumer write is introduced.

- [x] Confirm package rules and read the complete owner contract.
- [x] Write checker regression tests, run them failing, then implement and pass them.
- [x] Add generic skill/references, workflow pointers and bounded validator guidance.
- [x] Register the skill, refresh version/catalog metadata and prepare 0.11.0.
- [x] Run full pytest, Ruff, Codex parity and system Python contract checks; report evidence.

Constraints: write only here. Preserve canonical owner contract bytes. Do not commit, tag, push,
bind locks, apply/attest/finalize capabilities, change user installs or write generated `.codex/**`.
Full pytest may retain the named pre-release capability-lock failure. Agent-source changes may
require Main-owned derivative regeneration; report that state without bypassing parity checks.

Source work and required check execution are complete. Main must regenerate the ontology-validator
Codex derivative; release capability-lock binding remains outside this task. See
`tasks/change_log.md` under "Ontology phase B1 verification (2026-10-14)" for commands, results,
package rules, isolation details and the exact changed-file inventory.
