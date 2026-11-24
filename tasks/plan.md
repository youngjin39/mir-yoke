# Plan

## Active task: SG-Y-PORT2 SessionStart upfront context port

Intent authority: the owner-supplied SG-Y-PORT2 brief and Stage G common rules.
Scope: port scripts/build_session_upfront_context.py into the existing native
project-hooks SessionStart handler; leave an uncommitted, reviewable diff.
Main owns generated .codex files, final adopter-payload regeneration and commits.

Design: reuse session_upfront.rs, already called by native session-start for
repository context, and remove its obsolete Python-file presence selector.
Switch the legacy shell to session-start with the common native availability
policy. The native handler already owns bootstrap gating and the UTF-8 output
budget; this avoids a second assembler and any Python fallback.
Recognize the native wrapper in both consumer adoption validators while retaining
legacy wiring and raw-Python rejection. Use the already-pinned TOML syntax tree
to preserve key identity, calendar validity, BOM and newline parity.
Keep W1 reference bytes pinned separately from live files. Freeze the Python
on synthetic projects before deletion; invalid UTF-8 crashes are diagnosed
reference defects and the native renderer supplies safe unavailable context.
Out-of-range TOML integers and JSON lone surrogates fail safely as undesigned
format inputs; their permissive Python outputs remain frozen as defect evidence.

Scenarios / acceptance matrix:
- Frozen direct renderer: absent/empty/malformed/types, Unicode, long inputs,
  directories, symlinks, intent conflict/completion and source gate order.
- Real shell: ready native, missing/disabled/unexecutable/symlinked native,
  failed warmup, launch statuses 64/126/127 and propagated ordinary failures.
- SessionStart: bootstrap states, read-only behavior and UTF-8 10KB cap.
- Retirement: no live callers, allowlist and inventory changes; W1 pin replay.
- Offline fmt, clippy and crate tests; affected Python tests and Ruff.
- Same synthetic ready project, ten hook start-to-exit runs before/after.

Current evidence: 38 frozen cases pass through the renderer and native handler;
the crate passes 928 tests with one existing ignored capture test. The selected
Python checks pass 592 tests plus the corrected W1 provenance check (1 test).
Fmt, Clippy, Ruff, shell syntax and ontology mapping checks pass. Original local
venv state is restored. Native availability mutation is rejected by the test.

Integration acceptance remains with Main: stage archived deletions for the raw
Git-index guard, regenerate adopter payload, and handle the pre-existing local
jobs file that fails the public-path scan. Rebuild/bind the native artifact before
delivering the retired Python source. No commit or release is authorized here.

Prior cursor: tasks/change_log.md#cursor-before-sg-y-port2-2026-11-25.
