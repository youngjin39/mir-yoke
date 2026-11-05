//! Replay unmodified Yoke references; no interpreter or live Git repository.
use serde_json::{Value, json};
use std::{fs, path::Path, process::Command};
fn snapshot(root: &Path) -> Value {
    fn walk(root: &Path, dir: &Path, out: &mut serde_json::Map<String, Value>) {
        for entry in fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                out.insert(
                    format!("{}/", path.strip_prefix(root).unwrap().display()),
                    json!("directory"),
                );
                walk(root, &path, out);
            } else {
                out.insert(
                    path.strip_prefix(root).unwrap().to_str().unwrap().into(),
                    json!(fs::read(&path).unwrap()),
                );
            }
        }
    }
    let mut out = serde_json::Map::new();
    walk(root, root, &mut out);
    Value::Object(out)
}
fn replay(mode: &str) {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/w1/tdd-ledger.json")).unwrap();
    let mut count = 0;
    for record in fixture["records"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["mode"] == mode)
    {
        let dir = tempfile::tempdir().unwrap();
        // Records were captured under a non-symlinked root; macOS temp dirs are symlinked.
        let root_buf = fs::canonicalize(dir.path()).unwrap();
        let root = root_buf.as_path();
        let expand = |s: &str| s.replace("@PROJECT@", root.to_str().unwrap());
        for (name, body) in record["setup"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, expand(body.as_str().unwrap())).unwrap();
        }
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_project-hooks"));
        cmd.current_dir(root).env("CLAUDE_PROJECT_DIR", root);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let tools = tempfile::tempdir().unwrap();
            let git = tools.path().join("git");
            fs::write(
                &git,
                format!(
                    "#!/bin/sh\nprintf '%s' '{}'\n",
                    record["changed"].as_str().unwrap()
                ),
            )
            .unwrap();
            fs::set_permissions(&git, fs::Permissions::from_mode(0o755)).unwrap();
            cmd.env("PATH", tools.path());
            // Keep fake Git alive for the duration of the child.
            run(&mut cmd, record, mode, &expand, root);
        }
        #[cfg(not(unix))]
        {
            run(&mut cmd, record, mode, &expand, root);
        }
        count += 1;
    }
    assert_eq!(
        count,
        match mode {
            "prewrite" => 53,
            "precommit" => 27,
            "precommit-merge" => 13,
            "tdd-guard" => 150,
            _ => panic!("unknown fixture mode"),
        }
    );
    println!("{mode}: {count} frozen records");
}
fn run(cmd: &mut Command, r: &Value, mode: &str, expand: &impl Fn(&str) -> String, root: &Path) {
    if mode == "tdd-guard" {
        cmd.args(["tdd-guard", &expand(r["target"].as_str().unwrap())]);
    } else {
        cmd.arg("tdd-matrix");
        if let Some(args) = r["args"].as_array() {
            for arg in args {
                cmd.arg(expand(arg.as_str().unwrap()));
            }
        } else {
            cmd.args(
                [
                    mode,
                    root.to_str().unwrap(),
                    if mode == "precommit" {
                        "changed"
                    } else {
                        r["target"].as_str().unwrap()
                    },
                ]
                .map(expand),
            );
        }
    }
    let before = snapshot(root);
    let result = cmd.output().unwrap();
    assert_eq!(snapshot(root), before, "filesystem: {}", r["id"]);
    let normalize = |b: Vec<u8>| {
        String::from_utf8(b)
            .unwrap()
            .replace(root.to_str().unwrap(), "@PROJECT@")
    };
    let observed = json!({"exit":result.status.code(),"stdout":normalize(result.stdout),"stderr":normalize(result.stderr),"delta":{},"deleted":[]});
    if r["id"] == "guard-helper-missing" {
        // Retired branch: the Python helper is no longer consulted, so the
        // in-process ledger decides and the guard stays advisory.
        assert_eq!(observed["exit"], 0);
        assert!(
            !observed["stderr"]
                .as_str()
                .unwrap()
                .contains("Missing helper")
        );
        return;
    }
    if r["id"] == "guard-valid" {
        // Captured where the retired interpreter route was unavailable, so the
        // reference warned; the native ledger accepts the valid entry.
        assert_eq!(observed["exit"], 0);
        assert_eq!(observed["stderr"], "");
        return;
    }
    assert_eq!(observed, r["expected"], "{}", r["id"]);
}
#[test]
fn matrix_prewrite() {
    replay("prewrite");
}
#[test]
fn matrix_precommit_first_match() {
    replay("precommit");
}
#[test]
fn matrix_merge_unused() {
    replay("precommit-merge");
}
#[test]
fn guard_always_advisory() {
    replay("tdd-guard");
}
