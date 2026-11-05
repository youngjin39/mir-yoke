# W1-Y1 frozen hook references

Authority: the owner's W1-Y1 freeze request. Architecture option (a) was supplied
by the parent as the accepted direction. Analysis report sections 3 and 6 supplied
the inventory, not additional write authority. No production changes accompany
this freeze.

`manifest.json` records revision, capture interval, platform, Python version,
source SHA-256 pins, native artifact digest, semantic contract/map pin and case
inventory. `records.json` contains 322 independent observations in 29 families:
148 own-hook records (22 files), 30 template records (five files), 42 partial
native bootstrap records and 102 Windows launcher records. Own bootstrap accounts
for 43 of the 148 records. Native observations come from the existing evaluator;
they never supply expectations for shell references. Unsupported native states
remain observed declines, not claims of complete native parity.

Each record carries argv, stdin bytes, explicit environment overrides, synthetic
setup bytes/modes/symlinks, repository source copies, stdout/stderr bytes, status,
project filesystem delta including modes, and deleted paths. Binary values use
base64. In setup and stream envelopes, `@TMP@` denotes the replay root; inside
project filesystem snapshots it denotes the project root. `@REPO@` and `@PYTHON@`
denote repository and interpreter. Streams retain their original byte encoding.

The replay helper compares copied references with immutable expectations. Capture
scripts remain in task scratch. Replay has no record/update mode. Future ports
should route the same envelopes to replacement implementations before retiring
source execution tests. Investigate digest drift rather than auto-refreezing.

Isolation uses a fresh project, home and temp directory, fixed POSIX tool
allowlist, synthetic Git and project Python launcher, no inherited PATH or Git
configuration, and offline execution. The temporary-file adapter relocates
hardcoded system-temp audit staging into task scratch. Receipt-bound CLI,
upfront builder, tool-contract validator and self-ingest adapters are synthetic
where declared. These cases freeze orchestration, not helper correctness.
Precommit commands are literal shell builtins and synthetic Git only.

Only invocation timestamps/durations and audit filename time/PID/random fields
are normalized after format/type checks. Audit content timestamps are checked
separately. Diagnostics, whitespace, statuses, modes, payload bytes and other
log fields remain exact. Snapshot collisions are rejected.

Windows launcher envelopes execute the Python entrypoint with synthetic children
on POSIX. They cover both argv forms, four event pairs, 2/37/64/126/127, warmup
stdin isolation/output suppression, admission failures, rollback, raw CRLF/NUL/
Unicode input and non-UTF-8 stderr. They do not establish real Windows shell or
installed-Claude behavior; existing platform-specific tests own those lanes.

Run `uv run --no-sync pytest -q -p no:cacheprovider tests/test_w1_hook_freeze.py`
with task-local TMPDIR/CARGO_TARGET_DIR and the prescribed UV_CACHE_DIR. The test
builds the existing bootstrap evaluator offline and locked, or accepts an explicit
W1_BOOTSTRAP_NATIVE path. Native replay never silently skips on POSIX. Windows
skips POSIX replay and retains the platform-specific suite.

## Source re-pins

- W1-Y3b re-pins the crate manifest and lock for `tempfile`, which supplies
  private temporary files and portable atomic replacement. The bootstrap target,
  shell sources and all frozen observations remain unchanged. The Rust checkpoint
  replay entrypoint initially used `checkpoint_replay.py` as a test adapter.
  W1-Y4 slice 1a replaces that adapter with `tests/support/replay.rs`; checkpoint
  and compact replay now compare full filesystem deltas, modes and deleted paths
  in Rust, retaining the same frozen observations and normalization contract.

- `native/handoff-packet/Cargo.toml`: re-pinned after W1-Y2 added only the
  `project-hooks` `[[bin]]` declaration. The pinned file is a build input for the
  bootstrap-native observations; the `bootstrap-gate` target and every record
  replay unchanged.

- W1-Y6a re-pins `native/handoff-packet/src/bootstrap_gate.rs` and the crate
  manifest: a separate `state --protocol 1` subcommand, a `--capabilities` probe
  and the additive serde_json `raw_value` feature. The legacy `ready`/`invalid`
  fast path is byte-identical and all 42 bootstrap-native envelopes replay
  unchanged.
