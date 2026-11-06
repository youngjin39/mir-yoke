use handoff_packet::mir_core::{audit_log::*, canonical::canonical_json, memory::store};
use rusqlite::{
    Connection,
    trace::{TraceEvent, TraceEventCodes},
    types::ValueRef,
};
use serde_json::{Value, json};
use std::cell::RefCell;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
thread_local! {
    static TRACE: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
}
fn trace(event: TraceEvent<'_>) {
    if let TraceEvent::Stmt(statement, _) = event {
        TRACE.with_borrow_mut(|statements| statements.push(statement.expanded_sql().unwrap()));
    }
}
fn take_trace() -> Vec<String> {
    TRACE.with_borrow_mut(std::mem::take)
}
fn clock() -> SystemTime {
    UNIX_EPOCH + Duration::new(1_893_542_400, 123_456_000)
}
#[rustfmt::skip]
fn rows(c: &Connection, table: &str) -> Value {
    let mut s = c.prepare(&format!("SELECT * FROM {table} ORDER BY 1")).unwrap();
    let width = s.column_count();
    let values = s.query_map([], |r| Ok((0..width).map(|i| match r.get_ref(i).unwrap() {
        ValueRef::Null => Value::Null,
        ValueRef::Integer(n) => json!(n),
        ValueRef::Text(t) => json!(std::str::from_utf8(t).unwrap()),
        other => panic!("unexpected cell {other:?}"),
    }).collect::<Vec<_>>())).unwrap().collect::<Result<Vec<_>, _>>().unwrap();
    json!(values)
}
fn state(a: &AuditLog<'_>) -> Value {
    json!({"audit":rows(a.conn,"audit_log"),"facts":rows(a.conn,"facts"),
        "transaction":!a.conn.is_autocommit(),"verify":a.audit_verify().unwrap()})
}
#[test]
#[rustfmt::skip]
fn frozen_records() {
    let records: Value = serde_json::from_str(include_str!("fixtures/w2/b04-audit.json")).unwrap();
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        // Only Python object-system observations remain exempt.
        let reason = if name.starts_with("now.") { Some("Python mock call repr; timestamp bytes are still replayed") }
            else if name == "canonical.mixed_keys" { Some("Python mixed-type mapping keys are outside serde_json::Value") }
            else if name == "canonical.set" { Some("Python set objects are outside serde_json::Value") }
            else if name == "canonical.nonfinite" { Some("Python non-finite floats are outside serde_json::Value") }
            else if name == "result.fields_frozen" { Some("Python dataclass repr, setattr and FrozenInstanceError") } else { None };
        if let Some(reason) = reason { exempt += 1; eprintln!("{name}: exempt: {reason}"); } else { replayed += 1; }
        if name.starts_with("canonical.") {
            let input = match name.as_str() {
                "canonical.empty" => json!({}),
                "canonical.nested" => json!({"z":[null,true,false,-0.0],"a":{"\u{e9}":"\n\t\"\\\0"}}),
                _ => continue,
            };
            assert_eq!(json!({"value":canonical_json(&input,Some(&[]))}), *expected, "{name}");
            continue;
        }
        if let Some(n) = name.strip_prefix("now.") {
            let t = UNIX_EPOCH + Duration::new(1_893_542_400, n.parse::<u32>().unwrap()*1000);
            assert_eq!(now_iso(t).unwrap(), expected["value"]["value"]);
            continue;
        }
        if name == "result.fields_frozen" { continue; }
        let tmp = tempfile::tempdir().unwrap();
        let c = store::connect(&tmp.path().join("db"), Some(0.001)).unwrap().conn;
        // Oracle _db uses raw sqlite3 defaults rather than store.connect pragmas.
        c.execute_batch("PRAGMA journal_mode=DELETE; PRAGMA foreign_keys=OFF").unwrap();
        store::apply_migrations(&c).unwrap();
        c.execute("UPDATE schema_migrations SET applied_at = ?", [now_iso(clock()).unwrap()]).unwrap();
        if name.starts_with("append.") {
            take_trace();
            c.trace_v2(TraceEventCodes::SQLITE_TRACE_STMT, Some(trace));
        }
        let a = AuditLog::with_clock(&c, clock);
        let value = if let Some(mode) = name.strip_prefix("facade.") {
            let hash = match mode {
                "event" => a.event("custom", &json!({"nested":{"b":2,"a":1}})),
                "numbers" => a.event("custom", &json!({"f":1e16,"g":0.1,"h":-0.0,"s":1.5e-7})),
                "extra" => a.record("p","t","denied","why", &json!({"detail":"\u{e9}","n":0})),
                _ => a.record("","","","", &json!({})),
            }.unwrap();
            json!({"value":hash,"state":state(&a)})
        } else if let Some(mode) = name.strip_prefix("verify.") {
            for i in 0..if mode == "empty" {0} else {3} { a.event(&format!("event-{i}"), &json!({"index":i})).unwrap(); }
            if mode != "empty" && mode != "valid" {
                c.execute_batch("BEGIN").unwrap();
                let sql = match mode {
                    "reordered" => "UPDATE audit_log SET id = 0 WHERE id = 2".into(),
                    "gap" => "UPDATE audit_log SET id = 9 WHERE id = 3".into(),
                    "deleted" => "DELETE FROM audit_log WHERE id = 2".into(),
                    _ => { let (col,id)=mode.rsplit_once('_').unwrap(); format!("UPDATE audit_log SET {col} = 'x' WHERE id = {id}") }
                }; c.execute(&sql, []).unwrap();
            } state(&a)
        } else if let Some(mode) = name.strip_prefix("gc.") {
            let flags: Vec<_> = mode.split('_').map(|v| v == "True").collect();
            if !flags[1] {
                for to in [None,Some("2030-01-01"),Some("2030-01-01T23:59:59+00:00"),Some("2030-01-02"),Some("2030-01-02T00:00:00+00:00"),Some("2030-01-02T00:00:01+00:00"),Some("2030-01-03")] {
                    c.execute("INSERT INTO facts(status, valid_to) VALUES ('active', ?)", [to]).unwrap();
                }
                for status in ["expired","superseded"] { c.execute("INSERT INTO facts(status, valid_to) VALUES (?, '2030-01-01')",[status]).unwrap(); }
            }
            if flags[2] { c.execute_batch("BEGIN; INSERT INTO facts(status) VALUES ('active')").unwrap(); }
            let before=state(&a); let counts=a.gc_scan(flags[0]).unwrap(); let after=state(&a); let again=a.gc_scan(flags[0]).unwrap();
            if !c.is_autocommit() { c.execute_batch("ROLLBACK").unwrap(); }
            json!({"before":before,"counts":counts,"after":after,"again":again,"rollback":state(&a)})
        } else if let Some(mode) = name.strip_prefix("append.") {
            if mode == "busy" {
                let other=Connection::open(tmp.path().join("db")).unwrap(); other.execute_batch("BEGIN IMMEDIATE").unwrap();
                let e=a.event("busy", &json!({})).unwrap_err();
                let trace=take_trace();
                let result=json!({"result":{"error":[e.python_class(),e.to_string()]},"trace":trace,"state":state(&a)});
                assert_eq!(result,expected["value"],"{name}"); continue;
            }
            if mode.starts_with("caller") { c.execute_batch("BEGIN").unwrap(); }
            let hashes=[a.audit_append("a|b", &json!({"z":1,"a":"\u{e9}"}), !matches!(mode,"deferred"|"caller_false")).unwrap(), a.event("", &json!({})).unwrap()];
            let trace=take_trace();
            let mut result=json!({"hashes":hashes,"trace":trace,"state":state(&a)});
            if matches!(mode,"caller"|"caller_false"|"deferred") { c.execute_batch("ROLLBACK").unwrap(); result["rollback"]=state(&a); }
            else if mode == "caller_commit" { c.execute_batch("COMMIT").unwrap(); result["commit"]=state(&a); }
            else {
                result["migrations"]=rows(&c,"schema_migrations");
                let mut s=c.prepare("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").unwrap();
                result["objects"]=json!(s.query_map([], |r| Ok((0..4).map(|i| r.get::<_,Option<String>>(i).unwrap()).collect::<Vec<_>>())).unwrap().collect::<Result<Vec<_>,_>>().unwrap());
                let mut pragmas=serde_json::Map::new();
                for key in ["journal_mode","foreign_keys","busy_timeout"] {
                    let v=c.query_row(&format!("PRAGMA {key}"), [], |r| Ok(match r.get_ref(0)? { ValueRef::Integer(n)=>json!(n), ValueRef::Text(t)=>json!(std::str::from_utf8(t).unwrap()), _=>panic!("pragma type") })).unwrap();
                    pragmas.insert(key.into(),v);
                }
                result["pragmas"]=json!(pragmas);
            }
            result
        } else { panic!("unmapped {name}") };
        assert_eq!(value, expected["value"], "{name}");
    }
    assert_eq!((replayed,exempt),(40,7));
    assert_eq!(replayed+exempt,47);
}
