use super::*;
use crate::mir_cli::bootstrap::ProductionHost;

fn normalize_root(message: &str, root: &str) -> String {
    let plain = root.strip_prefix(r"\\?\").unwrap_or(root);
    let mut normalized = message.to_owned();
    // Messages are decoded JSON, but OS paths can still be Python repr strings.
    for spelling in [root, plain] {
        normalized = normalized
            .replace(&spelling.replace('\\', r"\\"), "{ROOT}")
            .replace(spelling, "{ROOT}");
    }
    normalized
}

#[test]
fn y_e16_root_spellings() {
    let root = r"\\?\C:\scratch\oracle";
    let plain = r"C:\scratch\oracle";
    for spelling in [root, plain] {
        for escaped in [false, true] {
            let path = if escaped {
                spelling.replace('\\', r"\\")
            } else {
                spelling.into()
            };
            let suffix = if escaped {
                r"\\config\\s"
            } else {
                r"\config\s"
            };
            let message = format!("invalid '{path}{suffix}': schema keeps a/b and c\\d");
            let expected = format!("invalid '{{ROOT}}{suffix}': schema keeps a/b and c\\d");
            assert_eq!(normalize_root(&message, root), expected);
            let wire = serde_json::to_string(&message).unwrap();
            let decoded: String = serde_json::from_str(&wire).unwrap();
            assert_eq!(normalize_root(&decoded, root), expected);
        }
    }
    assert_eq!(
        normalize_root("invalid /tmp/root/config/s", "/tmp/root"),
        "invalid {ROOT}/config/s"
    );
}

fn frozen(mode: &str, case: &str) {
    #[cfg(windows)]
    let mut records: Vec<Value> = {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/y-e16-windows.json");
        let data = fs::read_to_string(path)
            .expect("capture y-e16-windows.json on Windows with generate_y_e16.py first");
        let records: Vec<Value> = serde_json::from_str(&data).unwrap();
        assert_eq!(
            records.len(),
            58,
            "Windows capture must include base and shipped cases"
        );
        records
    };
    #[cfg(not(windows))]
    let mut records: Vec<Value> = {
        let mut records: Vec<Value> =
            serde_json::from_str(include_str!("../../tests/fixtures/y-e16.json")).unwrap();
        records.extend(
            serde_json::from_str::<Vec<Value>>(include_str!("../../tests/fixtures/y-e16b.json"))
                .unwrap(),
        );
        records
    };
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
            load_boundary(&root, &mut ProductionHost::default())
        } else {
            payload(
                &root,
                &json!({"payload_manifest":"config/p.json"}),
                &mut ProductionHost::default(),
            )
        };
        let actual = match result {
            Ok(value) => json!({"value":value}),
            Err(e) => {
                json!({"class":e.class,"message":normalize_root(&e.message, root.to_str().unwrap())})
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
