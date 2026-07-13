# Failure patterns

Recurring AI mistakes the harness was built to prevent. Add new entries when the same shape of error fires twice in this repo.

## Confident output without evidence
**Shape**: agent produces a plausible-looking summary that conflicts with the actual code or test result.
**Trigger**: question whose answer requires reading >3 files, agent skips the read.
**Mitigation**: gate "what is the current state" answers behind an actual `Read` / `Bash` call. The harness's session-start hook helps by pre-loading plan/lessons; everything else, the agent must fetch.

## Cascading "fix" beyond scope
**Shape**: bug fix turns into a refactor that touches twelve files.
**Trigger**: agent notices unrelated issues while working in a file.
**Mitigation**: surgical-change rule + ledger `targets` list. If a file is not in `targets`, it is not in scope. New issues become new ledger entries.

## Silent error swallow
**Shape**: `try/except: pass` or empty catch block.
**Trigger**: agent wants the test to pass quickly.
**Mitigation**: development-ai-rules.md "no silent error swallowing" + post-edit-check warns on bare `except`.

## TDD-after-the-fact
**Shape**: agent writes the implementation, then writes tests that pass against it without reading the spec.
**Trigger**: agent skipped the planning step.
**Mitigation**: composite TDD ledger written before code. The hook blocks implementation edits without an entry — but the *quality* of the entry is on the planner.

## Hook bypass
**Shape**: `git commit --no-verify`, or rewriting the hook to no-op.
**Trigger**: hook block is treated as a hassle, not a signal.
**Mitigation**: deny-list pattern blocks `--no-verify`. Hook script reviews are part of code review.

## Unrecorded override
**Shape**: agent flips Claude/Codex roles without writing the override into `tasks/plan.md`.
**Trigger**: one CLI is unavailable, agent silently switches.
**Mitigation**: role-policy section in CLAUDE.md / AGENTS.md mandates a recorded override. Reviewers must look for the line.

## Invalidated session resume
**Shape**: new session starts work on a stale plan because the snapshot was never updated.
**Trigger**: agent ended the previous session without running the closeout.
**Mitigation**: SessionEnd hook drops a stub snapshot. The closeout discipline is on the human.

## Format mismatch in ledger
**Shape**: ledger entry has 5 of the 12 categories, missing 7 silently.
**Trigger**: agent copies an existing entry and edits the parts it cares about.
**Mitigation**: pre-commit hook validates all 12 categories are present per entry. Schema in `.ai-harness/tdd-matrix.md`.

## Renderer overwrites manual fix
**Shape**: agent edits a generated file (`.codex/hooks.json`, `.claude/settings.json`) directly. Next compile run wipes it.
**Trigger**: the renderer is hidden behind a tool; agent does not realize the file is generated.
**Mitigation**: GENERATED notice at the top of every renderer-emitted file + entry in `.ai-harness/failure-patterns.md`.

## 2026-07-13 - Transport progress is not artifact progress; preservation must be deterministic

### Failure
Two backup dispatch waves emitted transport activity but produced no usable backup artifact. States such as `created` and `codex_completed` described delivery or model lifecycle, not a verified file, ref, index/worktree snapshot, or evidence package. Retrying the same model lane consumed time without improving recoverability.

### Why It Happened
The progress signal measured the transport and model process instead of the requested artifact. Preservation was also assigned to a generative lane even though its acceptance criteria were deterministic: exact Git objects, binary diffs, file metadata, hashes, and a replayed restore.

### Rule
Measure progress only through artifact fingerprints: expected file existence and hash, safety ref or bundle identity, index/worktree status, manifest counts and hashes, and completed verification evidence. A live transport with no changed artifact fingerprint is `STALL`; a completed transport without the required artifact is `EVIDENCE_MISSING`. Stop same-shape model retries. Route preservation to deterministic machinery that creates a Git bundle, staged and unstaged `--binary --full-index` patches, an untracked-file manifest/archive containing path, type, mode, size, and SHA-256, and disposable restore proof. `REDISPATCH` only after decomposing the failed task into a materially smaller or different lane. Use `ESCALATE_HUMAN` when no deterministic lane is available.

### Scope
Backup and restore gates, dirty-worktree reconciliation, delegated dispatch monitoring, artifact-producing automation, and session closeout.

### Failure Class
EVIDENCE_MISSING

### Recommended Action
REDISPATCH

## 2026-07-13 - Raw shell-text regexes confuse code with comments and data

### Failure
A regex guard both blocked harmless `codex exec` mentions and missed quoted executable invocations.

### Why It Happened
Raw text matching cannot simultaneously model shell comments, quote normalization, and command position.

### Rule
For executable-routing guards, use a non-executing lexer with command-position checks and paired positive-deny and negative-false-positive regressions. Propagate producer placeholders as argv taint through execution consumers, keep a reviewed allowlist for terminal data commands, and inspect bounded embedded-code statements using consumer flag semantics, including clustered flags and multiline code arguments. Keep shell separators as scan boundaries and fail closed when the bounded scanner cannot safely classify the syntax.

### Scope
Shell-command policy hooks and other guards that distinguish executable argv from comments or data.
