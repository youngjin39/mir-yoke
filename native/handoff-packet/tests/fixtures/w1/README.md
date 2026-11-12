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

- Clean-checkout hygiene removes the ignored CPython cache from source/copy
  inventories; the Python source remains pinned and all expected envelopes remain
  unchanged. Crate build inputs follow committed CLI migration changes, including
  84b7b8a's selected-root alias correction. Full replay verifies these updated pins
  against the original observations.

- W1-Y6b(1) re-pins only the bootstrap binary entrypoint for the additive
  enforce/instructions protocol routes and capabilities. The shell sources,
  caller selection and all existing frozen observations remain unchanged.

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

## W1-Y9a SessionStart reference extension

`session-start.json` adds 36 isolated shell-reference observations without changing
any of the 322 original envelopes. Capture used the unchanged session hook,
bootstrap gate and launcher, and the actual upfront builder copied into synthetic
projects. Its `sources` pins those four reference files. Each record retains its
setup, argv, source-copy list, streams, status, and complete project delta. All
36 observations have an empty delta and deletion list, including protected-mode
cursor and handoff sentinels. The receipt-bound synthetic CLI dispatches actual
Python for `run-python`, rather than silently accepting that command.

The native integration suite `project_hooks_session_start.rs` reuses the original
missing-receipt envelope and compares 33 new envelopes: greenfield/adoption
bootstrap states, a provider,
builder absence, nine profile forms, eight intent forms, and five output-cap cases.
Profiles include wrong-shaped tables and scalars, ordered required gates,
non-string array items, all five preserve fields, missing/malformed TOML, empty
and false scalars, finite/nonfinite floats, dates, times, and local/offset
datetimes including fractional seconds.
Intent cases cover reversed-history selection, whitespace normalization,
completion suppression, wrong shapes, non-string/nonfinite goals, and Unicode ellipsis.
The replay normally exposes only a failing Git stub; the provider envelope uses
its captured synthetic origin responder. No Python interpreter or shell renderer is available to the native command.

The cap is applied to the body before shell command substitution removes trailing
newlines. `cap-ascii-10237` is one byte below the raw-body limit.
`cap-ascii-10238` has exactly 10,239 pre-strip bytes and remains intact;
the next two cases cross that boundary and truncate. `cap-unicode-boundary` cuts
inside a three-byte code point and verifies the reference's valid-UTF-8 suffix.
Every native replay compares stdout, stderr and status, then compares full
project snapshots including bytes, modes, directories, and symlinks.

Three new envelopes are explicitly retired interpreter failure evidence, rather
than supported native output expectations: a Python builder exception, invalid
UTF-8 in the profile (which the Python builder does not catch), and receipt-bound
`run-python` returning 127. All three shell paths warn and use the safety fallback;
the launcher failure additionally warns that the output cap is unavailable. Removing the interpreter also removes these
Python failure modes. Native tests explicitly verify all three cases now render
unavailable-profile context without executing the builder or emitting the Python
warning. The three original ready-state SessionStart envelopes
(`ready-fallback`, `ready-builder`, `ready-cap`) likewise remain frozen evidence,
but their synthetic CLI swallows `run-python` and produces only a newline. The
new captures supply the real rendering/cap contract; they do not overwrite those
original adapter artifacts. The original missing-receipt envelope is reused as
native parity evidence.

Run the native tests with `cargo test --offline --locked --manifest-path
native/handoff-packet/Cargo.toml --test project_hooks_session_start`, with
`TMPDIR` and `CARGO_TARGET_DIR` under the task's T7 scratch directory.

- W1-Y9a re-pins `native/handoff-packet/src/lib.rs` only for shared bootstrap
  exports and the additive SessionStart/upfront modules. Bootstrap implementation
  sources and all existing frozen expected bytes remain unchanged.
