use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

#[test]
fn warmup_exits_silently_without_reading_stdin_or_touching_state() {
    let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .or_else(|| std::env::var_os("CARGO_TARGET_DIR"))
        .map(std::path::PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = base.join(format!("warmup-state-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    let binary = env!("CARGO_BIN_EXE_mir-mcp");
    let mut child = Command::new(binary)
        .args(["--mir-warmup", "--invalid-option"])
        .current_dir(&root)
        .env("CLAUDE_PROJECT_DIR", &root)
        .env("CODEX_HOME", &root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    // Keep stdin open: a read-until-EOF would block until the deadline.
    let input = child.stdin.take().unwrap();
    let deadline = Instant::now() + Duration::from_secs(if cfg!(windows) { 35 } else { 2 });
    loop {
        if child.try_wait().unwrap().is_some() {
            break;
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("warmup blocked: {binary}");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    drop(input);
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success(), "{binary}: {output:?}");
    assert!(output.stdout.is_empty(), "{binary}: {output:?}");
    assert!(output.stderr.is_empty(), "{binary}: {output:?}");
    assert_eq!(std::fs::read_dir(&root).unwrap().count(), 0);
    std::fs::remove_dir(root).unwrap();
}
