# Rust analysis and verification

Run gates in this order from the relevant crate or workspace:

```sh
cargo fmt --check
cargo clippy --all-targets --locked -- -D warnings
cargo test --locked
cargo build --release --locked
```

Read the full compiler or Clippy diagnostic, including notes and suggested context.
Fix the cause. Every `#[allow(...)]` needs a reason comment and the narrowest scope;
do not silence a whole crate to hide a local issue.

Review `cargo tree`, duplicate versions (`cargo tree --duplicates`) and feature
selection (`cargo tree --edges features`). Remove unnecessary dependencies and
features. Run `cargo audit` or `cargo deny` when installed and relevant; they are
optional checks, not prerequisites to installing or using this skill. Record when
not run rather than claiming a clean dependency audit.

## Agent-written code checklist

- Find production `unwrap`, `expect` and panic paths and replace them with errors.
- Check that conversions preserve error kinds and source chains.
- Reject wildcard matches that mask new owned enum variants.
- Inspect lossy text/path conversions and stdout/stderr encoding.
- Look for blocking I/O inside async code; use the runtime's appropriate boundary.
- Bound stdin reads according to the input contract; reject or stream excess data.
- Reject tests that assert nothing. Show a new behavioral test failing for its
  intended reason before implementation, then passing through the real changed route.
- Check parity fixtures and platform evidence before accepting a port or artifact.
