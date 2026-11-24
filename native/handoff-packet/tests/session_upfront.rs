//! Frozen Python renderer bytes through the supported native SessionStart route.
#![cfg(unix)]
#[path = "support/replay.rs"]
#[allow(dead_code)]
mod frozen;
#[path = "../src/session_upfront.rs"]
mod renderer;
use serde_json::Value;
use std::{fs, process::Command};

#[test]
fn frozen_python_upfront_context_without_builder() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/session-upfront.json")).unwrap();
    let baseline: Value =
        serde_json::from_str(include_str!("fixtures/w1/session-start.json")).unwrap();
    let ready = baseline["records"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["case"] == "profile-missing")
        .unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let mut command = frozen::prepare(&root);
        frozen::install(&ready["setup"], &root);
        let project = root.join("project");
        fs::remove_file(project.join("scripts/build_session_upfront_context.py")).unwrap();
        for path in [".mir/repo-profile.toml", "tasks/intent.json"] {
            let _ = fs::remove_file(project.join(path));
        }
        for (path, body) in case["files"].as_object().unwrap() {
            let path = project.join(path);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, frozen::decode(body)).unwrap();
        }
        for path in case["directories"].as_array().unwrap() {
            fs::create_dir_all(project.join(path.as_str().unwrap())).unwrap();
        }
        for (path, target) in case["links"].as_object().unwrap() {
            let path = project.join(path);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::os::unix::fs::symlink(target.as_str().unwrap(), path).unwrap();
        }
        let before = frozen::snapshot(&project);
        let output = command.arg("session-start").output().unwrap();
        assert_eq!(output.status.code(), Some(0), "{}", case["id"]);
        assert!(output.stderr.is_empty(), "{}", case["id"]);
        let expected = if case["python_defect"] == true {
            // Frozen reference bytes remain separate from diagnosed safe corrections.
            frozen::decode(&case["native_expected"]["stdout"])
        } else {
            assert_eq!(case["expected"]["exit"], 0);
            assert!(frozen::decode(&case["expected"]["stderr"]).is_empty());
            frozen::decode(&case["expected"]["stdout"])
        };
        assert_eq!(
            format!("{}\n", renderer::build(&project)).as_bytes(),
            expected,
            "{} direct bytes",
            case["id"]
        );
        assert!(!renderer::build(&project).contains("Context depth on demand"));
        let mut expected = [b"=== SESSION CONTEXT ===\n".as_slice(), &expected, b"\n"].concat();
        if expected.len() > 10239 {
            let text = std::str::from_utf8(&expected).unwrap();
            let mut end = 10239 - 64;
            while !text.is_char_boundary(end) {
                end -= 1;
            }
            expected = [
                expected[..end].to_vec(),
                b"\n[mir] session-start context truncated at 10KB (F3 cap)\n".to_vec(),
            ]
            .concat();
        }
        while expected.ends_with(b"\n\n") {
            expected.pop();
        }
        assert_eq!(output.stdout, expected, "{}", case["id"]);
        assert_eq!(
            frozen::snapshot(&project),
            before,
            "{} mutated project",
            case["id"]
        );
    }
}

#[test]
fn legacy_shell_uses_real_native_without_python() {
    let temp = tempfile::tempdir().unwrap();
    let project = temp.path();
    let bin = project.join(".mir/bin");
    fs::create_dir_all(&bin).unwrap();
    fs::copy(
        env!("CARGO_BIN_EXE_project-hooks"),
        bin.join("project-hooks"),
    )
    .unwrap();
    let output = Command::new("/bin/bash")
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../.claude/hooks/session-start.sh"
        ))
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("HOME", project.join("home"))
        .env("CLAUDE_PROJECT_DIR", project)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    assert!(
        String::from_utf8(output.stdout)
            .unwrap()
            .contains("bootstrap_gate: required (state=missing)")
    );
}

#[test]
fn shell_native_availability_and_exit_policy() {
    use std::os::unix::fs::{PermissionsExt, symlink};
    let script = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../.claude/hooks/session-start.sh"
    );
    for (state, status, expected) in [
        ("missing", 0, 0),
        ("disabled", 0, 0),
        ("not-executable", 0, 0),
        ("symlink", 0, 0),
        ("bin-symlink", 0, 0),
        ("mir-symlink", 0, 0),
        ("warmup-fails", 0, 0),
        ("ready", 0, 0),
        ("ready", 1, 1),
        ("ready", 64, 0),
        ("ready", 126, 0),
        ("ready", 127, 0),
    ] {
        let temp = tempfile::tempdir().unwrap();
        let project = temp.path();
        let bin = project.join(".mir/bin");
        fs::create_dir_all(&bin).unwrap();
        let native = bin.join("project-hooks");
        if state != "missing" {
            fs::write(&native, format!("#!/bin/sh\nif [ \"$1\" = --mir-warmup ]; then exit {}; fi\n[ \"$1\" = session-start ] || exit 90\nprintf 'native context\\n'\nexit {status}\n", if state == "warmup-fails" { 1 } else { 0 })).unwrap();
            fs::set_permissions(
                &native,
                fs::Permissions::from_mode(if state == "not-executable" {
                    0o644
                } else {
                    0o755
                }),
            )
            .unwrap();
        }
        let linked = match state {
            "symlink" => Some(native),
            "bin-symlink" => Some(bin),
            "mir-symlink" => Some(project.join(".mir")),
            _ => None,
        };
        if let Some(linked) = linked {
            let actual = project.join("actual");
            fs::rename(&linked, &actual).unwrap();
            symlink(actual, linked).unwrap();
        }
        let out = Command::new("/bin/bash")
            .arg(script)
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("HOME", project.join("home"))
            .env("CLAUDE_PROJECT_DIR", project)
            .env(
                "MIR_NATIVE_HOOKS",
                if state == "disabled" { "0" } else { "1" },
            )
            .output()
            .unwrap();
        assert_eq!(out.status.code(), Some(expected), "{state}/{status}");
        assert_eq!(
            out.stdout,
            if state == "ready" {
                b"native context\n".as_slice()
            } else {
                b""
            },
            "{state}/{status}"
        );
        assert_eq!(
            out.stderr,
            if state != "ready" || [64, 126, 127].contains(&status) {
                b"project-hooks: native unavailable\n".as_slice()
            } else {
                b""
            },
            "{state}/{status}"
        );
    }
}
