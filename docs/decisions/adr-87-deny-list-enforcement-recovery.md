---
adr: 87
title: "Deny-list enforcement recovery"
type: template-adr
created: 2026-09-01
status: accepted
template_scope: mir-yoke
related_adrs: ["adr-22", "adr-83", "adr-86"]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-87 — Deny-List Enforcement Recovery

## 1. Context

`.ai-harness/deny-list.yaml` declares twelve rules, eight of them `severity: block`. None of them
could ever fire. The awk field reader in `.claude/hooks/pre-tool-use.sh` strips only double quotes,
while every pattern in the file is single-quoted, so each pattern reached `grep -E` with a literal
leading apostrophe and matched nothing.

Hardcoded guards in the same hook independently covered most of the dangerous shapes, which is why
the defect stayed invisible: `rm -rf /`, force push, `--no-verify`, `curl | bash`, and secret-file
writes were all still blocked. Measuring the difference showed three rules had no other coverage:

- `dd-of-device` (`block`) — `dd if=/dev/zero of=/dev/nvme0n1` ran unblocked.
- `protected-secrets-dir` (`block`) — a write under `secrets/` ran unblocked, because the hardcoded
  secret guard matches a `basename` and structurally cannot express a directory prefix.
- `chmod-777-recursive` (declared `warn` at the time) — silent.

Two further defects surfaced while measuring. The hardcoded force-push and `sudo` guards are
position-dependent, so `git push origin main --force` and `echo x;sudo rm -rf /var` were allowed
while their canonical spellings were blocked. And the F9 sealed-family guard carried unsubstituted
`<your-home>` placeholders with an unclosed group, so `grep` aborted with `Unmatched ( or \(` on
every `git push` and the guard failed open.

The root cause of all of this is that no test asserted a deny-list rule fires.
`tests/test_hook_executability.py` covers the hardcoded guards only.

## 2. Decision Drivers

- A rule that declares `severity: block` must block, or must not be declared.
- Enforcement must be verified by a test that fails when enforcement regresses.
- The template runs on Linux and macOS CI, so patterns must not depend on one `grep` build.
- Adopters inherit these files, so a fix must not narrow or widen protection unexpectedly.

## 3. Considered Alternatives — HARD

1. **Fix the quote handling only.** Rejected as insufficient: the patterns are also flag-order
   dependent, so `git push origin main --force` still slips after unquoting.
2. **Delete the deny-list and keep only hardcoded guards.** Rejected: the file is the documented
   extension point for adopters, and three shapes have no hardcoded equivalent.
3. **Move matching into Python.** Rejected for this change: it enlarges the hook's startup cost and
   dependency surface for no gain the shell path cannot deliver.
4. **Fix quoting, make patterns position-independent, use POSIX classes, and pin the behaviour with
   a test.** Selected.

## 4. Decision

Read single-quoted and double-quoted pattern values. Treat an unusable pattern as a configuration
error and fail closed for that invocation rather than silently allowing the command. Rewrite the
shipped patterns and the hardcoded guards so they do not depend on flag position, and express
whitespace and word boundaries with POSIX classes instead of `\s` and `\b`. Add a directory-prefix
check for `secrets/`, which a `basename` test cannot cover. Remove the F9 sealed-family guard: its
regex is broken, its paths are the maintainer's private layout and meaningless to adopters, and
ADR-22 in this repository is a reference stub that imposes no hook requirement. Correct the stale
claim in `docs/harness-engineering/applications/harness-review-criteria.md` that F9 hard-blocks
external push.

`tests/test_deny_list.py` asserts on the blocking reason emitted to stderr, not only on exit code 2.
An exit code alone cannot distinguish a deny-list block from a BootstrapGate block, and that
ambiguity is what allowed the regression to persist.

Rewriting the patterns also required changing three shipped rules beyond their regexes, because the
old severities described protection that the patterns never delivered:

| Rule | Was | Now | Why |
| --- | --- | --- | --- |
| `chmod-777-recursive` | `warn` | `block` | No hardcoded equivalent exists, so `warn` left the shape unprotected in practice. |
| `curl-pipe-shell` | `warn` | `block` | Guard 5 already hard-blocks the same shape; `warn` was inconsistent with it. |
| `git-push-force-main` | `block` | renamed `git-push-force`, `warn` | A single POSIX ERE cannot express "force flag AND protected branch" in either argument order. The blocking decision moves to guard 2 in the hook, which tests both conditions; the rule keeps a warning for force-pushing any branch. |

Screen path rules against the bare path, and give every edit-shaped tool a path screen. Two
corrections:

1. **The deny-list subject was `"$TOOL_NAME $FP"`,** so a `^` in a path pattern anchored on the tool
   name rather than the path. `protected-secrets-dir` is `(^|/)secrets/`, which blocked
   `./secrets/prod.yaml` and an absolute path but allowed a bare `secrets/prod.yaml` — the spelling an
   agent writes most often. The subject is now the bare path, and the path guards move into one
   `screen_path_target` function so a new edit-shaped tool cannot pick up a subset of them.
2. **Coverage differed by tool.** `NotebookEdit` carries its target in `notebook_path` and reached no
   path guard at all; it now goes through `screen_path_target`. `apply_patch` already had its own
   screen — `_mir_patch_path_safety_reason` covers outside-root, `.git` internals and secret
   basenames for every path in the patch header — but that screen never consulted the deny-list, so a
   patch adding `secrets/prod.yaml` was allowed. It now calls `apply_deny_list` per patch path.

## 5. Rejected Alternatives — HARD

- Keeping `\s` and `\b`: they are not POSIX ERE. They happen to work under the GNU and ugrep builds
  used today, but the patterns were inert everywhere until now, so no evidence exists that the macOS
  CI runner agrees. POSIX classes remove the question.
- Repairing F9 by substituting real paths: a public template must not carry the maintainer's
  directory layout, and no accepted decision in this repository requires the guard.
- Failing open on an unusable pattern: that is the current behaviour and it is what turned a broken
  regex into silent permission.

## 6. Positive Consequences

- The three previously uncovered shapes are blocked, for relative as well as absolute paths.
- Force-push and `sudo` guards no longer depend on argument order.
- `git push` stops emitting a `grep` error.
- `NotebookEdit` reaches the path guards for the first time, and `apply_patch` target paths are now
  screened against the deny-list as well as the safety reasons they already carried.
- A regression in deny-list handling now fails `tests/test_deny_list.py`, which asserts on the
  reported rule id. **Locally only.** This does not yet hold in CI, for two independent reasons:
  the test is not referenced by any job in `.github/workflows/validate.yml`, and GitHub Actions is
  disabled at the repository level, so `validate.yml` has never run since it was added
  (`gh api repos/<owner>/mir-yoke/actions/permissions` → `{"enabled": false}`; `gh run list -w
  validate.yml` → no runs). Re-enabling Actions is a repository-settings action for the maintainer
  and is the prerequisite for the wiring, not the other way round.

## 7. Negative Consequences — HARD

- Fail-closed means a malformed pattern committed to `deny-list.yaml` blocks the affected tool call
  until it is fixed. This is deliberate, and the new test validates every shipped pattern so the
  failure surfaces in CI rather than during a session.
- Tightening the branch match to word boundaries changes behaviour for branches such as
  `maintenance` and `my-release-notes`, which the previous unanchored `(main|master|release)` match
  blocked by accident. This is a correction, but adopters relying on the accident will see those
  pushes allowed.
- Adopters who copied the inert deny-list now get real enforcement. A `secrets/` directory that was
  previously writable becomes read-only to the agent.
- `chmod -R 777` and `curl … | bash` now block rather than warn. Both were declared `warn` while
  inert, so no adopter has observed them warn; the change is visible only as new blocking.
- The rule id `git-push-force-main` no longer exists. An adopter who referenced that id in their own
  tooling or documentation must move to `git-push-force`, and should note that the id is now `warn`
  while the blocking decision lives in hook guard 2.
- A leading `+` on a refspec forces an update with no flag, and guard 2 still tests only for
  `-f`/`--force*`, so `git push origin +main` remains allowed here. `mir-harness` covers this case,
  which leaves the control repository stricter than this template on that one shape until it is
  ported.

## 8. Out-of-Scope — HARD

- Rewriting the hook in Python.
- Adding or removing rules. The set of twelve rules is unchanged; the severity and id corrections in
  §4 are in scope precisely because the old values described protection the patterns never delivered.
- Re-enabling GitHub Actions and wiring `tests/test_deny_list.py` into `validate.yml`. Both are
  required for the CI claim in §6 and neither is a change to this repository's code.
- Covering the `+refspec` force-push spelling, recorded as a known gap in §7.
- The `mir-harness` control repository's own copy of these guards, which shares the position-dependent
  force-push and `sudo` weaknesses but has a working deny-list parser and no F9 guard. It shares both
  path-screening defects corrected here: the same `"$TOOL_NAME $FP"` deny-list subject, and a patch
  screen that never consults the deny-list.
- Distribution-name and console-script collisions between this repository and `mir-harness`.

## 9. Verification

- `uv run pytest -q tests/test_deny_list.py` — every shipped rule blocks or warns as declared, every
  pattern compiles, and the reason reaches stderr. Includes
  `test_path_deny_list_anchors_at_the_path`, which uses a probe rule rather than a shipped one so it
  fails for exactly one reason, and the relative-path, `apply_patch`, and `NotebookEdit` cases.
- Probe the shipped hook with cases derived from this document rather than from the test file. The
  repository's tests share their fixture's assumptions — the first version of
  `test_secrets_directory_writes_are_blocked` built `str(project / file_path)`, so relative paths
  were absent from the test space entirely and the hole survived a green suite.
- `uv run pytest -q tests/test_hook_executability.py` — existing hardcoded guards still hold.
- `uv run pytest -q` — full repository suite.
- `uv run python -m tools.template_assets --write-adopter-payload` — adopter payload digests match.
