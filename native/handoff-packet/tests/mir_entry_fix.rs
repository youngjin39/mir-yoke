#![cfg(unix)]
use serde_json::Value;
use std::{
    ffi::OsString,
    fs,
    os::unix::{ffi::OsStringExt, process::CommandExt},
    process::{Command, Stdio},
};
fn unhex(v: &Value) -> Vec<u8> {
    v.as_str()
        .unwrap()
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|s| u8::from_str_radix(std::str::from_utf8(s).unwrap(), 16).unwrap())
        .collect()
}
fn check(indices: &[usize]) {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e1-fix.json")).unwrap();
    for &index in indices {
        let r = &records[index];
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        let cwd = root.join("cwd");
        fs::create_dir_all(cwd.join("tasks")).unwrap();
        fs::write(cwd.join("tasks/plan.md"), r["plan"].as_str().unwrap()).unwrap();
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_mir"));
        cmd.args(
            r["argv"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| OsString::from_vec(unhex(v))),
        )
        .env_clear()
        .env("HOME", &root)
        .env("PYTHONIOENCODING", r["encoding"].as_str().unwrap())
        .current_dir(&cwd)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
        if r["mode"] == "deleted" {
            // Only synthetic child cwd is removed, after the OS chdir and before exec.
            unsafe {
                let deleted = cwd.clone();
                cmd.pre_exec(move || fs::remove_dir_all(&deleted));
            }
        }
        if r["mode"] == "closed" || r["mode"] == "write-closed" || r["mode"] == "large-closed" {
            let (reader, writer) = std::io::pipe().unwrap();
            drop(reader);
            cmd.stdout(Stdio::from(writer));
        }
        if r["mode"] == "badfd" {
            cmd.stdout(fs::File::open(cwd.join("tasks/plan.md")).unwrap());
        }
        let out = cmd.output().unwrap();
        assert_eq!(
            out.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "exit record {index}"
        );
        assert_eq!(out.stdout, unhex(&r["stdout"]), "stdout record {index}");
        assert_eq!(out.stderr, unhex(&r["stderr"]), "stderr record {index}");
        if let Some(after) = r["after"].as_str() {
            assert_eq!(
                fs::read_to_string(cwd.join("tasks/plan.md")).unwrap(),
                after,
                "effect record {index}"
            );
        }
    }
}
#[test]
fn loop_argparse() {
    check(&(0..8).collect::<Vec<_>>());
}
#[test]
fn valid_codecs() {
    check(&[8, 16]);
}
#[test]
fn valid_codecs_namereplace() {
    check(&[9, 15]);
}
#[test]
fn console_bom() {
    check(&[10, 11]);
}
#[test]
fn closed_stdout() {
    check(&[12, 17, 18, 19]);
}
#[test]
fn deleted_cwd_help() {
    check(&[13]);
}
#[test]
fn invalid_codec_startup() {
    check(&[14]);
}
