# Native handoff packet proof of concept

This maintainer-only crate implements PreToolUse and forwards other events to
`python3 <first argument>`, preserving stdin, environment, stdout/stderr and status.
No hook caller or plugin payload selects it.

Run Cargo from this directory:

```sh
export CARGO_HOME="$PWD/target/cargo-home" CARGO_TARGET_DIR="$PWD/target"
cargo fmt --check
cargo clippy --all-targets --offline --locked -- -D warnings
cargo test --offline --locked
cargo build --release --offline --locked
```

Invoke `target/release/handoff-packet <path-to-handoff_packet.py>`.
Without the argument, recognized PreToolUse errors remain silent; other events
emit the reference unavailable warning without owner-specific additionalContext.

The reference's stdin limit counts decoded characters. Oversized, malformed and
non-object input leaves its event undetermined and emits a warning. Preserve those
observed bytes by forwarding these inputs. The initial read is bounded to four
UTF-8 bytes per character; only forwarding drains remaining input. Native internal
errors return silently. Regex backtracking is bounded to 64 Mi steps.

`patterns.rs` transcribes the reachable reference patterns. `python_text.rs` freezes
Python 3.14 Unicode 16.0 word ranges and casefold exceptions. Word boundaries,
whitespace controls and dotted/dotless I need explicit compatibility. Look-around
uses fancy-regex; other patterns use regex. Other Python Unicode versions may
classify newly added codepoints differently. JS lone surrogates are replaced only
in internal command evidence, which is neither emitted nor executed; nested call
detection and denial remain identical.

From the repository root, measure 30 fresh processes per implementation and fixture:

```sh
uv run python native/handoff-packet/benchmark.py
```

Median and nearest-rank p90 include startup and pipe I/O. Implementations alternate;
OS caches are not flushed. Local execution evidence covers macOS arm64 only.
Linux, Windows, distribution signing and vulnerability audits are unverified.

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
