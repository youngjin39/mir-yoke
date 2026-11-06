use handoff_packet::mir_core::memory::{store, vector_index as vi};
use rusqlite::{Connection, types::ValueRef};
use serde_json::{Value, json};
mod b17_support;

fn observed<T: serde::Serialize>(result: Result<T, vi::Error>) -> Value {
    match result {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":[e.python_class(),e.to_string()]}),
    }
}
fn rows(conn: &Connection, sql: &str) -> Value {
    let mut stmt = conn.prepare(sql).unwrap();
    let width = stmt.column_count();
    let values = stmt
        .query_map([], |row| {
            Ok(Value::Array(
                (0..width)
                    .map(|i| match row.get_ref(i).unwrap() {
                        ValueRef::Null => Value::Null,
                        ValueRef::Integer(v) => json!(v),
                        ValueRef::Real(v) => json!(v),
                        ValueRef::Text(v) => json!(std::str::from_utf8(v).unwrap()),
                        ValueRef::Blob(_) => panic!("unexpected blob"),
                    })
                    .collect(),
            ))
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    json!(values)
}
fn database(missing: bool) -> Value {
    let tmp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
    let options = store::ConnectOptions {
        timeout: None,
        vec_loading: if missing {
            store::VecLoading::Unavailable("synthetic unavailable")
        } else {
            store::VecLoading::Bundled
        },
    };
    let wrapper = store::connect(&tmp.path().join("synthetic.db"), options).unwrap();
    let conn = &wrapper.conn;
    let mut state = json!({"available":wrapper.vec_available,"reason":wrapper.vec_reason(),
        "create":observed(vi::ensure_vec_table(conn, 2, "facts_vec"))});
    if !missing {
        assert!(wrapper.vec_available, "{:?}", wrapper.vec_reason());
        vi::ensure_vec_table(conn, 2, "facts_vec").unwrap();
        for (rowid, vector) in [(1, [1., 0.]), (2, [0., 1.]), (3, [-1., 0.])] {
            vi::upsert_vector(conn, rowid, &vector, 2, "facts_vec").unwrap();
        }
        state["replace"] = observed(vi::upsert_vector(conn, 1, &[0., -1.], 2, "facts_vec"));
        state["rows"] = rows(
            conn,
            "SELECT rowid, hex(embedding) FROM facts_vec ORDER BY rowid",
        );
        for (label, query, k) in [
            ("order", vec![0., 1.], 3),
            ("ties", vec![0., 0.], 3),
            ("zero_k", vec![0., 0.], 0),
            ("shape", vec![1.], 2),
        ] {
            state[label] = observed(vi::knn(conn, &query, k, "facts_vec"));
        }
    }
    state["pragmas"] = json!({
        "journal_mode":rows(conn,"PRAGMA journal_mode")[0][0],
        "synchronous":rows(conn,"PRAGMA synchronous")[0][0],
        "foreign_keys":rows(conn,"PRAGMA foreign_keys")[0][0]});
    state["schema"] = rows(
        conn,
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name",
    );
    state["migrations"] = if rows(
        conn,
        "SELECT 1 FROM sqlite_master WHERE name='schema_migrations'",
    ) == json!([])
    {
        json!([])
    } else {
        rows(
            conn,
            "SELECT version,name FROM schema_migrations ORDER BY version",
        )
    };
    json!({"value":state})
}
fn replay(name: &str) -> Value {
    if name.starts_with("http.") {
        return b17_support::replay(name);
    }
    if name.starts_with("vector.") {
        return database(name == "vector.missing");
    }
    if name.starts_with("pack.") {
        let vector = match name {
            "pack.finite" => vec![0., -0., 1., -2.5, 0.1],
            "pack.nonfinite" => vec![f64::NAN, f64::INFINITY, f64::NEG_INFINITY],
            "pack.empty" => vec![],
            _ => panic!("unmapped {name}"),
        };
        let hex: String = vi::pack_vector(&vector)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        return json!({"value":hex});
    }
    let (v, dim) = match name {
        "validate.finite" => (vec![0.6, 0.8], 2),
        "validate.zero" => (vec![0., 0.], 2),
        "validate.dimension" => (vec![1.], 2),
        "validate.empty" => (vec![], 0),
        "validate.nan" => (vec![f64::NAN, 0.], 2),
        "validate.inf" => (vec![0., f64::INFINITY], 2),
        "validate.negative_inf" => (vec![f64::NEG_INFINITY, 0.], 2),
        "validate.bound" => (vec![-10., 10.], 2),
        "validate.over_bound" => (vec![10.001, 0.], 2),
        _ => panic!("unmapped {name}"),
    };
    observed(vi::validate_embedding(&v, dim))
}
#[test]
fn frozen_vector_records() {
    let records: Value = serde_json::from_str(include_str!("fixtures/w2/b17-vector.json")).unwrap();
    let (mut replayed, mut with_exemptions) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        let actual = replay(name);
        let mut expected = expected.clone();
        if name.starts_with("http.") {
            for request in expected["value"]["requests"].as_array_mut().unwrap() {
                for header in b17_support::exempt_headers() {
                    assert!(
                        request["headers"]
                            .as_object_mut()
                            .unwrap()
                            .remove(*header)
                            .is_some()
                    );
                }
            }
            with_exemptions += 1;
        } else {
            replayed += 1;
        }
        assert_eq!(actual, expected, "record {name}");
        eprintln!(
            "{name}: {}",
            if name.starts_with("http.") {
                concat!(
                    "replayed-with-cell-exemptions: requests[*].headers.",
                    "{accept,accept-encoding,connection,content-length,host,user-agent}"
                )
            } else {
                "replayed"
            }
        );
    }
    assert_eq!((replayed, with_exemptions), (14, 17));
    eprintln!("31 records: {replayed} replayed, {with_exemptions} with cell exemptions, 0 exempt");
}
