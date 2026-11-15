use super::*;
use crate::mir_cli::bootstrap::ProductionHost;

fn frozen(mode: &str, case: &str) {
    let mut records: Vec<Value> =
        serde_json::from_str(include_str!("../../tests/fixtures/y-e16.json")).unwrap();
    records.extend(
        serde_json::from_str::<Vec<Value>>(include_str!("../../tests/fixtures/y-e16b.json"))
            .unwrap(),
    );
    records.extend(
        serde_json::from_str::<Vec<Value>>(include_str!("../../tests/fixtures/y-e16c.json"))
            .unwrap(),
    );
    let scratch = Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/Y-E16");
    fs::create_dir_all(&scratch).unwrap();
    for record in records
        .iter()
        .filter(|r| r["mode"] == mode && (case.is_empty() || r["case"] == case))
    {
        let temp = tempfile::tempdir_in(&scratch).unwrap();
        let root = temp.path().canonicalize().unwrap();
        fs::create_dir(root.join("config")).unwrap();
        let path = if mode == "boundary" {
            "config/adopter-boundary.json"
        } else {
            "config/p.json"
        };
        fs::write(root.join(path), record["document"].as_str().unwrap()).unwrap();
        if let Some(schema) = record["schema"].as_str() {
            fs::write(root.join("config/s"), schema).unwrap();
        }
        if record["case"] == "directory" {
            fs::create_dir(root.join("config/s")).unwrap();
        }
        let result = if mode == "boundary" {
            load_boundary(&root, &mut ProductionHost)
        } else {
            payload(
                &root,
                &json!({"payload_manifest":"config/p.json"}),
                &mut ProductionHost,
            )
        };
        let actual = match result {
            Ok(value) => json!({"value":value}),
            Err(e) => {
                json!({"class":e.class,"message":e.message.replace(root.to_str().unwrap(),"{ROOT}")})
            }
        };
        assert_eq!(actual, record["result"], "{mode}/{}", record["case"]);
        assert!(!root.join(".mir/memory.db").exists());
    }
}
#[test]
fn y_e16_boundary() {
    frozen("boundary", "");
}
#[test]
fn y_e16_payload() {
    frozen("payload", "");
}

#[test]
fn y_e16c_long_string() {
    frozen("payload", "long-string");
}
#[test]
fn y_e16c_long_list() {
    frozen("payload", "long-list");
}
#[test]
fn y_e16c_nested_dict() {
    frozen("payload", "nested-dict");
}
#[test]
fn y_e16c_unicode_long_string() {
    frozen("payload", "unicode-long-string");
}
