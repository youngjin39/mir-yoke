# Native handoff packet proof of concept

`executor-query --home-root ROOT [executor query arguments]` implements
`status`, `result`, `list-jobs` and `cancel` for the invoking repository only. The home
root comes from the calling package. It creates absent registries, migrates supported legacy schemas,
and restricts storage permissions like Python. Cancel declines local Python extensions,
cross-target requests and unsupported inputs silently with exit 64.
The lightweight Python entrypoint checks the target manifest pin and retains
the Python CLI on any decline or unavailable artifact.

The same binary exposes the library's direct Codex execution path with
`executor-query --home-root ROOT execute --change-id ID --category unit --codex-args "exec 'task'"`.
It uses the app-server transport, updates the existing TDD ledger atomically, and
supports asynchronous execution and same-process background jobs. Background mode
flushes the job ID before starting the provider. Target hooks share one persistent
Python bridge. Dispatch, resume, Claude, dynamic parser extensions and unsupported
arguments decline with exit 64 before command hooks; failures after admission are
final. The Python entrypoint routing is unchanged.
Literal parser-extension declarations decline before importing local code. Extensions
computed during import fail finally and require an explicit Python invocation, so
import side effects cannot be repeated by an automatic fallback.

`tests/test_executor_execute_native_parity.py` compares offline Python oracles with
native process output, complete ledger text, job rows and hook order. It normalizes
generated paths, IDs, timestamps, measured durations and platform line endings.
Direct execution does not attach a dispatch brief, so it does not invoke
`validate_brief`. Agent-specific read-only execution remains on the Python path.
Ledger replacement uses `std::fs::rename` on every platform, including replacement
of an existing ledger on Windows. Unix account home lookup uses `getpwuid_r` in
one isolated unsafe module; Windows uses `USERPROFILE`. Neither operation starts
Python; target hooks still use the persistent Python bridge.

`tests/test_executor_query_native_parity.py` compares stdout, stderr and exit
status with isolated copies of the Python CLI. It runs on macOS, Ubuntu and the
dedicated Windows lane. Bundled SQLite requires the runner's C compiler; a Mac
host cannot perform the MSVC check without that compiler.

This maintainer-only crate implements PreToolUse, UserPromptSubmit and Stop natively.
The second binary, `runtime-continuity`, prints SessionStart context with Python
text-stream line endings. No event forwards to the Python reference. Internal
errors use the reference warning contract; PreToolUse errors remain silent.
`MIR_HANDOFF_PYTHON` selects only the repository pin runner (one path, not a shell command).
The lifecycle plugin selects an installed executable in `bin/` when available,
otherwise its Python reference. Capability updates install lock-pinned native
artifacts by default; `MIR_CAPABILITY_NATIVE_ARTIFACTS=0` disables placement.

Run Cargo from this directory:

```sh
export CARGO_HOME="$PWD/target/cargo-home" CARGO_TARGET_DIR="$PWD/target"
cargo fmt --check
cargo clippy --all-targets --offline --locked -- -D warnings
cargo test --offline --locked
cargo build --release --offline --locked
```

Invoke `target/release/handoff-packet` with hook JSON on stdin.
On Windows the executable has an `.exe` suffix. With `CARGO_TARGET_DIR`, use its
`release` directory instead; relative target paths resolve from this crate.
No reference argument is needed; the former reference argument is ignored.

The reference's stdin limit counts decoded characters. Oversized, malformed and
non-object input leaves its event undetermined and emits a warning. Preserve those
observed bytes with the native warning. The initial read is bounded to four
UTF-8 bytes per character. PreToolUse internal errors return silently; UserPromptSubmit exceptions emit
the reference warning, including owner context for detected author prompts. Stop
exceptions warn without owner context. Regex backtracking is bounded to 64 Mi steps.

`patterns.rs` transcribes the reachable reference patterns. `python_text.rs` freezes
Python 3.14 Unicode 16.0 word ranges and casefold exceptions. Word boundaries,
whitespace controls and dotted/dotless I need explicit compatibility. Look-around
uses fancy-regex; other patterns use regex. Other Python Unicode versions may
classify newly added codepoints differently. JS lone surrogates are replaced only
in internal command evidence, which is neither emitted nor executed; nested call
detection and denial remain identical.

## Cross-platform validation

The `native_handoff` CI job builds and executes byte parity on `macos-latest`,
`ubuntu-latest` and `windows-latest`. It pins Python 3.14 (Unicode 16.0), matching
the frozen tables, rather than the Python 3.12 used by other jobs. Runner rustup
uses `rust-toolchain.toml` (1.99.1, clippy and rustfmt). Clippy, tests and release
builds use `--locked`; `cargo fmt --check` has no lockfile/offline options.

The parity fixture inherits `CARGO_HOME` and `CARGO_TARGET_DIR`, and permits Cargo
to fetch by default. Set `MIR_HANDOFF_CARGO_OFFLINE=1` for the pre-fetched local
workflow above, keeping both exported Cargo variables when running pytest from
the repository root. The whole parity module skips if Cargo is absent.

Parity uses `HANDLER_PYTHON` from `tests/test_mechanical_handoff.py`: the current
`sys.executable`, or `MIR_HANDOFF_TEST_PYTHON` when explicitly set. It supplies that
same executable to the repository pin runner through `MIR_HANDOFF_PYTHON`. This avoids
Windows Store aliases and accidentally testing a different Python/Unicode version.
The shipped `hooks.json` uses POSIX `if`/`exec` selection, including `.exe`, and
requires `python3` on PATH for fallback. A native handoff may still need Python
for the repository pin runner. POSIX command tests cover installed binaries and
fallback with paths containing spaces and preserve deny exit codes. The owner
reports Claude on Windows uses Git Bash; that is parent-supplied context, not
local execution evidence. The Windows Codex plugin hook shell is not established
in the inspected repository. ADR-79 remains reference-adaptation-only there;
these tests do not establish live Windows shell delivery or activation.

Subprocesses run with `PYTHONUTF8=1` to decode non-ASCII input consistently across
Windows code pages. Native output is UTF-8 with CRLF on Windows and LF elsewhere,
matching Python text streams. Fixtures
are encoded explicitly and `.gitattributes` sets `* -text`, preventing checkout
conversion even with `core.autocrlf`. Assertions compare raw stdout/stderr bytes
and exit status without newline or encoding normalization. CI also runs
`tests/test_line_endings.py` to check the checkout contract.

From the repository root, measure 30 fresh processes per implementation and fixture:

```sh
uv run python native/handoff-packet/benchmark.py
```

Median and nearest-rank p90 include startup and pipe I/O. Implementations alternate;
OS caches are not flushed. Local execution evidence covers macOS arm64 only.
Linux and Windows execution requires the matrix job's results; distribution
signing and vulnerability audits remain unverified.

## Cold pattern compilation experiment (2026-10-31)

Before optimizing, a temporary release-build probe placed `Instant::now()` after
the pattern cache lookup and recorded elapsed time after translation and regex
construction. The probe was removed before parity and latency measurements.
Single cold-process samples (not warmed averages) identified these top costs:

| Pattern/check | Bash x (ms) | Author denial (ms) |
| --- | ---: | ---: |
| English write/prepare/... detector | 5.291 | 5.444 |
| Delegate detector | 3.100 | not taken |
| Recipient target label | 3.278 | not taken |
| Recipient status fields | 3.208 | not taken |
| Recipient authority fields | 4.018 | not taken |
| Owner prohibition | not taken | 7.024 |
| Unquoted exclusion | not taken | 2.679 |
| Restriction exception | not taken | 2.204 |
| All pattern translation + compilation | 28.703 | 24.521 |

The recipient-denial probe compiled 30 patterns totaling 51.507 ms. Bash x
compiled 15; author denial compiled 18. Compared with the cold-process totals
below, compilation accounts for most time; repeated matching is not the main
startup cost. These are separate runs, so their difference is not a phase timer.

Two optimizations preserve the original regex decisions:

- On ASCII haystacks, replace only Python's word class with `[a-zA-Z0-9_]`.
  Every input character has identical membership, including characters observed
  by word-boundary look-around. Other translations stay intact. Cache keys include
  this mode so Unicode input always retains the pinned table. Unicode literal
  case folding stays in the regex engine.
- After removing fences, detector matches require agent, codex, claude or the Korean word for agent (U+C5D0 U+C774 U+C804 U+D2B8)
  under the detector's existing lowercase operation. After removing recipient
  markup, target matches require qualified target under Python IGNORECASE or the Korean word for target (U+B300 U+C0C1).
  The prefilter maps dotted/dotless I, long s and Kelvin sign to ASCII counterparts;
  it neither collapses whitespace nor accepts a candidate without the full regex.
  Filtering before stripping would be wrong: stripping can join literal fragments.

Twenty added differential boundary cases include special folds, Korean labels,
markup/fence joins, line splits, near words and combining marks. Mutation evidence:
requiring an unrelated literal at the recognition gate failed 12/20 cases;
treating handoff/target substrings as sufficient failed 11/20. Their union is all
20 fixtures. Both intentionally wrong filters were removed. A Rust unit test
also alternates ASCII/Unicode haystacks to check cache separation.

Thirty fresh processes per cell, median / nearest-rank p90 in milliseconds:

| Fixture | Python before | Python after | Rust before | Rust after |
| --- | ---: | ---: | ---: | ---: |
| Read | 35.915 / 36.965 | 38.798 / 39.852 | 2.794 / 2.915 | 3.152 / 3.349 |
| Bash x | 38.787 / 39.931 | 38.386 / 39.326 | 31.996 / 32.354 | 3.160 / 3.304 |
| Ordinary Bash | 38.972 / 39.687 | 39.545 / 40.730 | 32.107 / 32.661 | 3.127 / 3.306 |
| Handoff deny | 38.893 / 39.801 | 39.376 / 41.832 | 27.563 / 28.243 | 7.535 / 8.004 |

No build-time precompilation or new dependency was needed. Unicode slow paths
still compile the full pinned classes; the optimization does not claim every
possible prompt reaches the process-startup floor. The benchmark uses cached OS
files and includes pipe/process overhead; Read variation reflects that baseline.

## Native supply scope

UserPromptSubmit ordinary prompts perform detection only. Recipient packets get
receipt rules; author prompts get owner context and pins or the reference warning.
The read-only pin runner uses MIR_HANDOFF_PYTHON (default python3), repository cwd,
PYTHONDONTWRITEBYTECODE=1 and GIT_OPTIONAL_LOCKS=0. Five-second timeouts terminate
the POSIX process group, or use bounded Windows taskkill followed by kill fallback.
Pipe readers drain both streams concurrently. Output uses UTF-8 replacement decoding,
universal newlines, the one-Mi-character limit, dictionary JSON and exclusion checks.
No plugin or hook caller is switched.

Native supply measurement (2026-10-31), macOS arm64, Python 3.12, release Rust,
30 alternating fresh processes per implementation, startup and pipe I/O included.
OS caches were not flushed. Command: `uv run python native/handoff-packet/benchmark.py`
with CARGO_TARGET_DIR pointing at this crate target.

| Fixture | Python median / p90 (ms) | Rust median / p90 (ms) |
| --- | ---: | ---: |
| submit ordinary | 51.463 / 57.903 | 5.11 / 5.942 |
| submit forbidden | 39.406 / 41.277 | 8.125 / 8.508 |
| SessionStart | 16.782 / 17.546 | 2.784 / 3.029 |

## Native Stop scope

Stop reads the explicit bounded transcript tail and native final message, then
checks packet fields, owner authority, map namespaces, full pins, cited sources,
recipient accounting, this-turn tool evidence and source-output claims. Native
Claude/Codex feedback controls the two-block repair limit, including reused Codex
run IDs and paired transcript views. Command-ban warnings survive later checker
exceptions in their original stderr order. All remaining exceptions produce the
reference warning directly; there is no Python event forwarding or fallback.

The shared pin runner retains its five-second timeout; cited-source collection
uses the remaining 6.5-second budget with the reference half-second floor. SHA-256
reuses the native implementation. Protected citation patterns use a parse-only
TOML dependency and Python-compatible filename matching. JSON pin comparison keeps
object insertion order, observation time, Python indentation and ASCII escaping.
No runner is started for a no-packet author turn or command-forbidden turn.

The parity module reuses the mechanical Stop tests and parameters at their actual
subprocess boundary, comparing stdout/stderr bytes and status before returning the
original test API. It also covers escaped Korean, fake-runner pin match/mismatch,
repair counts for both transcript shapes and ordered exception warnings. The
simulated Python 3.9 interpreter banner is outside the native binary contract;
the corresponding no-tomllib baseline is compared without that injected banner.

Stop measurement (2026-10-31): macOS arm64, Python 3.12, release Rust;
30 alternating fresh processes per implementation, OS caches not flushed.
Command: `uv run python native/handoff-packet/benchmark.py`. Startup, pipe I/O
and the fake repository runner are included. Every measured pair also compares
stdout/stderr/status; the valid packet must be silent and the defective packet
must block. Literal guards avoid compiling action/Korean grant/source patterns
when necessary input literals are absent; all candidates still use the checker.

| Stop fixture | Python median / p90 (ms) | Rust median / p90 (ms) |
| --- | ---: | ---: |
| Stop no packet | 44.713 / 49.185 | 5.14 / 5.718 |
| Stop valid | 61.073 / 65.418 | 58.852 / 64.282 |
| Stop defective | 64.601 / 70.397 | 59.838 / 66.554 |

## B1 adoption evaluator

`bootstrap-gate <target>` evaluates only the ready adoption branch of
`.claude/hooks/_lib/bootstrap-gate.sh`. It emits `ready\n` with exit 0 or
`invalid\n` with exit 1 for supported shapes. Exit 64 is silent and requires
calling the existing shell function unchanged. Malformed JSON, duplicate JSON
keys, unusual jq types/escaping, unreadable files, provider exemptions,
non-adoption states and Windows defer. Unknown JSON fields are ignored.
Leaf evidence symlinks are rejected; ancestor symlinks follow the current shell
oracle. This experiment deliberately does not strengthen that existing policy.

A separate binary in this crate reuses the existing JSON dependency and SHA-256
implementation; no new dependency or independent release unit is needed.
`tests/test_bootstrap_native.py` compares the real shell function with the binary
and a test-only dispatcher, including binary absence. Build the release binary
before running it; `MIR_B1_REQUIRE_NATIVE=1` makes absence a test failure.
The production helper uses this evaluator only for adoption-ready state. The
release workflow includes it alongside the other two binaries for all five targets.

### Production caller and integrity boundary

The helper probes the regular, executable, non-symlink
`<target>/.mir/bin/bootstrap-gate`. The adoption receipt contains:

```json
"native_evaluator": {"path": ".mir/bin/bootstrap-gate", "sha256": "<64 lowercase hex characters>"}
```

Before execution, the helper checks that pin against the binary's raw SHA-256;
the pinned bytes fix the version, so no separate version probe runs. Only
`(ready LF, 0)` or `(invalid LF, 1)` on stdout is accepted; the evaluator's
stderr is discarded. A missing pin or file, symlink, non-regular or
non-executable file, hash mismatch, unexpected output, signal or exit 64 runs
the shell path.
`MIR_NATIVE_HOOKS=0` forces shell evaluation. Provider exemptions, jq availability,
greenfield state and enforcement remain in shell.

The pin detects stale or replaced bytes under the target-owned receipt trust
model. It is not a signature: rewriting both receipt and binary defeats it, and
hash-then-exec retains a concurrent replacement race.

### Delivery and release

`mir bootstrap-adoption --apply` selects `bootstrap-gate` from the provider's
capability lock for the host target. It reads the pinned source URL and verifies
SHA-256 and size, atomically replaces the target file using a same-directory
temporary file with mode 0755, then records the receipt pin. An unavailable or
unverified artifact leaves adoption on shell without a native pin. Packaged
installs without a provider lock also remain on shell. The release binder checks
the published source commit and tag before writing artifact pins; installation
does not require the lock source commit to equal the artifact tag revision.

Maintainers can explicitly use
`mir bootstrap-adoption --apply --native-evaluator /path/to/bootstrap-gate`.
This local source is still hashed into the receipt; its digest is local build
evidence, not a published artifact attestation. Native Windows installs no
bootstrap evaluator and writes no pin, including with this option. The Windows
release binary returns 64; bash remains the reference until a tested path contract
supports a native verdict.

See [the native release procedure](../../MIGRATION.md#native-lifecycle-hook-selection)
for authorized workflow dispatch, prerelease inventory validation and lock binding.
Publishing now requires 20 assets: three binaries for five targets plus five
checksum files. Do not reuse a digest after signing or packaging changes bytes.
The crate protocol version remains 0.1.0; a verdict protocol change must also
update the helper's verdict match and its byte pin. Public repository
release versions follow CONTRIBUTING.md and tests/test_release_metadata.py.

G2 still requires actual macOS, Ubuntu and Windows execution. G4 requires final
published bytes and their lock digests; local builds do not establish it. G5 also
requires rollback verification and separately authorized consumer attestation.
No workflow dispatch or consumer adoption is implied by source changes.
