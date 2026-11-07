use handoff_packet::mir_core::memory::store;
use rusqlite::{Connection, types::ValueRef};
use serde_json::{Value, json};
use std::path::Path;
// Only synthetic root identity and platform path separators differ from the oracle.
pub fn clean_paths(value: &mut Value, tmp: &Path) {
    match value {
        Value::String(s) => {
            let root = tmp.to_str().unwrap();
            *s = s
                .replace(&root.replace('\\', "\\\\"), "<tmp>")
                .replace(root, "<tmp>");
            if s.contains("<tmp>") {
                *s = s.replace("\\\\", "/").replace('\\', "/");
            }
        }
        Value::Array(values) => values.iter_mut().for_each(|v| clean_paths(v, tmp)),
        Value::Object(values) => values.values_mut().for_each(|v| clean_paths(v, tmp)),
        _ => (),
    }
}
pub fn connect(path: &Path) -> store::Connection {
    store::connect(
        path,
        store::ConnectOptions {
            timeout: None,
            vec_loading: store::VecLoading::Bundled,
        },
    )
    .unwrap()
}
pub fn rows(conn: &Connection, sql: &str) -> Value {
    let mut stmt = conn.prepare(sql).unwrap();
    let width = stmt.column_count();
    let values = stmt
        .query_map([], |row| {
            Ok((0..width)
                .map(|i| match row.get_ref(i).unwrap() {
                    ValueRef::Null => Value::Null,
                    ValueRef::Integer(v) => json!(v),
                    ValueRef::Real(v) => json!(v),
                    ValueRef::Text(v) => json!(std::str::from_utf8(v).unwrap()),
                    ValueRef::Blob(_) => panic!("unexpected blob"),
                })
                .collect::<Vec<_>>())
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    json!(values)
}
pub fn schema(conn: &Connection) -> Value {
    json!({"schema": rows(conn,
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"),
        "migrations": rows(conn,"SELECT version,name FROM schema_migrations ORDER BY version"),
        "pragmas": {"journal_mode":rows(conn,"PRAGMA journal_mode")[0][0],
            "synchronous":rows(conn,"PRAGMA synchronous")[0][0],
            "foreign_keys":rows(conn,"PRAGMA foreign_keys")[0][0]}})
}
