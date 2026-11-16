use serde_json::Value;
use std::{fs, path::Path, process::Command};

fn test_git() -> std::path::PathBuf {
    std::env::split_paths(&std::env::var_os("PATH").expect("test PATH"))
        .map(|dir| dir.join(format!("git{}", std::env::consts::EXE_SUFFIX)))
        .find(|path| path.is_file())
        .expect("Git must be installed for E14")
        .canonicalize()
        .unwrap()
}

fn isolated_command(executable: &Path, root: &Path, git: &Path) -> Command {
    let mut command = Command::new(executable);
    command
        .env_clear()
        .env("HOME", root)
        .env("USERPROFILE", root)
        .env(
            "PATH",
            std::env::join_paths([git.parent().unwrap()]).unwrap(),
        )
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env(
            "GIT_CONFIG_GLOBAL",
            if cfg!(windows) { "NUL" } else { "/dev/null" },
        )
        .current_dir(root);
    // As in E2, retain only the Windows loader's OS locations.
    #[cfg(windows)]
    for name in ["SystemRoot", "WINDIR"] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    command
}

fn observe_root(text: &str, root: &str, windows: bool) -> String {
    if !windows {
        return text.replace(root, "{ROOT}");
    }
    let native = root.trim_start_matches(r"\\?\");
    let mut forms = vec![
        root.to_owned(),
        native.to_owned(),
        root.replace('\\', "/"),
        native.replace('\\', "/"),
    ];
    if native.contains('\\') {
        forms.push(format!(r"\\?\{native}"));
    }
    for mut form in forms.clone() {
        for _ in 0..2 {
            form = form.replace('\\', r"\\");
            forms.push(form.clone());
        }
    }
    forms.sort_by_key(|s| std::cmp::Reverse(s.len()));
    forms.dedup();
    forms.into_iter().fold(text.to_owned(), |text, spelling| {
        text.replace(&spelling, "{ROOT}")
    })
}

#[test]
fn isolated_git_environment() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let git = test_git();
    let mut command = isolated_command(&git, &root, &git);
    let env: std::collections::HashMap<_, _> = command.get_envs().collect();
    assert_eq!(
        env[std::ffi::OsStr::new("PATH")],
        Some(git.parent().unwrap().as_os_str())
    );
    assert_eq!(
        env[std::ffi::OsStr::new("USERPROFILE")],
        Some(root.as_os_str())
    );
    assert_eq!(
        env[std::ffi::OsStr::new("GIT_CONFIG_GLOBAL")],
        Some(std::ffi::OsStr::new(if cfg!(windows) {
            "NUL"
        } else {
            "/dev/null"
        }))
    );
    #[cfg(windows)]
    for name in ["SystemRoot", "WINDIR"] {
        assert_eq!(
            env.get(std::ffi::OsStr::new(name)).copied().flatten(),
            std::env::var_os(name).as_deref()
        );
    }
    assert!(command.args(["init", "-q"]).status().unwrap().success());
    assert!(
        isolated_command(Path::new("git"), &root, &git)
            .args(["status", "--porcelain"])
            .output()
            .unwrap()
            .status
            .success()
    );
}

#[test]
fn root_observation_preserves_other_path_bytes() {
    for (root, wire) in [
        (r"\\?\C:\scratch\case", "C:/scratch/case"),
        (r"C:\scratch\case", "C:/scratch/case"),
        (r"\\?\UNC\server\share\case", "UNC/server/share/case"),
    ] {
        let text = format!(r"{root}\evidence.txt | {wire}/manifest.json | C:\other\error.txt");
        assert_eq!(
            observe_root(&text, root, true),
            r"{ROOT}\evidence.txt | {ROOT}/manifest.json | C:\other\error.txt"
        );
    }
    assert_eq!(
        observe_root(
            "C:\\scratch\\case\\receipt | C:\\\\scratch\\\\case\\\\receipt | C:/scratch/case/report\r\nC:\\other\\file",
            r"\\?\C:\scratch\case",
            true
        ),
        "{ROOT}\\receipt | {ROOT}\\\\receipt | {ROOT}/report\r\nC:\\other\\file"
    );
    assert_eq!(
        observe_root(
            r"/tmp/case\literal /tmp/case/literal",
            r"/tmp/case\literal",
            false
        ),
        "{ROOT} /tmp/case/literal"
    );
}

#[test]
fn frozen_bootstrap_adoption_public() {
    let git = test_git();
    // Load only at runtime: a pending PC capture must not break Mac compilation.
    let records: Vec<Value> = if cfg!(windows) {
        serde_json::from_slice(
            &fs::read(
                Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/y-e14-windows.json"),
            )
            .expect("missing Windows E14 oracle: run generate_y_e14.py on Windows Python 3.12"),
        )
        .unwrap()
    } else {
        serde_json::from_str(include_str!("fixtures/y-e14.json")).unwrap()
    };
    assert_eq!(records.len(), 42);
    let mut failures = Vec::new();
    let temporary_name = regex::Regex::new(r"\.bootstrap-receipt\.json\.[^']+").unwrap();
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        for (name, body) in r["files"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            let body = body.as_str().unwrap();
            // Recreate the reference's Path.write_text inputs, including the
            // untouched old receipt whose physical bytes are also asserted.
            let body = if cfg!(windows) {
                body.replace('\n', "\r\n")
            } else {
                body.to_owned()
            };
            fs::write(path, body).unwrap();
        }
        let receipt = root.join(".mir/bootstrap-receipt.json");
        if let Some(sql) = r["sql"].as_str().filter(|s| !s.is_empty()) {
            rusqlite::Connection::open(root.join(".mir/memory.db"))
                .unwrap()
                .execute_batch(sql)
                .unwrap();
        }
        if r["mode"] == "memory-bad" {
            fs::write(root.join(".mir/memory.db"), b"bad database").unwrap();
        }
        if r["mode"] == "receipt-dir" {
            fs::remove_file(&receipt).unwrap();
            fs::create_dir(&receipt).unwrap();
        }
        let command = |executable: &Path| {
            let mut c = isolated_command(executable, &root, &git);
            c.env(
                "MIR_CAPABILITY_NATIVE_ARTIFACTS",
                if r["mode"] == "local" { "1" } else { "0" },
            );
            c
        };
        assert!(
            command(&git)
                .args(["init", "-q"])
                .status()
                .unwrap()
                .success()
        );
        if r["mode"] != "untracked" {
            assert!(command(&git).args(["add", "."]).status().unwrap().success());
        }
        let out = command(Path::new(env!("CARGO_BIN_EXE_mir")))
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_str().unwrap()),
            )
            .output()
            .unwrap();
        let actual = serde_json::json!({"exit":out.status.code(),
            "stdout":observe_root(&String::from_utf8(out.stdout).unwrap(), root.to_str().unwrap(), cfg!(windows)),
            "stderr":temporary_name.replace_all(&observe_root(&String::from_utf8(out.stderr).unwrap(), root.to_str().unwrap(), cfg!(windows)), ".bootstrap-receipt.json.<TEMP>"),
            // Python Path.read_text observes universal newlines; raw bytes are checked separately.
            "receipt":fs::read_to_string(&receipt).ok().map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))});
        if cfg!(windows) {
            assert!(
                r.get("receipt_physical_hex").is_some(),
                "recapture Windows E14 physical bytes"
            );
            let physical: Option<String> = fs::read(&receipt)
                .ok()
                .map(|bytes| bytes.iter().map(|b| format!("{b:02x}")).collect());
            if serde_json::json!(physical) != r["receipt_physical_hex"] {
                failures.push(format!(
                    "{} {} receipt physical bytes differ",
                    r["mode"], r["argv"]
                ));
            }
        }
        for field in ["exit", "stdout", "stderr", "receipt"] {
            if actual[field] != r[field] {
                failures.push(format!(
                    "{} {} {field}: {} != {}",
                    r["mode"], r["argv"], actual[field], r[field]
                ));
            }
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

#[cfg(unix)]
#[test]
fn receipt_parent_substitution_fails_closed() {
    use handoff_packet::mir_cli::bootstrap_adoption::write_receipt_with;
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let parent = root.join("project");
    let outside = root.join("outside");
    fs::create_dir(&parent).unwrap();
    fs::create_dir(&outside).unwrap();
    let receipt = parent.join("receipt.json");
    let sentinel = outside.join("receipt.json");
    fs::write(&sentinel, "preserve").unwrap();
    let result = write_receipt_with(&receipt, &serde_json::json!({"ready":true}), |source, _| {
        fs::copy(source, outside.join(source.file_name().unwrap()))?;
        fs::rename(&parent, root.join("saved"))?;
        std::os::unix::fs::symlink(&outside, &parent)
    });
    assert!(result.is_err());
    assert_eq!(fs::read_to_string(sentinel).unwrap(), "preserve");
    assert_eq!(fs::read_dir(outside).unwrap().count(), 2);
}

#[test]
fn public_receipt_physical_bytes_match_pinned_python() {
    use handoff_packet::mir_cli::bootstrap_adoption::write_receipt_with;
    let fixture = Path::new(env!("CARGO_MANIFEST_DIR")).join(if cfg!(windows) {
        "tests/fixtures/y-e14-receipt-bytes-windows.json"
    } else {
        "tests/fixtures/y-e14-receipt-bytes.json"
    });
    let record: Value = serde_json::from_slice(
        &fs::read(fixture)
            .expect("capture byte oracle on this platform with generate_y_e14.py --receipt-bytes"),
    )
    .unwrap();
    assert_eq!(
        record["platform"],
        std::env::consts::OS
            .replace("macos", "darwin")
            .replace("windows", "win32")
    );
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().canonicalize().unwrap().join("receipt.json");
    write_receipt_with(&path, &record["payload"], |_, _| Ok(())).unwrap();
    let bytes = fs::read(path).unwrap();
    let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    assert_eq!(hex, record["physical_hex"].as_str().unwrap());
    assert_eq!(
        String::from_utf8(bytes).unwrap().replace("\r\n", "\n"),
        record["logical"]
    );
}

#[cfg(unix)]
#[test]
fn receipt_leaf_substitution_preserves_outside_target() {
    use handoff_packet::mir_cli::bootstrap_adoption::write_receipt_with;
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let parent = root.join("project");
    fs::create_dir(&parent).unwrap();
    let outside = root.join("outside.json");
    fs::write(&outside, b"preserve").unwrap();
    let path = parent.join("receipt.json");
    // A leaf link is atomically replaced; its target must never be written.
    write_receipt_with(
        &path,
        &serde_json::json!({"ready":true}),
        |_, destination| std::os::unix::fs::symlink(&outside, destination),
    )
    .unwrap();
    assert_eq!(fs::read(outside).unwrap(), b"preserve");
    assert!(!path.is_symlink());
    assert_eq!(fs::read_dir(parent).unwrap().count(), 1);
}

#[test]
fn nested_repr_json_root_observation() {
    for root in [
        r"C:\scratch\case",
        r"\\?\C:\scratch\case",
        r"\\?\UNC\server\share\case",
    ] {
        let mut spelling = root.to_owned();
        for _ in 0..3 {
            let text = format!("{spelling}\\suffix | C:\\other\\file\r\n");
            assert_eq!(
                observe_root(&text, root, true),
                "{ROOT}\\suffix | C:\\other\\file\r\n"
            );
            spelling = spelling.replace('\\', r"\\");
        }
    }
}

// Public-command oracle: Python 5f8f69f, archived in this repository. Captured
// with s14-symlink-3/probe.py (-I -B -X utf8, synthetic HOME, network forbidden).
#[cfg(unix)]
#[test]
fn public_adoption_linked_mir_matches_python() {
    fn unhex(value: &Value) -> Vec<u8> {
        value
            .as_str()
            .unwrap()
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect()
    }
    fn snapshot(root: &Path, directory: &Path, output: &mut serde_json::Map<String, Value>) {
        for entry in fs::read_dir(directory).unwrap() {
            let path = entry.unwrap().path();
            if path.file_name().unwrap() == ".git" || path.is_symlink() {
                continue;
            }
            if path.is_dir() {
                snapshot(root, &path, output);
            } else {
                let hex: String = fs::read(&path)
                    .unwrap()
                    .iter()
                    .map(|b| format!("{b:02x}"))
                    .collect();
                output.insert(
                    path.strip_prefix(root).unwrap().to_str().unwrap().into(),
                    Value::String(hex),
                );
            }
        }
    }
    let fixture: Value = serde_json::from_str(include_str!("fixtures/s14-symlink.json")).unwrap();
    assert_eq!(
        fixture["reference_pin"],
        "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"
    );
    let git = test_git();
    for record in fixture["records"].as_array().unwrap() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        for (name, body) in record["files_before"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, unhex(body)).unwrap();
        }
        let project = root.join("project");
        std::os::unix::fs::symlink("../sibling", project.join(".mir")).unwrap();
        for args in [vec!["init", "-q"], vec!["add", "."]] {
            assert!(
                isolated_command(&git, &project, &git)
                    .args(args)
                    .status()
                    .unwrap()
                    .success()
            );
        }
        let out = isolated_command(Path::new(env!("CARGO_BIN_EXE_mir")), &project, &git)
            .env("MIR_CAPABILITY_NATIVE_ARTIFACTS", "0")
            .args([
                "bootstrap-adoption",
                "--project-root",
                project.to_str().unwrap(),
                "--apply",
                "--json",
            ])
            .output()
            .unwrap();
        assert_eq!(
            out.status.code(),
            record["exit"].as_i64().map(|n| n as i32),
            "{}",
            record["case"]
        );
        assert_eq!(out.stdout, unhex(&record["stdout_hex"]));
        assert_eq!(out.stderr, unhex(&record["stderr_hex"]));
        assert_eq!(
            fs::read_link(project.join(".mir")).unwrap(),
            Path::new("../sibling")
        );
        let mut after = serde_json::Map::new();
        snapshot(&root, &project, &mut after);
        snapshot(&root, &root.join("sibling"), &mut after);
        assert_eq!(Value::Object(after), record["files_after"]);
    }
}
