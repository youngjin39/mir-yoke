#[path = "../src/digest.rs"]
mod digest;
#[path = "support/relation_root.rs"]
mod relation_root;
use handoff_packet::mir_core::{
    memory::{relation_facts as f, store},
    memory_relations as m,
    relations::{Edge, Options, Result},
};
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use std::{
    fs,
    path::Path,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
fn clock() -> SystemTime {
    UNIX_EPOCH + Duration::from_secs(981173106)
}
fn observed<T: serde::Serialize>(v: Result<T>) -> Value {
    match v {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":["RelationError",e.0]}),
    }
}
fn compact(v: Value) -> Value {
    match v {
        Value::String(s) if s.chars().count() > 256 => {
            json!({"len":s.chars().count(),"sha256":digest::sha256(s.as_bytes())})
        }
        Value::Array(a) => Value::Array(a.into_iter().map(compact).collect()),
        Value::Object(m) => Value::Object(m.into_iter().map(|(k, v)| (k, compact(v))).collect()),
        v => v,
    }
}
fn edge_values(edges: &[Edge]) -> Vec<Value> {
    edges.iter().map(Edge::as_dict).collect()
}
#[cfg(unix)]
fn symlink(from: &Path, to: &Path, _: bool) {
    std::os::unix::fs::symlink(from, to).unwrap();
}
#[cfg(windows)]
fn symlink(from: &Path, to: &Path, directory: bool) {
    if directory {
        std::os::windows::fs::symlink_dir(from, to).unwrap();
    } else {
        std::os::windows::fs::symlink_file(from, to).unwrap();
    }
}
fn metadata_raw(m: &Value) -> String {
    format!(
        "{{\"path\": {}, \"relation_schema\": {}, \"relation_project_path\": {}, \
        \"relation_document_status\": {}}}",
        m["path"], m["relation_schema"], m["relation_project_path"], m["relation_document_status"]
    )
}
fn scenario(name: &str, root: &Path) -> Value {
    for p in ["src/a.py", "tests/a.py"] {
        fs::create_dir_all(root.join(p).parent().unwrap()).unwrap();
        fs::write(root.join(p), "pass\n").unwrap();
    }
    fs::create_dir(root.join(".mir")).unwrap();
    let path = root.join(".mir").join("memory.db");
    if let Some(mode) = name.strip_prefix("path.") {
        match mode {
            "directory" => fs::create_dir(&path).unwrap(),
            "symlink" => symlink(&root.join("src/a.py"), &path, false),
            "regular" => fs::write(&path, "").unwrap(),
            "parent" => {
                fs::remove_dir(root.join(".mir")).unwrap();
                symlink(&root.join("src"), &root.join(".mir"), true);
                fs::write(root.join("src/memory.db"), "").unwrap();
            }
            "missing" => (),
            _ => panic!("{name}"),
        }
        return observed(m::memory_db_path(root).map(|p| p.to_str().unwrap().to_owned()));
    }
    let conn = Connection::open(&path).unwrap();
    conn.execute_batch("PRAGMA foreign_keys=OFF").unwrap();
    store::apply_migrations(&conn).unwrap();
    let mut body = String::from("---\nstatus: active\nmemory_relations:\n");
    for (a, p, b) in [
        ("A", "depends_on", "B"),
        ("B", "depends_on", "C"),
        ("A", "realized_by", "M"),
        ("M", "implemented_in", "src/a.py::z"),
        ("M", "implemented_in", "src/a.py::a"),
        ("A", "verified_by", "tests/a.py"),
    ] {
        body.push_str(&format!("  - [{a}, {p}, {b}]\n"));
    }
    if name == "owners.ambiguous" {
        body.push_str("  - [A, implemented_in, src/a.py::a]\n");
    }
    body.push_str("---\n");
    let mut metadata = Value::Null;
    for cid in 1..if name == "proofs" { 10 } else { 2 } {
        let source = format!("d{cid}.md");
        fs::write(root.join(&source), &body).unwrap();
        metadata = f::relation_metadata(&source, root, "active").unwrap();
        conn.execute(
            "INSERT INTO content_items(id,source,text_hash,metadata_json)
            VALUES (?,'self_ingest_md',?,?)",
            params![
                cid,
                digest::sha256(body.as_bytes()),
                metadata_raw(&metadata)
            ],
        )
        .unwrap();
        f::reconcile_relation_facts(
            &conn,
            &f::Reconcile {
                declarations: &f::parse_relation_document(&body).unwrap().declarations,
                content_item_id: Some(cid),
                project_root: root,
                source_path: &source,
                document_status: "active",
            },
            clock,
        )
        .unwrap();
    }
    if let Some(mode) = name.strip_prefix("source.") {
        let raw = match mode {
            "bom" => b"\xef\xbb\xbfx\r\ny\r".to_vec(),
            "invalid" => vec![255],
            "atlimit" => vec![b'x'; m::MAX_SOURCE_BYTES],
            "large" => vec![b'x'; m::MAX_SOURCE_BYTES + 1],
            _ => vec![b'x'],
        };
        fs::write(root.join("d1.md"), &raw).unwrap();
        match mode {
            "missing" => fs::remove_file(root.join("d1.md")).unwrap(),
            "unsafe" => metadata["path"] = json!("../outside"),
            "protected" => metadata["path"] = json!(".env"),
            _ => (),
        }
        let expected = if mode == "stale" {
            "stale".into()
        } else {
            digest::sha256(if mode == "bom" { b"x\ny\n" } else { &raw })
        };
        return json!({"value":m::source_text(root,&metadata,&json!(expected),&[],
            if mode=="budget" {0} else {raw.len()})});
    }
    if let Some(mode) = name.strip_prefix("invalid.") {
        conn.execute(
            [
                "UPDATE content_items SET text_hash='stale'",
                "DELETE FROM provenance",
                "UPDATE facts SET predicate='realized_by' WHERE id=1",
            ][mode.parse::<usize>().unwrap()],
            [],
        )
        .unwrap();
    }
    if let Some(n) = name.strip_prefix("metadata.") {
        let mut raw = format!(
            "{{\"path\": {}, \"relation_schema\": {}, \"relation_project_path\": {}, \
            \"relation_document_status\": {}}}",
            metadata["path"],
            metadata["relation_schema"],
            metadata["relation_project_path"],
            metadata["relation_document_status"]
        );
        raw.extend(std::iter::repeat_n(
            ' ',
            n.parse::<usize>().unwrap() - raw.len(),
        ));
        conn.execute("UPDATE content_items SET metadata_json=?", [raw])
            .unwrap();
    }
    if let Some(n) = name.strip_prefix("rows.") {
        for _ in 0..n.parse::<usize>().unwrap() {
            conn.execute(
                "INSERT INTO facts(subject_entity_id,predicate,object_entity_id,polarity,
                status,scope,project_path,created_from)
                VALUES (1,'depends_on',2,'asserted','active','project',?,1)",
                [root.to_str().unwrap()],
            )
            .unwrap();
        }
    }
    if let Some(n) = name.strip_prefix("owner_rows.") {
        for _ in 0..n.parse::<usize>().unwrap() {
            conn.execute_batch(
                "INSERT INTO facts(subject_entity_id,predicate,object_entity_id,polarity,
                status,scope,project_path,created_from) SELECT subject_entity_id,predicate,
                object_entity_id,polarity,status,scope,project_path,created_from FROM facts
                WHERE predicate='implemented_in' ORDER BY id LIMIT 1",
            )
            .unwrap();
        }
    }
    if !conn.is_autocommit() {
        conn.execute_batch("COMMIT").unwrap();
    }
    let mut o = Options::new(root);
    o.max_bytes = json!(16000);
    let anchors = [
        "A",
        "missing",
        "src/a.py",
        "./src//a.py::z",
        "src/A.py",
        ".env",
    ];
    if let Some(n) = name.strip_prefix("anchor.") {
        return observed(m::resolve_query_anchor(
            &conn,
            root,
            &[],
            anchors[n.parse::<usize>().unwrap()],
        ));
    }
    if let Some(n) = name.strip_prefix("implemented.") {
        return observed(m::implemented_in_rows(
            &conn,
            root,
            ["src/a.py", "src/a.py::a", "missing"][n.parse::<usize>().unwrap()],
        ));
    }
    if let Some(n) = name.strip_prefix("validate.") {
        let mut row = m::relation_rows(
            &conn,
            root,
            &["A".into()].into(),
            "dependencies",
            None,
            None,
            1,
        )
        .unwrap()
        .remove(0);
        let (i, value) = [
            (1, json!("")),
            (3, json!("missing.py")),
            (5, json!("stale")),
            (6, json!("{")),
            (6, json!("[]")),
            (2, json!("depends_on")),
            (2, json!("realized_by")),
        ][n.parse::<usize>().unwrap()]
        .clone();
        row[i] = value;
        let mut state = m::SelectionState::default();
        let (edge, reason) = m::validate_memory_row(&conn, root, &[], &row, &mut state).unwrap();
        let (cached, cached_reason) =
            m::validate_memory_row(&conn, root, &[], &row, &mut state).unwrap();
        return json!({"value":[edge.map(|e|e.as_dict()),reason,cached.map(|e|e.as_dict()),
            cached_reason,state.source_bytes]});
    }
    if let Some(mode) = name.strip_prefix("traverse.") {
        let (anchor, purpose, depth, max_edges) = if let Some(n) = mode.strip_prefix("limit") {
            let (d, e) = [(0, 64), (1, 64), (2, 64), (4, 1)][n.parse::<usize>().unwrap()];
            ("A", "dependencies", d, e)
        } else {
            (
                if mode == "impact" { "src/a.py::z" } else { "A" },
                mode,
                4,
                64,
            )
        };
        o.depth = json!(depth);
        o.max_edges = json!(max_edges);
        let mut state = m::SelectionState::default();
        let (edges, notices) =
            m::traverse_memory_rows(&conn, &o, &[], &[anchor.into()], purpose, &mut state).unwrap();
        return json!({"value":[edge_values(&edges),notices,state.selected_fact_ids,
            state.source_bytes,
            state.incomplete,state.proofs_omitted]});
    }
    if name == "logical" {
        let mut v = json!({});
        for p in ["journal_mode", "foreign_keys", "synchronous"] {
            v[p] = json!([[conn
                .query_row(&format!("PRAGMA {p}"), [], |r| Ok(match r.get_ref(0)? {
                    rusqlite::types::ValueRef::Integer(i) => json!(i),
                    rusqlite::types::ValueRef::Text(s) => json!(std::str::from_utf8(s).unwrap()),
                    _ => panic!("pragma"),
                }))
                .unwrap()]]);
        }
        return json!({"value":v});
    }
    if name == "inactive" {
        let draft = body.replace("status: active", "status: draft");
        fs::write(root.join("d1.md"), &draft).unwrap();
        metadata["relation_document_status"] = json!("draft");
        conn.execute(
            "UPDATE content_items SET text_hash=?,metadata_json=?",
            params![digest::sha256(draft.as_bytes()), metadata_raw(&metadata)],
        )
        .unwrap();
    }
    drop(conn);
    if let Some(n) = name.strip_prefix("budget.") {
        let n = n.parse::<i64>().unwrap();
        return observed(m::query_with_budget(
            &json!("A"),
            "implementation",
            &o,
            (body.len() as i64 + n) as usize,
        ));
    }
    if let Some(n) = name.strip_prefix("query.") {
        let (a, p) = [
            ("A", "implementation"),
            ("A", "impact"),
            ("A", "verification"),
            ("A", "dependencies"),
            ("src/a.py", "impact"),
            ("missing", "dependencies"),
            ("A", "unknown"),
        ][n.parse::<usize>().unwrap()];
        if n == "4" {
            o.max_edges = json!(1);
        }
        return observed(m::query_memory_relations(&json!(a), p, &o));
    }
    if name.starts_with("owner_rows.") {
        let purposes = json!(["impact", "dependencies"]);
        return observed(m::bundle_memory_relations(
            &json!(["src/a.py"]),
            &purposes,
            &o,
        ));
    }
    if name.starts_with("bundle.") || name == "owners.ambiguous" {
        let i = if name == "owners.ambiguous" {
            8
        } else {
            name[7..].parse::<usize>().unwrap()
        };
        let (a, p) = [
            (
                json!(["A"]),
                json!(["implementation", "dependencies", "verification", "impact"]),
            ),
            (
                json!(["src/a.py"]),
                json!(["implementation", "verification"]),
            ),
            (json!(["missing"]), json!(["impact", "dependencies"])),
            (json!([]), json!(["impact", "dependencies"])),
            (json!(["A", "A"]), json!(["dependencies", "dependencies"])),
            (json!(["A"]), json!(["unknown", "impact"])),
            (json!(["A"]), json!(["implementation", "dependencies"])),
            (Value::Null, Value::Null),
            (json!(["src/a.py"]), json!(["impact", "dependencies"])),
        ][i]
            .clone();
        if i == 6 {
            o.max_edges = json!(1);
        }
        return observed(m::bundle_memory_relations(&a, &p, &o));
    }
    o.depth = json!(4);
    let anchor = if name == "reverse" { "C" } else { "A" };
    observed(m::query_memory_relations(
        &json!(anchor),
        "dependencies",
        &o,
    ))
}
fn expected_record(oracle: &Value, name: &str, windows: bool) -> Value {
    if windows && name.starts_with("path.") {
        let captured: Value = serde_json::from_str(include_str!(
            "fixtures/w2/b07-relations-query-windows-paths.json"
        ))
        .unwrap();
        let record = &captured["records"][name];
        assert!(!record.is_null(), "missing Windows capture: {name}");
        return serde_json::from_str(
            &serde_json::to_string(record)
                .unwrap()
                .replace("{ROOT}", "<tmp>"),
        )
        .unwrap();
    }
    oracle[name].clone()
}

#[test]
fn windows_path_expectations_preserve_captured_suffixes() {
    let oracle: Value =
        serde_json::from_str(include_str!("fixtures/w2/b07-relations-query.json")).unwrap();
    let windows: Value = serde_json::from_str(include_str!(
        "fixtures/w2/b07-relations-query-windows-paths.json"
    ))
    .unwrap();
    assert_eq!(windows["platform"], "win32");
    assert_eq!(windows["python"], "3.12.13");
    assert_eq!(
        windows["reference_pin"],
        "f2a9dbf942585e0e02ed095db492d031c682d0e9"
    );
    assert_eq!(windows["records"].as_object().unwrap().len(), 5);
    for (name, record) in oracle.as_object().unwrap() {
        assert_eq!(expected_record(&oracle, name, false), *record, "{name}");
        if name.starts_with("path.") {
            let captured = serde_json::to_string(&windows["records"][name]).unwrap();
            let captured: Value =
                serde_json::from_str(&captured.replace("{ROOT}", "<tmp>")).unwrap();
            assert_eq!(expected_record(&oracle, name, true), captured, "{name}");
        } else {
            assert_eq!(expected_record(&oracle, name, true), *record, "{name}");
        }
    }
}

#[test]
fn frozen_records() {
    let oracle: Value =
        serde_json::from_str(include_str!("fixtures/w2/b07-relations-query.json")).unwrap();
    let mut counts = [0, 0, 0];
    let mut mismatches = Vec::new();
    for name in oracle.as_object().unwrap().keys() {
        if ["query.7", "bundle.7"].contains(&name.as_str()) {
            // Python-only duplicate keyword binding errors occur before either library function.
            counts[2] += 1;
            continue;
        }
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let actual = if name == "limits" {
            json!({"value":[m::MAX_DB_ROWS,m::MAX_METADATA_CHARS,
            m::MAX_TOTAL_SOURCE_BYTES,m::MAX_PROVENANCE_PER_EDGE]})
        } else {
            scenario(name, &root)
        };
        let actual = relation_root::normalize(actual, &root);
        let actual: Value = serde_json::from_str(&serde_json::to_string(&actual).unwrap().replace(
            &serde_json::to_string(root.to_str().unwrap()).unwrap()
                [1..serde_json::to_string(root.to_str().unwrap()).unwrap().len() - 1],
            "<tmp>",
        ))
        .unwrap();
        let actual = compact(actual);
        let expected = expected_record(&oracle, name, cfg!(windows));
        if actual != expected {
            mismatches.push(format!("{name}: actual={actual}\nexpected={expected}"));
        }
        counts[0] += 1;
    }
    assert_eq!(counts, [69, 0, 2]);
    assert!(
        mismatches.is_empty(),
        "replayed all {} native records; {} mismatches:\n{}",
        counts[0],
        mismatches.len(),
        mismatches.join("\n")
    );
}

#[test]
fn inactive_documents_and_forward_only_queries_do_not_emit_edges() {
    for name in ["inactive", "reverse"] {
        let temp = tempfile::tempdir().unwrap();
        let actual = scenario(name, &temp.path().canonicalize().unwrap());
        assert_eq!(actual["value"]["edges"], json!([]), "{name}: {actual}");
        if name == "inactive" {
            assert_eq!(
                actual["value"]["notices"],
                json!(["skipped inactive relation document: 1 edge(s)"])
            );
        }
    }
}
