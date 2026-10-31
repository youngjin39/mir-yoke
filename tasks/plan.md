# Plan

## Active task: native Stop parity (2026-10-31)

Intent authority: current owner request; this cursor owns the bounded design.
Extend only the native crate, parity tests, benchmark/README and records. Preserve
plugins, real lock, generated Codex artifacts and all unrelated changes. No commit,
version change or caller switch.

Design: native Stop composes packet/authority/pin checks with transcript/tool
accounting; reuse digest and bounded runner. Remove event forwarding after native
coverage, retaining MIR_HANDOFF_PYTHON only for the repository pin runner. Exceptions
keep the reference warning contract. Differential fixtures are the behavior oracle.

Request matrix:
1. Entire Stop checker and exception/retry contract byte parity.
2. Every mechanical Stop fixture plus escaped Korean, repair and fake-runner pins.
3. Fail-first and checker-family mutation evidence.
4. Thirty-sample Stop no-packet/valid/defective median and p90.
5. Cargo and requested Python gates; README/records; payload regeneration LAST edit.

Status: native Stop implementation complete; all 15 checker-family mutants caught
and restored. Initial no-forwarding red: 4 failed / 2 passed; ordered-exception
warning red: 1 failed; control-only final-message red reproduced and four cases fixed. Cargo fmt/clippy/test/build pass (24 unit tests), Ruff passes.
Thirty-sample latency recorded in README and change_log. Payload generation is the
LAST edit, followed by the requested full read-only Python gate; final counts and
any open cells belong in the delivery report. No intentional behavior difference
or unported event remains. Local execution covers macOS only; Linux/Windows still
need CI. Previous-slice evidence below is historical.

## Previous slice: native supply and SessionStart (2026-10-31)

Intent authority: current owner request; this cursor owns the bounded design.
Preserve plugins, unrelated capability work, real lock and generated Codex files.
No commit, version or caller changes. Stop remains Python-forwarded.

Design: reuse native detection/owner restrictions, add supply context and bounded
runner lifecycle; add a separate runtime-continuity binary with Python text bytes.

Request matrix:
1. Native UserPromptSubmit, exception owner context and runner lifecycle.
2. SessionStart byte parity including Windows text line endings.
3. Differential fixtures, fail-first evidence and deliberate mutations.
4. Thirty-sample latency for ordinary/forbidden submit and SessionStart.
5. README scope and requested Cargo/Python gates; adopter payload LAST edit.

Status (2026-10-31): native implementation and 23 deliberate mutation checks
complete. Initial red: 18 failed / 1 existing pass; initial green: 19 passed.
DEL boundary red reproduced and fixed. Cargo four gates pass (10 unit tests);
Ruff passes. Thirty-sample latency measured and recorded in README/change_log.
Final inventory generation is the LAST edit, followed by the full requested
read-only Python gate. Final gate counts and any open cells belong in the delivery
report. Supported-platform execution remains local macOS only; Linux/Windows
and Windows cleanup require CI. No caller switch, commits or plugin changes.
