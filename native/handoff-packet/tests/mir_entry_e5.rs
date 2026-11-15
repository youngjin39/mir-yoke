use serde_json::Value;
use std::{fs, process::Command};

#[path = "support/unify2_s6.rs"]
mod platform;

#[test]
fn context_sync_console() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e5.json")).unwrap();
    for (i, r) in records.iter().enumerate().take(25) {
        check_record(i, r);
    }
}

fn check_record(i: usize, r: &Value) {
    let temp = tempfile::tempdir().unwrap();
    let root = fs::canonicalize(temp.path()).unwrap();
    fs::create_dir(root.join("notes")).unwrap();
    fs::write(root.join("notes/a.md"), "Synthetic archive document.\n").unwrap();
    fs::write(root.join("harness_a.toml"), r["config"].as_str().unwrap()).unwrap();
    if r["seed"] == true {
        let c = handoff_packet::mir_core::memory::store::connect(&root.join("memory.db"), None)
            .unwrap();
        handoff_packet::mir_core::memory::store::apply_migrations(&c.conn).unwrap();
    }
    if i == 22 {
        fs::write(root.join("memory.db"), "not a database").unwrap();
    }
    if i == 23 {
        fs::write(root.join("memory.db"), "").unwrap();
    }
    let out = Command::new(env!("CARGO_BIN_EXE_mir"))
        .args(
            r["argv"]
                .as_array()
                .unwrap()
                .iter()
                .map(|s| s.as_str().unwrap()),
        )
        .env_clear()
        .env("HOME", &root)
        .env("PYTHONIOENCODING", "utf-8")
        .current_dir(&root)
        .output()
        .unwrap();
    assert_eq!(
        out.status.code(),
        Some(r["exit"].as_i64().unwrap() as i32),
        "record {i}"
    );
    let normalize = |bytes| {
        String::from_utf8(bytes)
            .unwrap()
            .replace(root.to_str().unwrap(), "@ROOT@")
    };
    assert_eq!(
        normalize(out.stdout),
        platform::expected_text(r["stdout"].as_str().unwrap(), cfg!(windows)),
        "stdout {i}"
    );
    assert_eq!(
        normalize(out.stderr),
        platform::expected_text(r["stderr"].as_str().unwrap(), cfg!(windows)),
        "stderr {i}"
    );
    if [14, 16].contains(&i) {
        let c = rusqlite::Connection::open(root.join("memory.db")).unwrap();
        assert_eq!(
            c.query_row("SELECT count(*) FROM external_documents", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            1
        );
    }
}

#[test]
fn context_sync_db_spelling() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e5.json")).unwrap();
    check_record(25, &records[25]);
}

#[test]
fn context_sync_option_value() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e5.json")).unwrap();
    check_record(26, &records[26]);
}

#[test]
fn context_sync_top_help_order() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e5.json")).unwrap();
    check_record(27, &records[27]);
}

#[test]
fn context_sync_top_unknown_order() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e5.json")).unwrap();
    check_record(28, &records[28]);
}

#[test]
fn context_sync_short_help_explicit() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e5.json")).unwrap();
    check_record(29, &records[29]);
}
