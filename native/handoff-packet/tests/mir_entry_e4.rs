use serde_json::Value;
use std::process::Command;

#[path = "support/unify2_s6.rs"]
mod platform;

fn unhex(value: &Value) -> Vec<u8> {
    value
        .as_str()
        .unwrap()
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|s| u8::from_str_radix(std::str::from_utf8(s).unwrap(), 16).unwrap())
        .collect()
}

#[test]
fn all_non_text_startup_diagnostics() {
    let records: Value = serde_json::from_str(include_str!("fixtures/y-e4.json")).unwrap();
    let table: Value = serde_json::from_str(include_str!("../src/console-codecs.json")).unwrap();
    let cases = records["non_text"].as_array().unwrap();
    // Every non-text alias in the pinned table has a complete process record.
    for (alias, name) in table["aliases"].as_object().unwrap() {
        if table["non_text"].as_array().unwrap().contains(name) {
            assert!(
                cases.iter().any(|r| r["alias"] == *alias),
                "missing {alias}"
            );
        }
    }
    let temp = tempfile::tempdir().unwrap();
    for r in cases {
        let out = Command::new(env!("CARGO_BIN_EXE_mir"))
            .arg("--help")
            .env_clear()
            .env("HOME", temp.path())
            .env("PYTHONIOENCODING", r["alias"].as_str().unwrap())
            .current_dir(temp.path())
            .output()
            .unwrap();
        assert_eq!(
            out.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{r}"
        );
        assert_eq!(out.stdout, unhex(&r["stdout"]), "{r}");
        assert_eq!(out.stderr, unhex(&r["stderr"]), "alias {}", r["alias"]);
    }
}

#[test]
fn stdout_dup_injection_is_absent_from_console_binary() {
    let r: Value = serde_json::from_str(include_str!("fixtures/y-e4.json")).unwrap();
    let temp = tempfile::tempdir().unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_mir"))
        .arg("--help")
        .env_clear()
        .env("HOME", temp.path())
        .env("MIR_TEST_STDOUT_DUP_EMFILE", "1")
        .current_dir(temp.path())
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(0));
    let text = String::from_utf8(unhex(&r["no_dup_console"]["stdout"])).unwrap();
    assert_eq!(
        out.stdout,
        platform::expected_text(&text, cfg!(windows)).as_bytes()
    );
    assert!(out.stderr.is_empty());
}
