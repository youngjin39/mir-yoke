# W1-Y10a own Stop audit goldens

Authority: the W1-Y10a task brief. This bounded task adds native own-audit
subcommands without changing registrations or callers. The task prohibits cursor,
handoff and change-log edits; capture tooling remains in task scratch.

Captured on 2026-11-06 from unmodified references at be0baca, using CPython 3.12.
The capture script lives only in task scratch. Its environment uses the fixed POSIX
tool allowlist from tests/w1_golden.py, a project-local interpreter symlink, and a
mktemp bridge confined to the scratch TMPDIR (fixed reference.py for traceback
provenance). It never runs the real executor. Root, repository and interpreter
paths use the existing W1 placeholders. Only UTC timestamp, PID and random suffix
fields are normalized, after shape checks.

49 new full-effect records plus 4 reused immutable W1 records cover both hooks:
empty and missing input; all JSON field types; quote/control escaping; nested object
insertion order and duplicate keys; ASCII and Unicode messages beyond 500 characters;
malformed JSON; four non-object payloads; unwritable sessions directories; preservation
of an existing log; and review-gate argv with a fake tools.mir_executor returning 9.
The test supplies the separate native MIR_STOP_REVIEW_ADAPTER dependency, checks its
entire argv against the frozen fake-module capture, and ignores its failure.

12 records have explicit retired CPython branches (10 new and 2 reused):

- Both malformed records in each corpus retain file effects and exit/streams;
  only JSONDecodeError text becomes the stable native string `invalid JSON`.
- New list, null, numeric and string root payloads for each hook retain directory
  creation and no log. Native emits no CPython AttributeError traceback.

No other parity exception is accepted. Replay checks status, stdout, stderr, changed
file bytes/modes, directory effects and deletions. The collision test injects only
entropy bytes into the same create-new primitive used in production, proving that
an exact existing candidate survives and a fresh name is retried. Production entropy
uses bundled SQLite's OS-seeded ChaCha20 PRNG through randomblob(3), without
changing the frozen Cargo manifest or adding dependencies.

Reference SHA-256 pins:

- `.claude/hooks/mir-stop.sh`: `64700ca20839d2d88ab5c638d1ca566ad412306c5e1b31d12fd149abcddb89d3`.
- `.claude/hooks/stop-failure-audit.sh`: `898e86453d806c1600e9c5d8059c4db34069da90102b2da4731da9e27b68c695`.
- `../w1/records.json`: `9eebc7cf31f128b49285ba6c24def85bd97f4d8cb02a2d909680d4760b39896d`.
