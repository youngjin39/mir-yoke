#![cfg(unix)]
#[path = "support/executable.rs"]
mod executable;
use serde_json::Value;
use std::{
    ffi::OsString,
    fs,
    os::unix::{ffi::OsStringExt, process::CommandExt},
    process::Command,
};

fn bytes(value: &Value) -> Vec<u8> {
    value
        .as_str()
        .unwrap()
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|v| u8::from_str_radix(std::str::from_utf8(v).unwrap(), 16).unwrap())
        .collect()
}
fn check(indices: &[usize]) {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e2-fix.json")).unwrap();
    for &i in indices {
        let r = &records[i];
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        let cwd = root.join("cwd");
        fs::create_dir(&cwd).unwrap();
        fs::write(cwd.join("helper.py"), "print('script extension')\n").unwrap();
        let bin = root.join("bin");
        fs::create_dir(&bin).unwrap();
        let mir = bin.join("mir");
        // Reuse the built executable for deleted cwd so parallel forks cannot
        // inherit a copy's open writer for the executable about to be spawned.
        let executable = if r["deleted"] == true {
            std::path::PathBuf::from(env!("CARGO_BIN_EXE_mir"))
        } else {
            executable::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
            mir
        };
        let python =
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.venv/bin/python");
        std::os::unix::fs::symlink(python, bin.join("python")).unwrap();
        let mut cmd = Command::new(executable);
        cmd.args(
            r["argv"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| OsString::from_vec(bytes(v))),
        )
        .env_clear()
        .env("HOME", &root)
        .env("PYTHONIOENCODING", "utf-8")
        .current_dir(&cwd);
        if r["deleted"] == true {
            // Remove only this synthetic cwd after chdir, before the native exec.
            unsafe {
                cmd.pre_exec(move || fs::remove_dir_all(&cwd));
            }
        }
        let out = cmd.output().unwrap();
        assert_eq!(
            out.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "exit record {i}"
        );
        assert_eq!(out.stdout, bytes(&r["stdout"]), "stdout record {i}");
        assert_eq!(out.stderr, bytes(&r["stderr"]), "stderr record {i}");
        let cwd = root.join("cwd");
        let raw_db = cwd.join(OsString::from_vec(b"raw-\xff.db".to_vec()));
        assert_eq!(
            raw_db.is_file(),
            r["raw_db"].as_bool().unwrap(),
            "raw DB record {i}"
        );
        assert!(!cwd.join("raw-�.db").exists(), "lossy DB record {i}");
        assert!(
            !cwd.join("raw-\\udcff.db").exists(),
            "escaped DB record {i}"
        );
        assert!(!cwd.join(".mir").exists(), "no default DB record {i}");
    }
}
#[test]
fn os_argv() {
    check(&[0, 1, 2, 3]);
}
#[test]
fn migrate_argparse() {
    check(&(4..15).collect::<Vec<_>>());
    check(&[20, 21]);
}
#[test]
fn malformed_db() {
    check(&[15]);
}
#[test]
fn original_argv() {
    check(&[16]);
}
#[test]
fn cwd_only_when_needed() {
    check(&[17, 18, 19]);
}

#[test]
fn migrate_space_value() {
    check(&[22, 23, 24]);
}
#[test]
fn migrate_explicit_top_help() {
    check(&[25, 26]);
}
