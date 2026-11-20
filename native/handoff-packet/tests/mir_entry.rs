#![cfg(unix)]
use serde_json::Value;
use std::{
    ffi::OsString,
    fs,
    io::Write,
    os::unix::{ffi::OsStringExt, fs::PermissionsExt, process::ExitStatusExt},
    path::{Path, PathBuf},
    process::{Command, Stdio},
};

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
                | "capability"
                | "bootstrap"
                | "relations"
                | "project-hooks"
                | "context"
                | "loop"
                | "policy"
                | "runtime-manifest"
                | "run-python"
                | "migrate"
                | "executor"
                | "memory"
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

fn install_mir(root: &Path) -> PathBuf {
    let bin = root.join("tool bin");
    fs::create_dir_all(&bin).unwrap();
    let mir = bin.join("mir");
    fs::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
    mir
}

fn caller(root: &Path, program: &Path) -> Command {
    let mut command = Command::new(program);
    command
        .env_clear()
        .env("HOME", root)
        .env("PATH", root.join("unrelated bin"))
        .current_dir(root);
    command
}

fn write_script(path: &Path, script: &str, mode: u32) {
    fs::write(path, script).unwrap();
    fs::set_permissions(path, fs::Permissions::from_mode(mode)).unwrap();
}

#[test]
fn compatibility_families_refuse_unusable_interpreter() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path();
    let mir = install_mir(root);
    // A PATH interpreter and any accidental shell fallback leave a marker.
    let path_bin = root.join("unrelated bin");
    fs::create_dir(&path_bin).unwrap();
    let effect = ": > started\n";
    write_script(
        &path_bin.join("python"),
        &format!("#!/bin/sh\n{effect}"),
        0o755,
    );
    let python = root.join("tool bin/python");
    for state in ["missing", "non-executable", "invalid executable"] {
        match state {
            "non-executable" => write_script(&python, &format!("#!/bin/sh\n{effect}"), 0o644),
            "invalid executable" => write_script(&python, effect, 0o755),
            _ => (),
        }
        for family in ["executor", "memory"] {
            let output = caller(root, &mir)
                .args([family, "--help"])
                .output()
                .unwrap();
            let case = format!("{family}: {state}: {output:?}");
            assert_eq!(output.status.code(), Some(1), "{case}");
            assert!(output.stdout.is_empty(), "{case}");
            let stderr = std::str::from_utf8(&output.stderr).unwrap();
            assert!(
                stderr.starts_with("mir: ") && stderr.contains("bound Python interpreter"),
                "{case}"
            );
            assert!(
                stderr.ends_with('\n') && stderr.lines().count() == 1,
                "{case}"
            );
            assert!(!root.join("started").exists(), "{case}");
        }
    }
}

#[test]
fn compatibility_families_exit_one_with_closed_stderr_pipe() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path();
    let mir = install_mir(root);
    // Executable permissions let this shebang-free file reach execv and fail with ENOEXEC.
    write_script(&root.join("tool bin/python"), ":\n", 0o755);

    let statuses = ["executor", "memory"].map(|family| {
        let (reader, writer) = std::io::pipe().unwrap();
        drop(reader);
        let status = caller(root, &mir)
            .args([family, "--help"])
            .stderr(Stdio::from(writer))
            .status()
            .unwrap();
        (family, status.code(), status.signal())
    });
    assert_eq!(
        statuses,
        [("executor", Some(1), None), ("memory", Some(1), None)]
    );
}

fn assert_compatibility_route(family: &str, status: i32) {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let mir = install_mir(&root);
    let cwd = root.join("nested caller");
    fs::create_dir(&cwd).unwrap();
    write_script(
        &root.join("tool bin/python"),
        r#"#!/bin/sh
printf '%s\0' "$@" > argv
printf '%s\0' "$(/bin/pwd -P)" "$F04Y_MARKER" "$PYTHONIOENCODING" > context
/bin/cat > input
printf '\377stdout\000'
printf '\376stderr\000' >&2
exit "$F04Y_STATUS"
"#,
        0o755,
    );
    let raw = OsString::from_vec(vec![b'x', 255]);
    let stdin = b"caller\0stdin\xff\n";
    let mut child = caller(&root, &mir)
        .args([family, "arg with space", "--", ""])
        .arg(&raw)
        .arg("--")
        .env("F04Y_MARKER", &raw)
        .env("F04Y_STATUS", status.to_string())
        .env("PYTHONIOENCODING", "unknown-codec")
        .current_dir(&cwd)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let write = child.stdin.take().unwrap().write_all(stdin);
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code(), Some(status), "{family}: {output:?}");
    write.unwrap();
    assert_eq!(output.stdout, b"\xffstdout\0");
    assert_eq!(output.stderr, b"\xfestderr\0");
    assert_eq!(
        fs::read(cwd.join("argv")).unwrap(),
        [
            b"-m\0mir.cli\0".as_slice(),
            family.as_bytes(),
            b"\0arg with space\0--\0\0x\xff\0--\0"
        ]
        .concat()
    );
    assert_eq!(
        fs::read(cwd.join("context")).unwrap(),
        [
            cwd.as_os_str().as_encoded_bytes(),
            b"\0x\xff\0unknown-codec\0"
        ]
        .concat()
    );
    assert_eq!(fs::read(cwd.join("input")).unwrap(), stdin);
}

#[test]
fn executor_uses_bound_cli_module() {
    // A child exit of 64 is final.
    assert_compatibility_route("executor", 64);
}

#[test]
fn executor_preserves_default_sigpipe() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path();
    let mir = install_mir(root);
    let python = root.join("tool bin/python");
    write_script(&python, "#!/bin/sh\nkill -s PIPE $$\nexit 73\n", 0o755);
    let direct = caller(root, &python)
        .args(["-m", "mir.cli", "executor", "--help"])
        .output()
        .unwrap();
    assert_eq!(direct.status.signal(), Some(libc::SIGPIPE), "{direct:?}");
    let routed = caller(root, &mir)
        .args(["executor", "--help"])
        .output()
        .unwrap();
    assert_eq!(routed, direct);
}

#[test]
fn memory_uses_bound_cli_module() {
    assert_compatibility_route("memory", 37);
}

#[test]
fn compatibility_help_matches_real_pinned_python() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path();
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pinned = repo.join(".venv/bin/python");
    let mir = install_mir(root);
    write_script(
        &root.join("tool bin/python"),
        "#!/bin/sh\nexec \"$F04Y_PINNED_PYTHON\" \"$@\"\n",
        0o755,
    );
    let pythonpath = repo.join("src");
    let expected = caller(root, &pinned)
        .env("PYTHONPATH", &pythonpath)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .args(["-m", "mir.cli", "memory", "--help"])
        .output()
        .unwrap();
    assert!(expected.status.success(), "{expected:?}");
    let actual = caller(root, &mir)
        .env("F04Y_PINNED_PYTHON", &pinned)
        .env("PYTHONPATH", &pythonpath)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .args(["memory", "--help"])
        .output()
        .unwrap();
    assert_eq!(actual, expected);
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
