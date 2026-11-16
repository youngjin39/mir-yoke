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
    // Replace the canonical native spelling and bootstrap_adoption::wire's
    // report spelling only. Error suffixes, other paths and CRLF stay literal.
    let observed = text.replace(root, "{ROOT}");
    if windows {
        observed.replace(
            &root.trim_start_matches(r"\\?\").replace('\\', "/"),
            "{ROOT}",
        )
    } else {
        observed
    }
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
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e14.json")).unwrap();
    let mut failures = Vec::new();
    let temporary_name = regex::Regex::new(r"\.bootstrap-receipt\.json\.[^']+").unwrap();
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        for (name, body) in r["files"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, body.as_str().unwrap()).unwrap();
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
            "receipt":fs::read_to_string(&receipt).ok()});
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
