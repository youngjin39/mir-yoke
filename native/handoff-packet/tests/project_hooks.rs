//! The probe and warmup must finish while the caller still owns open stdin.
use std::{
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

fn run(args: &[&str], code: i32, stdout: &[u8], stderr: &[u8]) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_project-hooks"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let input = child.stdin.take().unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if child.try_wait().unwrap().is_some() {
            break;
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("project-hooks waited for stdin");
        }
        thread::sleep(Duration::from_millis(10));
    }
    let output = child.wait_with_output().unwrap();
    drop(input);
    assert_eq!(output.status.code(), Some(code));
    assert_eq!(output.stdout, stdout);
    assert_eq!(output.stderr, stderr);
}

#[test]
fn capabilities() {
    run(
        &["capabilities"],
        0,
        b"mir-project-hooks-v1\nmir-project-hooks-compact-v1\nmir-project-hooks-tdd-v1\n",
        b"",
    );
}

#[test]
fn warmup() {
    run(&["--mir-warmup"], 0, b"", b"");
}

#[test]
fn unknown_subcommand() {
    for args in [vec![], vec!["unknown"], vec!["capabilities", "extra"]] {
        run(&args, 64, b"", b"project-hooks: unknown subcommand\n");
    }
}
