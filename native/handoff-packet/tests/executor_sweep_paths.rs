//! Dry-run path parity; the fixture driver permits only fake, read-only Git calls.
#[cfg(unix)]
#[test]
fn sweep_python_path_spellings() {
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .unwrap_or_else(|| std::env::temp_dir().into_os_string());
    let output = std::process::Command::new("python3")
        .args([
            "-I",
            "tests/fixtures/generate_executor_sweep_paths.py",
            "--scratch",
        ])
        .arg(std::path::Path::new(&scratch).join(format!("paths-{}", std::process::id())))
        .arg("--native")
        .arg(env!("CARGO_BIN_EXE_executor-query"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    eprint!("{}", String::from_utf8_lossy(&output.stdout));
}
