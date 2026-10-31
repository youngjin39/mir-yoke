# Rust coding rules

## Toolchain and safety

Pin an exact stable toolchain release in `rust-toolchain.toml`; use edition 2024
in `Cargo.toml`. Commit `Cargo.lock` for binaries. Default each crate to
`#![forbid(unsafe_code)]`. An exception requires a written reason and explicit
review of the smallest boundary; `forbid` cannot be locally overridden.

## Errors and types

Use `Result` end to end. Outside tests, do not use `unwrap`, `expect`, or `panic!`.
Enforce this with Clippy `unwrap_used`, `expect_used` and `panic` lints, for example
crate attributes `#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]`.
Keep test code separately scoped when configuring these lints.
Use typed error enums for libraries; for binaries, convert once at the top level
into diagnostics and exit codes. Preserve error kinds and source chains. Handling
an unrelated I/O error as “not found” is analogous to catching the wrong exception
class in another language: it hides the actual failure. Never swallow an error kind.

Match owned enums exhaustively. Do not use wildcard arms that hide new variants.
Model every valid input shape as a type. For owned serde schemas, use
`#[serde(deny_unknown_fields)]`. For external inputs, explicitly document tolerant
handling, including which unknown fields or variants are accepted and why.

## Text, paths and patterns

Use `Path` and `OsStr` for paths. Do not silently use lossy conversions; reject an
unrepresentable value or preserve its native representation. Encode textual output
as explicit UTF-8 bytes and write them through stdout/stderr byte writers (for
example `write_all(text.as_bytes())`), propagating errors. Console code pages must
not change the output encoding or break output.

The `regex` crate does not support look-around or backreferences. A port using
these needs `fancy-regex` or a deliberate rewrite. Preserve matching behavior with
parity fixtures for non-ASCII text, case-insensitive matching, and Unicode `\w` and
`\b` semantics. Handle matching errors and bound input/work for backtracking engines.

Keep dependencies minimal. Prefer std for small hooks and CLIs where startup time
matters; justify each extra crate against measured need.
