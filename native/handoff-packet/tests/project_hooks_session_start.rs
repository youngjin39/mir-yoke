//! SessionStart reference envelopes, captured before replacing the Python renderer.
#![cfg(unix)]
#[path = "../src/digest.rs"]
mod digest;
#[path = "support/replay.rs"]
#[allow(dead_code)]
mod frozen;
use serde_json::Value;

fn records() -> Vec<Value> {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/w1/session-start.json")).unwrap();
    fixture["records"].as_array().unwrap().clone()
}

fn assert_native(record: &Value) {
    let root = tempfile::tempdir().unwrap();
    let mut command = frozen::prepare(root.path());
    frozen::install(&record["setup"], root.path());
    let before = frozen::snapshot(&root.path().join("project"));
    let output = command.arg("session-start").output().unwrap();
    assert_eq!(
        output.status.code(),
        record["expected"]["exit"].as_i64().map(|n| n as i32),
        "{} status",
        record["case"]
    );
    assert_eq!(
        frozen::transform(output.stdout, root.path(), false),
        frozen::decode(&record["expected"]["stdout"]),
        "{} stdout",
        record["case"]
    );
    assert_eq!(
        frozen::transform(output.stderr, root.path(), false),
        frozen::decode(&record["expected"]["stderr"]),
        "{} stderr",
        record["case"]
    );
    assert_eq!(
        frozen::snapshot(&root.path().join("project")),
        before,
        "{} must not mutate any project file, directory, mode or symlink",
        record["case"]
    );
}

#[test]
fn missing_receipt_reuses_frozen_w1_reference_without_mutation() {
    let original: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/w1/records.json")).unwrap();
    let missing = original
        .iter()
        .find(|r| r["family"] == ".claude/hooks/session-start.sh" && r["case"] == "missing")
        .unwrap();
    assert_native(missing);
}

#[test]
fn bootstrap_states_and_builder_presence_match_reference_without_mutation() {
    let cases = records();
    let selected: Vec<_> = cases
        .iter()
        .filter(|r| {
            r["case"].as_str().unwrap().starts_with("bootstrap-") || r["case"] == "builder-absent"
        })
        .collect();
    assert_eq!(selected.len(), 11);
    for record in selected {
        assert_native(record);
    }
}

#[test]
fn profiles_preserve_python_value_rendering_without_mutation() {
    let cases = records();
    let selected: Vec<_> = cases
        .iter()
        .filter(|r| r["case"].as_str().unwrap().starts_with("profile-"))
        .collect();
    assert_eq!(selected.len(), 9);
    for record in selected {
        assert_native(record);
    }
}

#[test]
fn intent_advisory_matches_reference_without_mutation() {
    let cases = records();
    let selected: Vec<_> = cases
        .iter()
        .filter(|r| r["case"].as_str().unwrap().starts_with("intent-"))
        .collect();
    assert_eq!(selected.len(), 8);
    for record in selected {
        assert_native(record);
    }
}

#[test]
fn cap_exact_10239_byte_input_and_unicode_cut_match_reference() {
    let cases = records();
    let selected: Vec<_> = cases
        .iter()
        .filter(|r| r["case"].as_str().unwrap().starts_with("cap-"))
        .collect();
    assert_eq!(selected.len(), 5);
    for record in selected {
        let stdout = frozen::decode(&record["expected"]["stdout"]);
        assert!(stdout.len() <= 10239);
        assert!(std::str::from_utf8(&stdout).is_ok());
        assert_native(record);
    }
}

#[test]
fn retired_python_runtime_failures_remain_explicit_reference_evidence() {
    let cases = records();
    let retired: Vec<_> = cases.iter().filter(|r| r["retired"] == true).collect();
    assert_eq!(cases.len(), 36);
    assert_eq!(retired.len(), 3);
    for record in retired {
        assert_eq!(record["expected"]["exit"], 0);
        let mut stderr =
            b"[SessionStart] WARNING: Upfront context unavailable; using safety fallback.\n"
                .to_vec();
        if record["case"] == "retired-python-launcher-failure" {
            stderr.extend_from_slice(
                b"[SessionStart] WARNING: Context output cap unavailable; using safety fallback.\n",
            );
        }
        assert_eq!(frozen::decode(&record["expected"]["stderr"]), stderr);
        assert_eq!(record["expected"]["delta"], serde_json::json!({}));
        assert_eq!(record["expected"]["deleted"], serde_json::json!([]));
    }
}

#[test]
fn captured_reference_sources_remain_pinned() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/w1/session-start.json")).unwrap();
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    for (path, expected) in fixture["sources"].as_object().unwrap() {
        assert_eq!(
            digest::sha256(&std::fs::read(repo.join(path)).unwrap()),
            expected.as_str().unwrap(),
            "{path}"
        );
    }
}

#[test]
fn retired_python_builder_errors_use_native_renderer_without_mutation() {
    let cases = records();
    let baseline = cases
        .iter()
        .find(|r| r["case"] == "profile-missing")
        .unwrap();
    for record in cases.iter().filter(|r| r["retired"] == true) {
        let mut native = record.clone();
        native["expected"] = baseline["expected"].clone();
        assert_native(&native);
    }
}
