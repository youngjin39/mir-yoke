//! Private entrypoint receipt: claim ownership before any command effects.
use std::sync::atomic::{AtomicBool, Ordering};

static OWNED: AtomicBool = AtomicBool::new(false);

/// Opt-in test diagnostics. Never write to the CLI streams or affect admission.
#[track_caller]
pub fn decline(reason: &str) -> i32 {
    if !OWNED.load(Ordering::Relaxed)
        && let Some(path) = std::env::var_os("MIR_EXECUTOR_DECLINE_TRACE")
        && let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
    {
        use std::io::Write;
        let reason = reason.replace(['\r', '\n'], " ");
        let _ = writeln!(file, "{}: {reason}", std::panic::Location::caller());
    }
    64
}

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
        std::process::exit(decline("ownership receipt write failed"));
    }
    OWNED.store(true, Ordering::Relaxed);
}
