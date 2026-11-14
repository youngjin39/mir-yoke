use serde_json::Value;
use std::{fs, process::Command};

fn check_family(family: &str) {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e2.json")).unwrap();
    for r in records.iter().filter(|r| r["argv"][0] == family) {
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        let bin = root.join("bin");
        fs::create_dir(&bin).unwrap();
        let mir = bin.join(format!("mir{}", std::env::consts::EXE_SUFFIX));
        fs::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
        // Installed console binds the interpreter beside its own executable.
        let python = std::env::var_os("Y_E2_PYTHON").unwrap_or_else(|| {
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../.venv")
                .join(if cfg!(windows) {
                    "Scripts/python.exe"
                } else {
                    "bin/python"
                })
                .into_os_string()
        });
        #[cfg(unix)]
        std::os::unix::fs::symlink(&python, bin.join("python")).unwrap();
        #[cfg(windows)]
        fs::copy(&python, bin.join("python.exe")).unwrap();
        fs::create_dir(root.join("config")).unwrap();
        fs::write(
            root.join("config/model-routing.lock.json"),
            r#"{"policy": {}}"#,
        )
        .unwrap();
        fs::create_dir(root.join("runtime")).unwrap();
        fs::write(root.join("runtime/data"), "payload\n").unwrap();
        fs::write(root.join("helper.py"), "print('script extension')\n").unwrap();
        if r["setup"] == true {
            if family == "runtime-manifest" {
                let body = records.iter().find(|r| r["manifest"].is_string()).unwrap();
                fs::write(
                    root.join("runtime/manifest.json"),
                    body["manifest"].as_str().unwrap(),
                )
                .unwrap();
            } else {
                let c =
                    handoff_packet::mir_core::memory::store::connect(&root.join("memory.db"), None)
                        .unwrap();
                handoff_packet::mir_core::memory::store::apply_migrations(&c.conn).unwrap();
            }
        }
        let output = Command::new(&mir)
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|a| a.as_str().unwrap()),
            )
            .env_clear()
            .env("HOME", &root)
            .env("PYTHONIOENCODING", "utf-8")
            .current_dir(&root)
            .output()
            .unwrap();
        let normalize = |bytes: Vec<u8>| {
            String::from_utf8(bytes)
                .unwrap()
                .replace(root.to_str().unwrap(), "@ROOT@")
        };
        assert_eq!(
            output.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{}",
            r["argv"]
        );
        assert_eq!(normalize(output.stdout), r["stdout"], "{}", r["argv"]);
        assert_eq!(normalize(output.stderr), r["stderr"], "{}", r["argv"]);
        if family == "migrate" && r["exit"] == 0 && r["argv"][1] == "up" {
            let c = rusqlite::Connection::open(root.join("memory.db")).unwrap();
            assert_eq!(
                c.query_row("SELECT MAX(version) FROM schema_migrations", [], |r| r
                    .get::<_, String>(
                    0
                ))
                .unwrap(),
                "018"
            );
        }
        if let Some(body) = r["manifest"].as_str() {
            assert_eq!(
                fs::read_to_string(root.join("runtime/manifest.json")).unwrap(),
                body
            );
        }
    }
}
#[test]
fn policy() {
    check_family("policy");
}
#[test]
fn runtime_manifest() {
    check_family("runtime-manifest");
}
#[test]
fn run_python() {
    check_family("run-python");
}
#[test]
fn migrate() {
    check_family("migrate");
}

#[test]
fn missing_managed_interpreter_refuses() {
    let temp = tempfile::tempdir().unwrap();
    let mir = temp
        .path()
        .join(format!("mir{}", std::env::consts::EXE_SUFFIX));
    fs::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
    let out = Command::new(mir)
        .args(["run-python", "--help"])
        .env_clear()
        .env("HOME", temp.path())
        .current_dir(temp.path())
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(127));
    assert!(out.stdout.is_empty());
    assert_eq!(out.stderr, b"[mir hook] external Mir Python unavailable; run setup.sh first (inside WSL on Windows hosts)\n");
}
