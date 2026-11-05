//! Exact immutable replay using the freeze's isolation and normalization.
#![cfg(not(windows))] // POSIX frozen modes; Windows is type-checked separately.
#[test]
fn checkpoint_frozen_records() {
    let output = std::process::Command::new("python3")
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/checkpoint_replay.py"
        ))
        .arg(env!("CARGO_BIN_EXE_project-hooks"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    print!("{}", String::from_utf8_lossy(&output.stdout));
}
