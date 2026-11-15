//! Replay only successful PC captures. Error/rollback records belong to S7.
use super::*;
use serde_json::{Value, json};
use std::fs;
#[cfg(windows)]
use std::os::windows::fs::MetadataExt;

const PIN: &str = "0754c36a1bc5814d793984292aa9be6ae26d3001";
const NORMAL: [&str; 12] = [
    "cleanup-created-home",
    "normal",
    "receipt-bytes",
    "receipt-missing",
    "restore-absent",
    "restore-new",
    "restore-old",
    "snapshot-normal",
    "source-regular",
    "sources-empty",
    "stale-absent",
    "target-absent",
];
fn corpus() -> Value {
    let corpus: Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/user_runtime_install/installer-windows.json"
    ))
    .unwrap();
    assert_eq!(corpus["manifest"]["reference_pin"], PIN);
    let records = corpus["records"].as_object().unwrap();
    assert_eq!(records.len(), 39); // 12 normal + 27 error (S6 FIX added 11 real-OS error records)
    let successful: Vec<_> = records
        .iter()
        .filter(|(_, r)| r["error"].is_null())
        .map(|(name, _)| name.as_str())
        .collect();
    assert_eq!(successful, NORMAL);
    corpus
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn unhex(value: &Value) -> Vec<u8> {
    let text = value["hex"].as_str().unwrap();
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap())
        .collect()
}
fn bytes(value: &Option<Vec<u8>>) -> Value {
    value
        .as_ref()
        .map_or(Value::Null, |b| json!({"hex":hex(b)}))
}
pub(super) fn tree(root: &Path) -> Value {
    fn walk(root: &Path, dir: &Path, rows: &mut serde_json::Map<String, Value>) {
        for entry in fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            let metadata = fs::symlink_metadata(&path).unwrap();
            assert!(!metadata.is_symlink());
            let directory = metadata.is_dir();
            let name = path
                .strip_prefix(root)
                .unwrap()
                .to_str()
                .unwrap()
                .replace('\\', "/");
            rows.insert(
                name,
                json!({
                    "type":if directory {"directory"} else {"file"},
                    "attributes":metadata.file_attributes(),
                    "bytes":if directory {None} else {Some(hex(&fs::read(&path).unwrap()))},
                }),
            );
            if directory {
                walk(root, &path, rows);
            }
        }
    }
    let mut rows = serde_json::Map::new();
    walk(root, root, &mut rows);
    Value::Object(rows)
}
fn check(corpus: &Value, name: &str, root: &Path, value: Value) {
    let record = &corpus["records"][name];
    assert!(NORMAL.contains(&name));
    assert_eq!(value, record["value"], "{name}: value");
    assert_eq!(
        tree(root),
        record["tree"],
        "{name}: tree including attributes/temps"
    );
    // These are direct library calls: exit is null, and no CLI is invoked.
    assert!(record["exit"].is_null());
    assert_eq!(record["stdout_hex"], "");
    assert_eq!(record["stderr_hex"], "");
}
pub(super) fn seed(root: &Path, record: &Value) {
    let mut entries: Vec<_> = record["tree"].as_object().unwrap().iter().collect();
    entries.sort_by_key(|(name, _)| name.len());
    for (name, row) in entries {
        let path = root.join(name);
        if row["type"] == "directory" {
            fs::create_dir_all(path).unwrap();
        } else {
            fs::write(path, unhex(&json!({"hex":row["bytes"]}))).unwrap();
        }
    }
}
pub(super) fn plans(root: &Path, corpus: &Value) -> Vec<RuntimePlan> {
    corpus["records"]["normal"]["input"]
        .as_array()
        .unwrap()
        .iter()
        .map(|input| {
            let home = root.join(input["home"].as_str().unwrap().rsplit('\\').next().unwrap());
            let files = input["files"]
                .as_array()
                .unwrap()
                .iter()
                .map(|f| ManagedFile {
                    source_relative: crate::python_json::Text::new(
                        f["source"]
                            .as_str()
                            .unwrap()
                            .chars()
                            .map(u32::from)
                            .collect(),
                    ),
                    target_relative: f["target"].as_str().unwrap().into(),
                    content: unhex(&f["content"]),
                    sha256: f["sha256"].as_str().unwrap().into(),
                })
                .collect::<Vec<_>>();
            let runtime = home.file_name().unwrap().to_str().unwrap();
            let receipt = make_receipt(runtime, PIN, &files);
            assert_eq!(
                receipt,
                unhex(&input["receipt"]),
                "{runtime}: receipt bytes"
            );
            RuntimePlan {
                identity: capture_home_identity(&home).unwrap(),
                files,
                stale: input["stale"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|s| StaleFile {
                        source_relative: crate::python_json::Text::new(
                            s["source"]
                                .as_str()
                                .unwrap()
                                .chars()
                                .map(u32::from)
                                .collect(),
                        ),
                        target_relative: s["target"].as_str().unwrap().into(),
                        sha256: s["sha256"].as_str().unwrap().into(),
                    })
                    .collect(),
                receipt,
                created_home: input["created_home"].as_bool().unwrap(),
            }
        })
        .collect()
}
#[test]
fn frozen_admission_normal_paths() {
    let c = corpus();
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let config = root.join("config");
    fs::create_dir(&config).unwrap();
    fs::write(
        config.join("capability-sources.json"),
        br#"{"agents":{"allowlist":[]},"commands":{"allowlist":{}},"profiles":{"packs":{}}}"#,
    )
    .unwrap();
    let (agents, commands) = load_sources(&root).unwrap();
    assert!(agents.is_empty() && commands.is_empty());
    // Provider configuration is outside the captured admission tree.
    fs::remove_file(config.join("capability-sources.json")).unwrap();
    fs::remove_dir(config).unwrap();
    check(&c, "sources-empty", &root, json!([[], []]));
    seed(&root, &c["records"]["source-regular"]);
    check(
        &c,
        "source-regular",
        &root,
        json!({"hex":hex(&regular_source(&root, &root.join("source.md")).unwrap())}),
    );

    let (path, receipt) = load_receipt(&root, "claude").unwrap();
    assert!(receipt.is_none());
    assert_eq!(path, root.join(RECEIPT_NAME));
    check(
        &c,
        "receipt-missing",
        &root,
        json!([format!("{{ROOT}}\\cases\\admission\\{RECEIPT_NAME}"), null]),
    );
    fs::write(root.join(RECEIPT_NAME), b"{").unwrap();
    check(
        &c,
        "receipt-bytes",
        &root,
        json!({"hex":hex(&make_receipt("claude", PIN, &[]))}),
    );
}
#[test]
fn frozen_transaction_snapshot_restore_and_absence() {
    let c = corpus();
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    seed(&root, &c["records"]["snapshot-normal"]);
    let plans = plans(&root, &c);
    let snapshots = snapshot(&plans[0]).unwrap();
    let value: Vec<_> = snapshots
        .iter()
        .map(|s| {
            json!({
                "relative":s.relative, "before":bytes(&s.before), "after":bytes(&s.after),
            })
        })
        .collect();
    check(&c, "snapshot-normal", &root, json!(value));
    let mut trace = vec![];
    replay_transaction(&plans, &mut trace).unwrap();
    check(&c, "normal", &root, Value::Null);
    // Compare actual pre-operation hook order to reference begin events only;
    // the native hook does not expose reference wrapper return events.
    let expected: Vec<_> = c["records"]["normal"]["trace"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["phase"] == "begin")
        .cloned()
        .collect();
    assert_eq!(trace, expected);
    check(
        &c,
        "target-absent",
        &root,
        bytes(&read(&plans[0].identity, Path::new("missing.md")).unwrap()),
    );
    restore(
        &plans[0],
        &Snapshot {
            relative: "agents/Z.md".into(),
            before: None,
            after: Some(b"new\r\n".to_vec()),
        },
    )
    .unwrap();
    check(&c, "restore-new", &root, Value::Null);
    restore(
        &plans[0],
        &Snapshot {
            relative: "agents/old.md".into(),
            before: Some(b"old".to_vec()),
            after: Some(b"new\r\n".to_vec()),
        },
    )
    .unwrap();
    check(&c, "restore-old", &root, Value::Null);
    // Replay the shared stale-absent branch through its real transaction caller.
    // The caller also republishes the identical receipt (no observable tree change).
    let absent = RuntimePlan {
        identity: capture_home_identity(&plans[0].identity.path).unwrap(),
        files: vec![],
        stale: plans[0]
            .stale
            .iter()
            .map(|s| StaleFile {
                source_relative: s.source_relative.clone(),
                target_relative: s.target_relative.clone(),
                sha256: s.sha256.clone(),
            })
            .collect(),
        receipt: plans[0].receipt.clone(),
        created_home: false,
    };
    apply_transaction(&[absent]).unwrap();
    check(&c, "stale-absent", &root, Value::Null);
}
fn replay_transaction(plans: &[RuntimePlan], trace: &mut Vec<Value>) -> Result<(), Error> {
    transaction_with(plans, |phase, _, relative| {
        let operation = match phase {
            "payload" | "receipt" => "atomic_write",
            "stale" => "remove_stale_file",
            _ => return Ok(()),
        };
        trace.push(json!({"operation":operation, "phase":"begin", "relative":relative}));
        Ok(())
    })
}
#[test]
fn frozen_restore_absent_and_created_home_cleanup() {
    let c = corpus();
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    seed(&root, &c["records"]["restore-absent"]);
    let plan = RuntimePlan {
        identity: capture_home_identity(&root).unwrap(),
        files: vec![],
        stale: vec![],
        receipt: vec![],
        created_home: false,
    };
    restore(
        &plan,
        &Snapshot {
            relative: "missing".into(),
            before: None,
            after: Some(b"new".to_vec()),
        },
    )
    .unwrap();
    check(&c, "restore-absent", &root, Value::Null);
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let home = root.join("home");
    fs::create_dir(&home).unwrap();
    let plan = RuntimePlan {
        identity: capture_home_identity(&home).unwrap(),
        files: vec![],
        stale: vec![],
        receipt: b"receipt".to_vec(),
        created_home: true,
    };
    replay_cleanup(
        &plan,
        &[Snapshot {
            relative: RECEIPT_NAME.into(),
            before: None,
            after: Some(b"receipt".to_vec()),
        }],
    )
    .unwrap();
    check(&c, "cleanup-created-home", &root, Value::Null);
}

fn replay_cleanup(plan: &RuntimePlan, snapshots: &[Snapshot]) -> Result<(), Error> {
    cleanup(plan, snapshots)
}
