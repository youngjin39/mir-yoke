#![cfg(unix)]
use serde_json::Value;
use std::{ffi::OsString, fs, os::unix::ffi::OsStringExt, process::Command};

fn bytes(v: &Value) -> Vec<u8> {
    v.as_str()
        .unwrap()
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|s| u8::from_str_radix(std::str::from_utf8(s).unwrap(), 16).unwrap())
        .collect()
}

#[test]
fn frozen_console_processes() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e1.json")).unwrap();
    for (i, r) in records.iter().enumerate() {
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        fs::create_dir(root.join("tasks")).unwrap();
        fs::write(root.join("tasks/plan.md"), r["plan"].as_str().unwrap()).unwrap();
        let output = Command::new(env!("CARGO_BIN_EXE_mir"))
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| OsString::from_vec(bytes(v))),
            )
            .env_clear()
            .env("HOME", &root)
            .env("PYTHONIOENCODING", r["encoding"].as_str().unwrap())
            .current_dir(&root)
            .output()
            .unwrap();
        assert_eq!(
            output.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{i}"
        );
        assert_eq!(output.stdout, bytes(&r["stdout"]), "stdout {i}");
        assert_eq!(output.stderr, bytes(&r["stderr"]), "stderr {i}");
        assert_eq!(
            fs::read_to_string(root.join("tasks/plan.md")).unwrap(),
            r["after"].as_str().unwrap(),
            "effect {i}"
        );
    }
}

#[test]
fn unbound_families_are_explicit() {
    for name in handoff_packet::mir_front::SUBCOMMANDS {
        if matches!(
            name,
            "bootstrap-adoption"
                | "relations"
                | "project-hooks"
                | "context"
                | "loop"
                | "policy"
                | "runtime-manifest"
                | "run-python"
                | "migrate"
        ) {
            continue;
        }
        let temp = tempfile::tempdir().unwrap();
        let output = Command::new(env!("CARGO_BIN_EXE_mir"))
            .args([name, "--help"])
            .env_clear()
            .env("HOME", temp.path())
            .current_dir(temp.path())
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(64), "{name}");
        assert!(output.stdout.is_empty());
        assert_eq!(
            output.stderr,
            format!("mir: native route unavailable: {name} (pending entry closure)\n").as_bytes()
        );
    }
}

#[test]
fn invalid_codec_cannot_mutate() {
    let temp = tempfile::tempdir().unwrap();
    fs::create_dir(temp.path().join("tasks")).unwrap();
    fs::write(
        temp.path().join("tasks/plan.md"),
        "## Active Task\nStep 1: TODO\n",
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_mir"))
        .args(["loop", "mark", "--step", "1", "--status", "DONE"])
        .env_clear()
        .env("PYTHONIOENCODING", "unknown-codec")
        .env("HOME", temp.path())
        .current_dir(temp.path())
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(
        fs::read_to_string(temp.path().join("tasks/plan.md")).unwrap(),
        "## Active Task\nStep 1: TODO\n"
    );
    assert!(output.stdout.is_empty());
}

#[test]
fn byte_mark_parser_does_not_read_fifo() {
    let temp = tempfile::tempdir().unwrap();
    fs::create_dir(temp.path().join("tasks")).unwrap();
    assert!(
        Command::new("mkfifo")
            .arg(temp.path().join("tasks/plan.md"))
            .status()
            .unwrap()
            .success()
    );
    let mut child = Command::new(env!("CARGO_BIN_EXE_mir"))
        .args([
            OsString::from("loop"),
            "mark".into(),
            OsString::from_vec(vec![255]),
        ])
        .env_clear()
        .env("HOME", temp.path())
        .current_dir(temp.path())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    let start = std::time::Instant::now();
    while child.try_wait().unwrap().is_none() && start.elapsed().as_secs() < 2 {
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    let timed_out = child.try_wait().unwrap().is_none();
    if timed_out {
        child.kill().unwrap();
    }
    let out = child.wait_with_output().unwrap();
    assert!(!timed_out, "parser blocked reading plan FIFO");
    assert_eq!(out.status.code(), Some(2));
}
