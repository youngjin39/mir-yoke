---
name: rust
description: "Rust coding, code analysis, project structure and parity-guided porting.\n\nTrigger: Rust, Cargo.toml, crate, cargo, clippy, rustfmt, native binary in Rust, porting Python (or another language) to Rust"
context: fork
---

# Rust

## When to use

Load on demand only for Rust work: writing or analyzing Rust code, configuring a
crate or workspace, building a Rust native binary, or porting another language to Rust.
A generic native-binary request alone does not select Rust.

Do not load for unrelated languages or as always-on context. Do not convert a
working implementation without a measured hot path or a distribution need. The
existing implementation stays the reference until parity passes.

## Procedure

1. Read project instructions, manifests, toolchain pins and the observable contract.
   Identify the smallest Rust scope and the reason for any port.
2. Use [structure and configuration](references/structure.md) to choose a single
   crate or workspace and honor host storage and signing policy before invoking tools.
3. Apply [coding rules](references/coding.md) to types, errors, schemas, text and paths.
   Prefer minimal dependencies and explicit contracts.
4. For a port, follow [parity and measurement](references/porting.md): capture the
   reference first, write golden fixtures and run both implementations. Keep callers
   on the reference until byte parity and measured latency justify switching.
5. Use [analysis and gates](references/analysis.md). Show each new behavioral test
   failing before implementation, then passing. Read full diagnostics and fix causes.
6. Report changed behavior, exact checks and results, intentional differences,
   measurements and any unexecuted platform or distribution checks.
