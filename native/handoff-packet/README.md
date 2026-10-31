# Native handoff packet proof of concept

This maintainer-only crate implements PreToolUse, UserPromptSubmit and Stop natively.
The second binary, `runtime-continuity`, prints SessionStart context with Python
text-stream line endings. No event forwards to the Python reference. Internal
errors use the reference warning contract; PreToolUse errors remain silent.
`MIR_HANDOFF_PYTHON` selects only the repository pin runner (one path, not a shell command).
No hook caller or plugin payload selects it.

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
The unchanged shipped `hooks.json` still requires `python3` on PATH on every OS,
including Windows. The native default matches that contract; tests select an
explicit interpreter, as the existing Windows hook tests do. These tests do not
prove that a Windows user's shell resolves the shipped `python3` command.

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
