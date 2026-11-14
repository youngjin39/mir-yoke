use handoff_packet::mir_core::memory::{external_store::*, store, vector_index};
use serde_json::{Value, json};
use std::fs;

#[test]
fn frozen_vector_retrieval() {
    let mut records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e7.json")).unwrap();
    records.extend(
        serde_json::from_str::<Vec<Value>>(include_str!("fixtures/y-e12a-metadata.json")).unwrap(),
    );
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        fs::create_dir(root.join("notes")).unwrap();
        for (i, doc) in r["docs"].as_array().unwrap().iter().enumerate() {
            fs::write(root.join(format!("notes/{i}.md")), doc.as_str().unwrap()).unwrap();
        }
        let mut c = store::connect(
            &root.join("memory.db"),
            store::ConnectOptions {
                timeout: None,
                vec_loading: store::VecLoading::Bundled,
            },
        )
        .unwrap();
        store::apply_migrations(&c.conn).unwrap();
        if r["mode"] == "unavailable" {
            c.vec_available = false;
        }
        let clock = || "2026-11-15T00:00:00Z".into();
        let es = ExternalStore::new(&c, &clock).unwrap();
        let id = es
            .register(&Registration {
                slug: "notes".into(),
                root_path: root.join("notes").to_str().unwrap().into(),
                mode: "indexed".into(),
                owner: "synthetic".into(),
                glob_include: vec![],
                glob_exclude: vec![],
                historical_glob: vec![],
                chunk_size: 800,
                chunk_overlap: 100,
            })
            .unwrap();
        es.scan(id, None).unwrap();
        let mode = r["mode"].as_str().unwrap();
        if let Some(kind) = mode.strip_prefix("metadata-") {
            let raw = r["metadata"].as_str().unwrap();
            let value = if ["unrelated", "archived"].contains(&kind) {
                rusqlite::types::Value::Blob(br#"{"created":"2026-11-15"}"#.to_vec())
            } else if kind.starts_with("blob") {
                rusqlite::types::Value::Blob(
                    (0..raw.len())
                        .step_by(2)
                        .map(|i| u8::from_str_radix(&raw[i..i + 2], 16).unwrap())
                        .collect(),
                )
            } else if kind == "integer" {
                rusqlite::types::Value::Integer(raw.parse().unwrap())
            } else {
                rusqlite::types::Value::Text(raw.into())
            };
            c.conn
                .execute(
                    "UPDATE external_documents SET frontmatter_json=? WHERE relative_path='1.md'",
                    [value],
                )
                .unwrap();
            if kind == "archived" {
                c.conn.execute("UPDATE external_documents SET status='archived' WHERE relative_path='1.md'", []).unwrap();
            }
        }
        if mode == "recent" {
            c.conn
                .execute(
                    "UPDATE external_documents SET frontmatter_json=? WHERE relative_path=?",
                    [r#"{"created":"2026-11-15"}"#, "2.md"],
                )
                .unwrap();
        }
        if ["filtered", "history"].contains(&mode) {
            c.conn
                .execute(
                    "UPDATE external_documents SET status='archived' WHERE relative_path='2.md'",
                    [],
                )
                .unwrap();
        }
        if mode == "expansion" {
            c.conn
                .execute(
                    "UPDATE external_documents SET status='archived' WHERE relative_path!='7.md'",
                    [],
                )
                .unwrap();
        }
        for i in 0..r["docs"].as_array().unwrap().len() {
            let mut v = vec![0.0; 1024];
            v[if ["ties", "recent", "expansion"].contains(&mode) {
                0
            } else {
                (1026 - i) % 1024
            }] = 1.0;
            if !["no-vectors", "unavailable", "no-scores"].contains(&mode) {
                vector_index::upsert_vector(&c.conn, i as i64 + 1, &v, 1024, "external_chunks_vec")
                    .unwrap();
            }
        }
        c.conn
            .execute(
                "INSERT OR REPLACE INTO external_store_meta(key,value) VALUES (?,?)",
                [
                    EMBEDDING_FINGERPRINT_KEY,
                    if mode == "mismatch" {
                        "wrong"
                    } else {
                        "synthetic-v1"
                    },
                ],
            )
            .unwrap();
        if mode == "vec-error" {
            c.conn
                .execute("DROP TABLE external_chunks_vec", [])
                .unwrap();
        }
        if mode == "fts-error" {
            c.conn
                .execute("DROP TABLE external_chunks_fts", [])
                .unwrap();
        }
        let query = if mode == "no-scores" {
            "absentword"
        } else {
            "apple"
        };
        let mut called = false;
        let mut embed = |texts: &[String]| {
            called = true;
            assert_eq!(texts, &[query]);
            if mode == "failed" {
                return Err(HelperError {
                    kind: "ValueError",
                    message: "synthetic provider failure".into(),
                });
            }
            if mode == "bad-dim" {
                return Ok(vec![vec![1.0]]);
            }
            if mode == "empty-embedding" {
                return Ok(vec![]);
            }
            if mode == "multiple" {
                return Ok(vec![vec![], vec![]]);
            }
            let mut v = vec![0.0; 1024];
            v[0] = 1.0;
            Ok(vec![v])
        };
        let scopes = match mode {
            "scoped" => vec!["1.md".into()],
            "empty" => vec!["absent".into()],
            _ => vec![],
        };
        let hits = es.search(
            query,
            r["k"].as_i64().unwrap(),
            &scopes,
            ["history", "empty-index"].contains(&mode),
            if mode == "disabled" || mode.starts_with("metadata-") {
                None
            } else {
                Some(&mut embed)
            },
            Some("synthetic-v1"),
        );
        match hits {
            Ok(hits) => {
                assert_eq!(r["exit"], 0, "{mode}");
                let text = hits
                    .iter()
                    .map(|h| {
                        format!(
                            "{{\"path\": {}, \"score\": {}}}",
                            serde_json::to_string(&h.relative_path).unwrap(),
                            h.score
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(", ");
                assert_eq!(
                    format!("[{text}]\n"),
                    r["stdout"].as_str().unwrap(),
                    "{mode}"
                );
                let actual = hits
                    .iter()
                    .map(|h| json!({"path": h.relative_path, "score": h.score}))
                    .collect::<Vec<_>>();
                let expected: Value = serde_json::from_str(r["stdout"].as_str().unwrap()).unwrap();
                assert_eq!(json!(actual), expected, "{mode}");
            }
            Err(e) => {
                assert_eq!(r["exit"], 1, "{mode}: {e}");
                assert!(
                    r["stderr"].as_str().unwrap().contains(&e.to_string()),
                    "{mode}: {e}"
                );
            }
        }
        assert_eq!(
            called,
            !mode.starts_with("metadata-")
                && ![
                    "zero",
                    "disabled",
                    "mismatch",
                    "empty",
                    "unavailable",
                    "vec-error"
                ]
                .contains(&mode),
            "{mode}"
        );
    }
}
