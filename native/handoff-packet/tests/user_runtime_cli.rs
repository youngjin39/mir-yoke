#![cfg(unix)]
use serde_json::Value;
use std::{
    ffi::OsString,
    fs,
    os::unix::{ffi::OsStringExt, fs::PermissionsExt},
    process::{Command, Stdio},
};

#[test]
#[rustfmt::skip] // Compact frozen-process matrix keeps the bounded migration diff reviewable.
fn user_runtime_cli_frozen_processes() {
    let records: Vec<Value> = serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/cli.json")).unwrap();
    let temporary = tempfile::tempdir().unwrap(); // Gate supplies synthetic TMPDIR.
    for record in records {
        let name = record["name"].as_str().unwrap();
        let root = temporary.path().join(name);
        for folder in ["provider/config", "provider/.claude/agents", "provider/.codex/agents", "bin"] {
            fs::create_dir_all(root.join(folder)).unwrap();
        }
        let root = root.canonicalize().unwrap();
        let provider = root.join("provider");
        let config = br#"{"agents":{"allowlist":[".claude/agents/a.md"]},"commands":{"allowlist":{}},"profiles":{"packs":{"p":{"agents":[".claude/agents/a.md"],"commands":[]}}}}"#;
        fs::write(provider.join("config/capability-sources.json"), if name == "unexpected" { b"\xff".as_slice() } else { config }).unwrap();
        fs::write(provider.join(".claude/agents/a.md"), b"agent\n").unwrap();
        fs::write(provider.join(".codex/agents/a.toml"), b"agent = true\n").unwrap();
        let mut git = String::from("#!/bin/sh\ncase \"$CASE:$3\" in\nstatus-fail:status) exit 1;;\ndirty:status) echo ' M config/capability-sources.json';;\nbad-head:rev-parse) echo invalid;;\nhead-fail:rev-parse) exit 1;;\n*:rev-parse) echo ffffffffffffffffffffffffffffffffffffffff;;\nesac\n");
        if name == "apply-mkdir-error" {
            git = git.replace("case \"$CASE:$3\" in", "if [ \"$3\" = rev-parse ]; then /usr/bin/touch \"$CASE_ROOT/claude\"; fi\ncase \"$CASE:$3\" in");
        }
        if name != "missing-git" {
            fs::write(root.join("bin/git"), git).unwrap();
            fs::set_permissions(root.join("bin/git"), fs::Permissions::from_mode(0o755)).unwrap();
        }
        if name == "transaction-error" {
            fs::create_dir(root.join("claude")).unwrap();
            fs::set_permissions(root.join("claude"), fs::Permissions::from_mode(0o555)).unwrap();
        }
        let args: Vec<OsString> = record["argv"].as_array().unwrap().iter().map(|arg| {
            let arg = arg.as_str().unwrap().replace("{ROOT}", root.to_str().unwrap());
            let mut bytes = Vec::new();
            for (i, part) in arg.split("{NONUTF}").enumerate() {
                if i > 0 { bytes.push(255); }
                bytes.extend_from_slice(part.as_bytes());
            }
            OsString::from_vec(bytes)
        }).collect();
        let mut command = Command::new(env!("CARGO_BIN_EXE_user-runtime-install"));
        let columns = match name {
            "help-width-spaces" => " 40 ", "help-width-underscore" => "1_00", "help-width-unicode" => "٤٠",
            _ => name.strip_prefix("help-width").unwrap_or("80"),
        };
        command.env("COLUMNS", columns);
        if name.starts_with("buffered-") { command.env_remove("PYTHONUNBUFFERED"); }
        else { command.env("PYTHONUNBUFFERED", "1"); }
        let stdout = if name.ends_with("broken-stdout") {
            let (reader, writer) = std::os::unix::net::UnixStream::pair().unwrap();
            drop(reader);
            Stdio::from(std::os::fd::OwnedFd::from(writer))
        } else { Stdio::piped() };
        let stderr = if name.ends_with("broken-stderr") {
            let (reader, writer) = std::os::unix::net::UnixStream::pair().unwrap();
            drop(reader);
            Stdio::from(std::os::fd::OwnedFd::from(writer))
        } else { Stdio::piped() };
        let child = command.arg(&provider).args(args).current_dir(&root)
            .env("HOME", root.join("home")).env("TMPDIR", &root)
            .env("PATH", root.join("bin")).env("CASE", name).env("CASE_ROOT", &root)
            .stdout(stdout).stderr(stderr).spawn().unwrap();
        let output = child.wait_with_output().unwrap();
        if name == "transaction-error" {
            fs::set_permissions(root.join("claude"), fs::Permissions::from_mode(0o755)).unwrap();
        }
        let normalize = |bytes: Vec<u8>| String::from_utf8(bytes).unwrap().replace(root.to_str().unwrap(), "{ROOT}");
        assert_eq!(output.status.code(), Some(record["code"].as_i64().unwrap() as i32), "{name}: {:?}", output);
        assert_eq!(normalize(output.stdout), record["stdout"].as_str().unwrap(), "{name} stdout");
        assert_eq!(normalize(output.stderr), record["stderr"].as_str().unwrap(), "{name} stderr");
        if name == "dry-run" || name == "abbreviated" || name == "normalized" {
            assert!(!root.join("claude").exists(), "{name} wrote claude home");
            assert!(!root.join("codex").exists(), "{name} wrote codex home");
        }
        if name == "apply" || name == "duplicate" {
            let home = root.join(if name == "duplicate" { "last" } else { "claude" });
            assert_eq!(fs::read(home.join("agents/a.md")).unwrap(), b"agent\n");
            assert_eq!(fs::read(root.join("codex/agents/a.toml")).unwrap(), b"agent = true\n");
            for path in [home, root.join("codex")] {
                let receipt: Value = serde_json::from_slice(&fs::read(path.join("mir-yoke-agent-command-receipt.json")).unwrap()).unwrap();
                assert_eq!(receipt["source_commit"], "ffffffffffffffffffffffffffffffffffffffff");
            }
        }
    }
}

#[test]
fn user_runtime_cli_requires_provider() {
    let root = tempfile::tempdir().unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_user-runtime-install"))
        .current_dir(root.path())
        .env("HOME", root.path())
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
    assert!(!output.stderr.is_empty());
}
