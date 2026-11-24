//! Exact shell-reference replay, with no Python or hook helpers in the native fixture.
#![cfg(unix)]
#[path = "../src/digest.rs"]
mod digest;
#[path = "support/replay.rs"]
#[allow(dead_code)]
mod frozen;
use serde_json::{Value, json};
use std::collections::BTreeMap;

fn cases() -> Vec<Value> {
    let data: Value =
        serde_json::from_str(include_str!("fixtures/w1/pre-commit-verification.json")).unwrap();
    data["records"].as_array().unwrap().clone()
}

fn normalized(name: &str, mut value: Value) -> Value {
    if name == "tasks/audit/suggest_bypass.jsonl" {
        let bytes = frozen::decode(&value["base64"]);
        let text = std::str::from_utf8(&bytes).unwrap();
        assert!(text.ends_with('\n'));
        assert_eq!(text.lines().count(), 1);
        let row: Value = serde_json::from_str(text).unwrap();
        assert_eq!(row.as_object().unwrap().len(), 3);
        assert!(
            regex::Regex::new(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:\+00:00|Z)$")
                .unwrap()
                .is_match(row["ts"].as_str().unwrap())
        );
        // Replace only the timestamp; preserve key order, spacing and all other bytes.
        let stable = text.replacen(row["ts"].as_str().unwrap(), "@UTC@", 1);
        // Compare decoded bytes below, so encoding is unnecessary.
        value["normalized"] = stable.into();
        value.as_object_mut().unwrap().remove("base64");
    }
    value
}

fn expected_delta(record: &Value) -> BTreeMap<String, Value> {
    record["expected"]["delta"]
        .as_object()
        .unwrap()
        .iter()
        .map(|(name, value)| {
            let mut value = value.clone();
            if name == "tasks/audit/suggest_bypass.jsonl" {
                let text = String::from_utf8(frozen::decode(&value["base64"])).unwrap();
                value["normalized"] = text.into();
                value.as_object_mut().unwrap().remove("base64");
            }
            (name.clone(), value)
        })
        .collect()
}

fn assert_native(record: &Value) {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    let mut command = frozen::prepare(root);
    let mut setup = record["setup"].clone();
    // Legacy captures carried a Python trampoline. Never install it for native replay.
    setup.as_object_mut().unwrap().retain(|name, _| {
        !name.starts_with("project/.venv/") && !name.starts_with("project/.claude/")
    });
    frozen::install(&setup, root);
    for (key, value) in record["env"].as_object().unwrap() {
        command.env(
            key,
            String::from_utf8(frozen::transform(
                value.as_str().unwrap().as_bytes().to_vec(),
                root,
                true,
            ))
            .unwrap(),
        );
    }
    // Login profiles may use run-parts even with this restricted PATH.
    // Do not execute ambient profile snippets in the isolated fixture.
    use std::os::unix::fs::PermissionsExt;
    let startup = root.join("tools/run-parts");
    std::fs::write(&startup, "#!/bin/sh\nexit 0\n").unwrap();
    std::fs::set_permissions(&startup, std::fs::Permissions::from_mode(0o755)).unwrap();
    std::fs::write(
        root.join("home/.bash_profile"),
        format!("export PATH='{}'\n", root.join("tools").display()),
    )
    .unwrap();
    let before = frozen::snapshot(&root.join("project"));
    let result = command.arg("pre-commit-verification").output().unwrap();
    let after = frozen::snapshot(&root.join("project"));
    let delta: BTreeMap<_, _> = after
        .iter()
        .filter(|(name, entry)| before.get(*name) != Some(*entry))
        .map(|(name, value)| (name.clone(), normalized(name, value.clone())))
        .collect();
    let deleted: Vec<_> = before
        .keys()
        .filter(|name| !after.contains_key(*name))
        .cloned()
        .collect();
    let label = record["id"].as_str().unwrap();
    assert_eq!(
        result.status.code(),
        record["expected"]["exit"].as_i64().map(|n| n as i32),
        "{label} exit"
    );
    assert_eq!(
        frozen::transform(result.stdout, root, false),
        frozen::decode(&record["expected"]["stdout"]),
        "{label} stdout"
    );
    assert_eq!(
        frozen::transform(result.stderr, root, false),
        frozen::decode(&record["expected"]["stderr"]),
        "{label} stderr"
    );
    assert_eq!(delta, expected_delta(record), "{label} full project delta");
    assert_eq!(
        json!(deleted),
        record["expected"]["deleted"],
        "{label} deleted paths"
    );
}

#[test]
fn original_precommit_envelopes_match_without_python_or_helpers() {
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/w1/records.json")).unwrap();
    let selected: Vec<_> = records
        .iter()
        .filter(|r| r["family"] == ".claude/hooks/pre-commit-verification.sh")
        .collect();
    assert_eq!(selected.len(), 10);
    for record in selected {
        assert_native(record);
    }
}

#[test]
fn staged_paths_manifest_gates_ordered_steps_and_tdd_match_shell() {
    let records = cases();
    assert_eq!(records.len(), 40);
    let selected: Vec<_> = records
        .iter()
        .filter(|r| r["retired_helper_absence"] != true)
        .collect();
    assert_eq!(selected.len(), 39);
    for record in selected {
        assert_native(record);
    }
}

#[test]
fn retired_missing_python_helper_uses_native_ledger_validation() {
    let records = cases();
    let selected: Vec<_> = records
        .iter()
        .filter(|r| r["retired_helper_absence"] == true)
        .collect();
    assert_eq!(selected.len(), 1);
    let missing_ledger = records
        .iter()
        .find(|r| r["case"] == "ledger-missing")
        .unwrap();
    for record in selected {
        assert!(!record["retirement_reason"].as_str().unwrap().is_empty());
        assert_eq!(record["expected"]["exit"], 2);
        assert_eq!(frozen::decode(&record["expected"]["stderr"]), b"[PreCommitVerification BLOCK] Missing helper: @TMP@/project/.claude/hooks/tdd-matrix-guard.py\n");
        let mut native = record.clone();
        native["expected"] = missing_ledger["expected"].clone();
        assert_native(&native);
    }
}

#[test]
fn captured_precommit_reference_sources_remain_pinned() {
    let data: Value =
        serde_json::from_str(include_str!("fixtures/w1/pre-commit-verification.json")).unwrap();
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    for (path, expected) in data["sources"].as_object().unwrap() {
        assert_eq!(
            digest::sha256(&std::fs::read(repo.join(path)).unwrap()),
            expected.as_str().unwrap(),
            "{path}"
        );
    }
}
