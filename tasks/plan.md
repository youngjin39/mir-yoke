# Plan

## Active task: Rust skill and native handoff proof of concept (2026-10-31)

Intent authority: the owner's messages relayed by Mir Harness Main (parent-supplied):
add on-demand Rust guidance, port the PreToolUse path of the continuity handoff hook as a
proof of concept, cut its start-up cost, then commit and bind; push, tag and release need
separate approval. Design authority: this cursor. No version bump; `hooks.json` and the
Python reference stay byte-identical; callers are not switched.
Prior cursor (three slices, verbatim): [cursor before Rust PoC commit](change_log.md#cursor-before-rust-poc-commit-2026-10-31).

Request matrix: (1) `mir-code:rust` skill with coding, analysis, structure and porting
references, registered; (2) `native/handoff-packet` with byte parity on shared fixtures and
measured latency; (3) start-up optimization with boundary fixtures; (4) source and bind
commits.

Status (2026-10-31, Main): (1)-(3) done. Main re-ran the four Cargo gates (9 unit tests),
the parity module (121 passed; dropping the `codex` or `claude` prefilter literal fails 2 or
1 fixtures) and 30-process latency (median ms, Python -> Rust: Read 37.1 -> 3.1, ordinary
Bash 37.4 -> 3.2, handoff deny 38.2 -> 7.6, non-ASCII ordinary 36.1 -> 2.6, non-ASCII
handoff deny 36.3 -> 32.2). Linux, Windows and signing remain unverified. (4) in progress.
