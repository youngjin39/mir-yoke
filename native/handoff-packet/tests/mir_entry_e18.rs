//! Literal reference records are frozen before replay at the same synthetic paths.
#![cfg(unix)]
use std::{fs, path::PathBuf, process::Command};

#[test]
fn public_bootstrap_interpreter_receipts() {
    let package = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let scratch = package.join("target/mig-scratch/Y-E18");
    fs::create_dir_all(&scratch).unwrap();
    let tmp = tempfile::tempdir_in(scratch).unwrap();
    let out = Command::new(package.join("../../.venv/bin/python"))
        .args(["-I", "-X", "utf8"])
        .arg(package.join("tests/fixtures/generate_y_e18.py"))
        .arg("--scratch")
        .arg(tmp.path())
        .arg("--output")
        .arg(tmp.path().join("frozen.json"))
        .arg("--binary")
        .arg(env!("CARGO_BIN_EXE_mir"))
        .env("HOME", tmp.path())
        .current_dir(tmp.path())
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
#[cfg(target_os = "macos")]
fn public_bootstrap_phase1_memory_receipts() {
    let package = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let scratch = package.join("target/mig-scratch/Y-E18-p2");
    fs::create_dir_all(&scratch).unwrap();
    let tmp = tempfile::tempdir_in(scratch).unwrap();
    let out = Command::new(package.join("../../.venv/bin/python"))
        .args(["-I", "-X", "utf8"])
        .arg(package.join("tests/fixtures/generate_y_e18_p2.py"))
        .arg("--scratch")
        .arg(tmp.path())
        .arg("--output")
        .arg(tmp.path().join("frozen.json"))
        .arg("--binary")
        .arg(env!("CARGO_BIN_EXE_mir"))
        .env("HOME", tmp.path())
        .current_dir(tmp.path())
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
#[cfg(target_os = "macos")]
fn public_bootstrap_phase2_content() {
    replay_phase2(&[]);
    replay_phase2(&["--yaml-diagnostics"]);
    replay_phase2(&["--yaml-p3c"]);
}

#[test]
#[cfg(target_os = "macos")]
fn public_bootstrap_numeric_diagnostics() {
    replay_phase2(&["--yaml-p3d"]);
}

#[test]
#[cfg(target_os = "macos")]
fn public_bootstrap_adopter_verification() {
    let package = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let scratch = package.join("target/mig-scratch/Y-E18-p4");
    fs::create_dir_all(&scratch).unwrap();
    let tmp = tempfile::tempdir_in(scratch).unwrap();
    let out = Command::new(package.join("../../.venv/bin/python"))
        .args(["-I", "-X", "utf8"])
        .arg(package.join("tests/fixtures/generate_y_e18_p4.py"))
        .arg("--scratch")
        .arg(tmp.path())
        .arg("--output")
        .arg(tmp.path().join("frozen.json"))
        .arg("--binary")
        .arg(env!("CARGO_BIN_EXE_mir"))
        .env("HOME", tmp.path())
        .current_dir(tmp.path())
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

#[cfg(target_os = "macos")]
#[test]
fn public_bootstrap_journal_commit() {
    let package = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let scratch = package.join("target/mig-scratch/Y-E18-p4b");
    fs::create_dir_all(&scratch).unwrap();
    let tmp = tempfile::tempdir_in(scratch).unwrap();
    let out = Command::new(package.join("../../.venv/bin/python"))
        .args(["-I", "-X", "utf8"])
        .arg(package.join("tests/fixtures/generate_y_e18_p4b.py"))
        .arg("--scratch")
        .arg(tmp.path())
        .arg("--output")
        .arg(tmp.path().join("frozen.json"))
        .arg("--binary")
        .arg(env!("CARGO_BIN_EXE_mir"))
        .env("HOME", tmp.path())
        .current_dir(tmp.path())
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

#[cfg(target_os = "macos")]
#[test]
fn public_bootstrap_interrupted_recovery() {
    let package = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let scratch = package.join("target/mig-scratch/Y-E18-p4c");
    fs::create_dir_all(&scratch).unwrap();
    let tmp = tempfile::tempdir_in(scratch).unwrap();
    let out = Command::new(package.join("../../.venv/bin/python"))
        .args(["-I", "-X", "utf8"])
        .arg(package.join("tests/fixtures/generate_y_e18_p4c.py"))
        .arg("--scratch")
        .arg(tmp.path())
        .arg("--output")
        .arg(tmp.path().join("frozen.json"))
        .arg("--binary")
        .arg(env!("CARGO_BIN_EXE_mir"))
        .env("HOME", tmp.path())
        .current_dir(tmp.path())
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

#[cfg(target_os = "macos")]
fn replay_phase2(extra: &[&str]) {
    let package = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let scratch = package.join("target/mig-scratch/Y-E18-p3");
    fs::create_dir_all(&scratch).unwrap();
    let tmp = tempfile::tempdir_in(scratch).unwrap();
    let out = Command::new(package.join("../../.venv/bin/python"))
        .args(["-I", "-X", "utf8"])
        .arg(package.join("tests/fixtures/generate_y_e18_p3.py"))
        .args(extra)
        .arg("--scratch")
        .arg(tmp.path())
        .arg("--output")
        .arg(tmp.path().join("frozen.json"))
        .arg("--binary")
        .arg(env!("CARGO_BIN_EXE_mir"))
        .env("HOME", tmp.path())
        .current_dir(tmp.path())
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}
