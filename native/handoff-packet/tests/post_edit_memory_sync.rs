//! Python-frozen stdin, diagnostics, exit and delegated file-effect parity.
#![cfg(unix)]
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    os::unix::fs::PermissionsExt,
    path::Path,
    process::{Command, Stdio},
};

fn snapshot(root: &Path, base: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut result = BTreeMap::new();
    for entry in fs::read_dir(root).unwrap() {
        let path = entry.unwrap().path();
        let meta = fs::symlink_metadata(&path).unwrap();
        if meta.file_type().is_symlink() {
            continue;
        }
        if meta.is_dir() {
            result.extend(snapshot(&path, base));
        } else {
            result.insert(
                path.strip_prefix(base)
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .to_owned(),
                fs::read(&path).unwrap(),
            );
        }
    }
    result
}

#[test]
fn frozen_python_memory_sync() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/post-edit-memory-sync.json")).unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let temp = tempfile::tempdir().unwrap();
        let base = fs::canonicalize(temp.path()).unwrap();
        let base_text = base.to_str().unwrap();
        let project = base.join("project");
        fs::create_dir_all(&project).unwrap();
        for (path, body) in case["files"].as_object().unwrap() {
            let path = base.join(path);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, body.as_str().unwrap().replace("@BASE@", base_text)).unwrap();
        }
        for path in case["executable"].as_array().unwrap() {
            fs::set_permissions(
                base.join(path.as_str().unwrap()),
                fs::Permissions::from_mode(0o755),
            )
            .unwrap();
        }
        for (path, target) in case["links"].as_object().unwrap() {
            let path = base.join(path);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::os::unix::fs::symlink(target.as_str().unwrap(), path).unwrap();
        }
        let before = snapshot(&base, &base);
        let mut child = Command::new(env!("CARGO_BIN_EXE_project-hooks"))
            .arg("post-edit-memory-sync")
            .env("CLAUDE_PROJECT_DIR", &project)
            .env("HOME", base.join("home"))
            .env("TMPDIR", &base)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(
                case["stdin"]
                    .as_str()
                    .unwrap()
                    .replace("@BASE@", base_text)
                    .as_bytes(),
            )
            .unwrap();
        let output = child.wait_with_output().unwrap();
        let expected = &case["expected"];
        assert_eq!(
            output.status.code(),
            Some(expected["exit"].as_i64().unwrap() as i32),
            "{}",
            case["id"]
        );
        assert_eq!(
            String::from_utf8(output.stdout)
                .unwrap()
                .replace(base_text, "@BASE@"),
            expected["stdout"].as_str().unwrap(),
            "{}",
            case["id"]
        );
        assert_eq!(
            String::from_utf8(output.stderr)
                .unwrap()
                .replace(base_text, "@BASE@"),
            expected["stderr"].as_str().unwrap(),
            "{}",
            case["id"]
        );
        let mut after = snapshot(&base, &base);
        for (path, body) in expected["effects"].as_object().unwrap() {
            assert_eq!(
                String::from_utf8(after.remove(&format!("project/{path}")).unwrap())
                    .unwrap()
                    .replace(base_text, "@BASE@"),
                body.as_str().unwrap(),
                "{}",
                case["id"]
            );
        }
        assert_eq!(before, after, "unexpected file effects: {}", case["id"]);
    }
}

#[test]
fn shell_native_availability_and_exit_policy() {
    let script =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.claude/hooks/post-edit-self-ingest.sh");
    for (state, status, expected) in [
        ("missing", 0, 0),
        ("disabled", 0, 0),
        ("symlink", 0, 0),
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
        let body = format!(
            "#!/bin/sh\nif [ \"$1\" = capabilities ]; then echo mir-project-hooks-post-edit-memory-sync-v1; exit 0; fi\nif [ \"$1\" = --mir-warmup ]; then exit {}; fi\n[ \"$1\" = post-edit-memory-sync ] || exit 90\ncat > input.json\nexit {status}\n",
            if state == "warmup-fails" { 1 } else { 0 }
        );
        if state != "missing" {
            fs::write(&native, body).unwrap();
            fs::set_permissions(&native, fs::Permissions::from_mode(0o755)).unwrap();
        }
        if state == "symlink" {
            fs::rename(&native, bin.join("actual")).unwrap();
            std::os::unix::fs::symlink("actual", &native).unwrap();
        }
        let mut child = Command::new("bash")
            .arg(&script)
            .current_dir(project)
            .env("CLAUDE_PROJECT_DIR", project)
            .env(
                "MIR_NATIVE_HOOKS",
                if state == "disabled" { "0" } else { "1" },
            )
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(b"{\"tool_input\":{\"path\":\"docs/x.md\"}}")
            .unwrap();
        let out = child.wait_with_output().unwrap();
        assert_eq!(out.status.code(), Some(expected), "{state}/{status}");
        assert!(out.stdout.is_empty());
        let launched = state == "ready";
        if launched {
            assert_eq!(
                fs::read(project.join("input.json")).unwrap(),
                b"{\"tool_input\":{\"path\":\"docs/x.md\"}}"
            );
        } else {
            assert!(!project.join("input.json").exists());
        }
        let unavailable = !launched || [64, 126, 127].contains(&status);
        assert_eq!(
            out.stderr,
            if unavailable {
                b"[mir-memory] skipped post-edit-memory-sync: native unavailable or outdated; repair: scripts/mir.sh project-hooks install --project-root .\n".as_slice()
            } else {
                b""
            }
        );
    }
}

#[test]
fn live_launcher_large_payload_syncs_and_reports_bound() {
    let temp = tempfile::tempdir().unwrap();
    let project = temp.path().join("project");
    fs::create_dir_all(project.join(".mir/bin")).unwrap();
    fs::write(project.join("harness_a.toml"), "").unwrap();
    fs::write(project.join(".mir/memory.db"), "synthetic").unwrap();
    let cli = temp.path().join("mir");
    let body = "#!/bin/sh\nprintf synced > effect.txt\n";
    fs::write(&cli, body).unwrap();
    fs::set_permissions(&cli, fs::Permissions::from_mode(0o755)).unwrap();
    let out = Command::new("shasum")
        .args(["-a", "256"])
        .arg(&cli)
        .output()
        .unwrap();
    let hash = String::from_utf8(out.stdout)
        .unwrap()
        .split_whitespace()
        .next()
        .unwrap()
        .to_owned();
    fs::write(
        project.join(".mir/bootstrap-receipt.json"),
        serde_json::json!({
            "cli": {"executable": cli, "sha256": hash}
        })
        .to_string(),
    )
    .unwrap();
    fs::copy(
        env!("CARGO_BIN_EXE_project-hooks"),
        project.join(".mir/bin/project-hooks"),
    )
    .unwrap();
    let script =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.claude/hooks/post-edit-self-ingest.sh");
    for size in [1_048_577, 10_000_000, 16 * 1024 * 1024 + 1] {
        let payload =
            serde_json::json!({"tool_input":{"file_path":"docs/x.md", "content":"a".repeat(size)}})
                .to_string();
        let input = temp.path().join("input.json");
        fs::write(&input, payload).unwrap();
        let out = Command::new("bash")
            .arg(&script)
            .current_dir(&project)
            .env("CLAUDE_PROJECT_DIR", &project)
            .env("MIR_NATIVE_HOOKS", "1")
            .stdin(fs::File::open(input).unwrap())
            .output()
            .unwrap();
        assert_eq!(out.status.code(), Some(0));
        if size <= 10_000_000 {
            assert_eq!(fs::read(project.join("effect.txt")).unwrap(), b"synced");
            fs::remove_file(project.join("effect.txt")).unwrap();
            assert!(out.stderr.is_empty(), "{:?}", out.stderr);
        } else {
            assert!(!project.join("effect.txt").exists());
            let diagnostic = String::from_utf8(out.stderr).unwrap();
            assert!(diagnostic.contains("16777216"), "{diagnostic}");
            assert!(diagnostic.contains("project-hooks install"), "{diagnostic}");
        }
    }
}
