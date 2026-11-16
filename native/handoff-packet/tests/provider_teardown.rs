#![cfg(unix)]
use std::{fs, path::PathBuf, process::Command};

fn scenario(mode: &str) {
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    fs::create_dir_all(&scratch).unwrap();
    let root = tempfile::tempdir_in(scratch).unwrap();
    let output = Command::new("python3")
        .args([
            "-I",
            concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/tests/fixtures/provider_teardown.py"
            ),
        ])
        .arg(env!("CARGO_BIN_EXE_executor-query"))
        .arg(root.path())
        .arg(mode)
        .current_dir(root.path())
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn sigterm_pairs_token_after_reap() {
    scenario("term");
}
#[test]
fn interruption_before_spawn_pairs_token() {
    scenario("early-term");
}
#[test]
fn sigint_pairs_token_after_reap() {
    scenario("int");
}
#[test]
fn surviving_descendant_is_uncertain() {
    scenario("descendant");
}
#[test]
fn clean_provider_stays_clean() {
    scenario("complete");
}
#[test]
fn initialize_failure_retains_live_descendant_lease() {
    scenario("init-live");
}
#[test]
fn dispatch_interruption_preserves_running_job_and_streams() {
    scenario("dispatch-term");
}
#[test]
fn writer_exit_signal_preserves_selected_interruption() {
    scenario("double");
}

#[test]
fn dispatch_success_retains_live_descendant_lease() {
    scenario("dispatch-descendant");
}

#[test]
fn dispatch_initialize_failure_retains_live_descendant_lease() {
    scenario("dispatch-init-live");
}

#[test]
fn reviewer_interruption_preserves_permanent_artifacts() {
    scenario("reviewer-term");
}

#[test]
fn reviewer_success_retains_live_descendant_lease() {
    scenario("reviewer-descendant");
}

#[test]
fn reviewer_initialize_failure_retains_live_descendant_lease() {
    scenario("reviewer-init-live");
}
