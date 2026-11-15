//! Tokenise only the synthetic relation_project_path, preserving metadata bytes otherwise.
use regex::{Captures, Regex};
use serde_json::{Value, json};
use std::{path::Path, sync::OnceLock};

pub fn normalize(value: Value, root: &Path) -> Value {
    let root = root.to_str().unwrap();
    let plain = root.strip_prefix(r"\\?\").unwrap_or(root);
    let verbatim = format!(r"\\?\{plain}");
    walk(value, &[root, plain, verbatim.as_str()])
}

fn walk(value: Value, aliases: &[&str]) -> Value {
    match value {
        Value::String(s) => {
            // Inspect metadata without re-serialising it: preserve spacing,
            // key order, escapes and every unrelated field byte-for-byte.
            let metadata = serde_json::from_str::<Value>(&s).ok();
            if !metadata
                .as_ref()
                .is_some_and(|m| m.get("relation_project_path").is_some())
            {
                return Value::String(s);
            }
            static FIELD: OnceLock<Regex> = OnceLock::new();
            let field = FIELD.get_or_init(|| {
                Regex::new(r#"("relation_project_path"\s*:\s*)("(?:\\.|[^"\\])*")"#).unwrap()
            });
            Value::String(
                field
                    .replace_all(&s, |c: &Captures<'_>| {
                        let path: String = serde_json::from_str(&c[2]).unwrap();
                        if aliases.contains(&path.as_str()) {
                            format!("{}\"<tmp>\"", &c[1])
                        } else {
                            c[0].to_owned()
                        }
                    })
                    .into_owned(),
            )
        }
        Value::Array(a) => Value::Array(a.into_iter().map(|v| walk(v, aliases)).collect()),
        Value::Object(m) => Value::Object(
            m.into_iter()
                .map(|(k, v)| {
                    let v = if k == "relation_project_path"
                        && v.as_str().is_some_and(|s| aliases.contains(&s))
                    {
                        json!("<tmp>")
                    } else {
                        walk(v, aliases)
                    };
                    (k, v)
                })
                .collect(),
        ),
        v => v,
    }
}

#[test]
fn escaped_relation_root() {
    for root in [r"C:\scratch\case", r"\\?\C:\scratch\case", "/scratch/case"] {
        let plain = root.strip_prefix(r"\\?\").unwrap_or(root);
        for alias in [root, plain] {
            let encoded = serde_json::to_string(alias).unwrap();
            let metadata =
                format!("{{\"path\": \"notes/a.md\", \"relation_project_path\": {encoded}}}");
            let actual = normalize(json!({"value": [[1, metadata]]}), Path::new(root));
            assert_eq!(
                actual["value"][0][1],
                r#"{"path": "notes/a.md", "relation_project_path": "<tmp>"}"#,
                "root={root} alias={alias}"
            );
        }
    }
}

#[test]
fn relation_root_scope() {
    let root = r"\\?\C:\scratch\case";
    let plain = r"C:\scratch\case";
    let other = r"C:\outside\case";
    let encoded = serde_json::to_string(plain).unwrap();
    let metadata = format!(
        "{{ \"relation_project_path\" : {encoded}, \"text\": {encoded}, \"other\": \"a\\\\b\" }}"
    );
    let expected = metadata.replacen(&format!(" : {encoded}"), " : \"<tmp>\"", 1);
    let value = json!({"metadata_json": metadata, "stdout": plain, "stderr": other,
        "code": 1, "bytes": r"a\b", "malformed": "{broken",
        "foreign": {"relation_project_path": other},
        "child": {"relation_project_path": format!("{plain}x")},
        "structured": {"relation_project_path": plain}});
    let mut wanted = value.clone();
    wanted["metadata_json"] = json!(expected);
    wanted["structured"]["relation_project_path"] = json!("<tmp>");
    assert_eq!(normalize(value, Path::new(root)), wanted);
}
