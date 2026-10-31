# Rust project structure and build configuration

Start with one crate unless independently reusable components or multiple binaries
justify a workspace. Give binaries explicit, stable names (`[[bin]]` when needed).
Keep `src/main.rs` thin over `src/lib.rs`: argument and process boundaries belong
in main, while logic stays unit-testable in the library. In a workspace, declare
members and shared dependency policy explicitly rather than copying configuration.

## Storage and toolchain

Honor host-local `CARGO_TARGET_DIR`, `CARGO_HOME` and `RUSTUP_HOME`. Never commit
`target/`. Put toolchains, caches and temporary build outputs where host storage
policy permits. Do not assume the home directory has space. A bare `rustup`
command can auto-install a whole toolchain into the default home; inspect host
policy and configured locations before invoking it or Cargo with a missing pin.

For small fast CLIs/hooks, consider this release profile and measure the result:

```toml
[profile.release]
lto = true
codegen-units = 1
strip = true
panic = "abort"
```

LTO and one codegen unit trade build time for cross-unit optimization; stripping
reduces shipped size but removes debugging symbols. Abort avoids unwinding cost
and size, but skips unwinding cleanup and catch-unwind recovery. Use only when
that failure behavior fits the contract; ordinary failures still return `Result`.
Keep defaults when these tradeoffs do not serve the application.

## Distribution

Build and test per supported target, including macOS arm64/x86_64, Windows MSVC
and Linux as required by the project. Typical triples are
`aarch64-apple-darwin`, `x86_64-apple-darwin`, `x86_64-pc-windows-msvc` and
`x86_64-unknown-linux-gnu`. Record the exact triple, toolchain, build command and a
SHA-256 for each final artifact (after signing or packaging). Cross-compilation
alone is not evidence that a binary runs on its target.

On macOS, a default ad-hoc/linker signature identity can change every build.
OS privacy permissions granted to that identity may not carry to the next build.
Keeping a grant across builds needs a stable signing identity chosen by the host
owner. Do not choose a certificate. Follow host-owned signing and permission
verification before replacing an executable that accesses protected resources.
