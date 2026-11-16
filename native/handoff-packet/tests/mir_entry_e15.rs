use serde_json::Value;
use std::{fs, process::Command};

fn scratch() -> tempfile::TempDir {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/Y-E15");
    fs::create_dir_all(&path).unwrap();
    tempfile::tempdir_in(path).unwrap()
}

#[test]
fn frozen_bootstrap_process_entry() {
    let text = if cfg!(windows) {
        fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/y-e15-windows.json"
        ))
        .expect("capture on Windows first: generate_y_e15.py")
    } else {
        include_str!("fixtures/y-e15.json").to_owned()
    };
    let records: Vec<Value> = serde_json::from_str(&text).unwrap();
    for r in records.iter().filter(|r| r["mode"] == "public") {
        let temp = scratch();
        let root = temp.path().canonicalize().unwrap();
        for (name, body) in r["files"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, body.as_str().unwrap()).unwrap();
        }
        let mut command = Command::new(env!("CARGO_BIN_EXE_mir"));
        command
            .arg("bootstrap")
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_str().unwrap()),
            )
            .current_dir(&root)
            .env_clear()
            .env("HOME", &root)
            .env("USERPROFILE", &root)
            .env("PATH", "/usr/bin:/bin")
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env(
                "GIT_CONFIG_GLOBAL",
                if cfg!(windows) { "NUL" } else { "/dev/null" },
            );
        for key in ["SystemRoot", "WINDIR"] {
            if let Some(value) = std::env::var_os(key) {
                command.env(key, value);
            }
        }
        let out = command.output().unwrap();
        assert_eq!(
            out.status.code(),
            r["exit"].as_i64().map(|v| v as i32),
            "{}",
            r["argv"]
        );
        assert_eq!(
            String::from_utf8(out.stdout)
                .unwrap()
                .replace(root.to_str().unwrap(), "{ROOT}"),
            r["stdout"]
        );
        assert_eq!(
            String::from_utf8(out.stderr)
                .unwrap()
                .replace(root.to_str().unwrap(), "{ROOT}"),
            r["stderr"]
        );
        assert!(!root.join(".mir/memory.db").exists());
        assert!(!root.join(".mir/bootstrap-receipt.json").exists());
    }
}

#[cfg(unix)]
#[test]
fn production_host_process_boundaries() {
    let temp = scratch();
    let root = temp.path().canonicalize().unwrap();
    let result = Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "host_child", "--nocapture"])
        .current_dir(&root)
        .env_clear()
        .env("HOME", &root)
        .env("PATH", "/usr/bin:/bin")
        .env("Y_E15_CHILD", "1")
        .env("PYTHONPATH", "poison")
        .env("VIRTUAL_ENV", "poison")
        .env("UV_PROJECT_ENVIRONMENT", "poison")
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}{}",
        String::from_utf8_lossy(&result.stdout),
        String::from_utf8_lossy(&result.stderr)
    );
}

#[cfg(unix)]
#[test]
fn host_child() {
    use handoff_packet::mir_cli::bootstrap::{CommandRequest, Host, ProductionHost};
    use std::{collections::BTreeMap, os::unix::fs::PermissionsExt, path::Path};
    if std::env::var("Y_E15_CHILD").is_err() {
        return;
    }
    assert!(std::env::var_os("Y_E15_ENV_POISON").is_none());
    let root = std::env::current_dir().unwrap();
    let mut host = ProductionHost::default();
    assert_eq!(
        host.expanduser(Path::new("~/future")).unwrap(),
        root.join("future")
    );
    assert_eq!(host.env("HOME").unwrap(), root.to_str().unwrap());
    assert!(host.which("sh").is_some());
    assert!(host.writable(&root));
    assert!(host.device(&root).is_ok());
    assert_eq!(
        host.resolve(Path::new("absent/../future")).unwrap(),
        root.join("future")
    );
    std::os::unix::fs::symlink("future", root.join("dangling")).unwrap();
    assert_eq!(
        host.resolve(&root.join("dangling")).unwrap(),
        root.join("future")
    );
    std::os::unix::fs::symlink("loop", root.join("loop")).unwrap();
    assert_eq!(
        host.resolve(&root.join("loop")).err().unwrap().class,
        "RuntimeError"
    );
    let fake = root.join("fake");
    fs::write(&fake, "#!/bin/sh\necho $$ > child.pid\n[ -z \"$PYTHONPATH$VIRTUAL_ENV$UV_PROJECT_ENVIRONMENT\" ] || exit 9\n[ \"$HOME\" = \"$PWD\" ] || exit 8\nprintf '%s' '{\"ready\":true,\"changed_paths\":[]}'\n").unwrap();
    fs::set_permissions(&fake, fs::Permissions::from_mode(0o755)).unwrap();
    let mut request = CommandRequest {
        argv: vec![fake.to_str().unwrap().into()],
        cwd: root.clone(),
        environment: BTreeMap::new(),
        stdin_null: true,
        capture_output: true,
        text: true,
        check: false,
    };
    assert_eq!(host.run(&request).unwrap().returncode, 9);
    let clean = host.slim_run_clean(&request).unwrap();
    assert_eq!(clean.returncode, 0);
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e15.json")).unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(records[5]["stdout"].as_str().unwrap()).unwrap(),
        serde_json::json!([true, "ready"])
    );
    assert_eq!(
        serde_json::from_str::<Value>(records[6]["stdout"].as_str().unwrap()).unwrap(),
        serde_json::json!([
            host.slim_process_alive(std::process::id() as i64).unwrap(),
            false
        ])
    );
    assert_eq!(clean.stdout, b"{\"ready\":true,\"changed_paths\":[]}");
    let pid = fs::read_to_string(root.join("child.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    assert!(
        !host.slim_process_alive(pid).unwrap(),
        "child must be reaped"
    );
    assert!(host.slim_process_alive(std::process::id() as i64).unwrap());
    request.argv = vec!["/bin/sh".into(), "-c".into(), "kill -TERM $$".into()];
    assert_eq!(host.run(&request).unwrap().returncode, -15);
    request.argv = vec!["/bin/sh".into(), "-c".into(), "printf '\\377'".into()];
    assert_eq!(
        host.run(&request).err().unwrap().class,
        "UnicodeDecodeError"
    );
    request.argv = vec!["bad\0name".into()];
    assert_eq!(host.run(&request).err().unwrap().class, "ValueError");
    request.argv.clear();
    assert_eq!(host.run(&request).err().unwrap().class, "IndexError");
    assert_eq!(
        host.slim_process_alive(i64::MAX).err().unwrap().class,
        "OverflowError"
    );
    request.argv = vec![root.join("missing").to_str().unwrap().into()];
    assert_eq!(host.run(&request).err().unwrap().class, "FileNotFoundError");
    request.argv = vec![fake.to_str().unwrap().into()];
    fs::set_permissions(&fake, fs::Permissions::from_mode(0o644)).unwrap();
    assert_eq!(host.run(&request).err().unwrap().class, "PermissionError");
    fs::set_permissions(&fake, fs::Permissions::from_mode(0o755)).unwrap();
    let denied = root.join("denied");
    fs::create_dir(&denied).unwrap();
    fs::set_permissions(&denied, fs::Permissions::from_mode(0o0)).unwrap();
    request.argv = vec![fake.to_str().unwrap().into()];
    request.cwd = denied.clone();
    let error = host.slim_run_clean(&request).err().unwrap();
    fs::set_permissions(&denied, fs::Permissions::from_mode(0o700)).unwrap();
    assert_eq!(
        format!("{}: {}\n", error.class, error.message).replace(root.to_str().unwrap(), "{ROOT}"),
        records[7]["stderr"]
    );
    request.cwd = fake;
    assert_eq!(
        host.run(&request).err().unwrap().class,
        "NotADirectoryError"
    );
}
