//! Private entrypoint receipt: claim ownership before any command effects.
use std::sync::atomic::{AtomicBool, Ordering};

static OWNED: AtomicBool = AtomicBool::new(false);

/// Call before hook imports, output, registry writes, or provider launch.
/// A failed receipt write must decline before any effects. Direct invocations
/// without a receipt path retain their existing behavior.
pub fn claim() {
    if OWNED.load(Ordering::Relaxed) {
        return;
    }
    if let Some(path) = std::env::var_os("MIR_EXECUTOR_OWNED_RECEIPT")
        && std::fs::write(path, b"owned").is_err()
    {
        std::process::exit(64);
    }
    OWNED.store(true, Ordering::Relaxed);
}
