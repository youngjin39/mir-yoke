//! Library-only parity with audit_log.py and memory/store.py's audit/GC helpers.
#![forbid(unsafe_code)]
use super::{canonical::canonical_json, memory::store::Error};
use rusqlite::{Connection, OptionalExtension, params};
use serde::Serialize;
use serde_json::{Value, json};
use std::time::{SystemTime, UNIX_EPOCH};
const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";
/// SQLite's unixepoch conversion is UTC on Unix and Windows; retain six digits.
pub fn now_iso(time: SystemTime) -> Result<String, Error> {
    let micros = match time.duration_since(UNIX_EPOCH) {
        Ok(d) => d.as_micros() as i128,
        Err(e) => -(e.duration().as_micros() as i128),
    };
    Ok(Connection::open_in_memory()?.query_row(
        "SELECT strftime('%Y-%m-%dT%H:%M:%S', ?, 'unixepoch') || printf('.%06d+00:00', ?)",
        params![
            micros.div_euclid(1_000_000).to_string(),
            micros.rem_euclid(1_000_000) as i64
        ],
        |r| r.get(0),
    )?)
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuditVerifyResult {
    pub ok: bool,
    pub checked: usize,
    pub first_bad_id: Option<i64>,
    pub reason: Option<String>,
}
impl Serialize for AuditVerifyResult {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        json!({"ok":self.ok,"checked":self.checked,"first_bad_id":self.first_bad_id,"reason":self.reason}).serialize(serializer)
    }
}
/// Borrowed connection; callers retain ownership of active transactions.
/// SQL errors reuse store::Error's Python class and SQLite message mapping.
pub struct AuditLog<'a> {
    pub conn: &'a Connection,
    clock: Box<dyn Fn() -> SystemTime + 'a>,
}
impl<'a> AuditLog<'a> {
    pub fn new(conn: &'a Connection) -> Self {
        Self::with_clock(conn, SystemTime::now)
    }
    pub fn with_clock(conn: &'a Connection, clock: impl Fn() -> SystemTime + 'a) -> Self {
        Self {
            conn,
            clock: Box::new(clock),
        }
    }
    /// Empty extra corresponds to omitted Python keyword arguments.
    pub fn record(
        &self,
        principal: &str,
        tool: &str,
        outcome: &str,
        reason: &str,
        extra: &Value,
    ) -> Result<String, Error> {
        let mut payload =
            json!({"principal":principal,"tool":tool,"outcome":outcome,"reason":reason});
        if extra.as_object().is_some_and(|v| !v.is_empty()) {
            payload["extra"] = extra.clone();
        }
        self.event("tool_call", &payload)
    }
    pub fn event(&self, event: &str, payload: &Value) -> Result<String, Error> {
        self.audit_append(event, payload, true)
    }
    pub fn audit_append(
        &self,
        event: &str,
        payload: &Value,
        commit: bool,
    ) -> Result<String, Error> {
        let owned = self.conn.is_autocommit();
        if owned {
            // Python catches OperationalError only, then attempts the deferred insert.
            if let Err(e) = self.conn.execute_batch("BEGIN IMMEDIATE") {
                let mapped = Error::from(e);
                if mapped.python_class() != "OperationalError" {
                    return Err(mapped);
                }
            }
        }
        let prev: String = self
            .conn
            .query_row(
                "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1",
                [],
                |r| r.get(0),
            )
            .optional()?
            .unwrap_or_else(|| GENESIS.into());
        let ts = now_iso((self.clock)())?;
        let body = canonical_json(payload, Some(&[]));
        let hash = crate::digest::sha256(format!("{prev}|{ts}|{event}|{body}").as_bytes());
        // Match CPython's implicit deferred transaction text, including its trailing space.
        if self.conn.is_autocommit() {
            self.conn.execute_batch("BEGIN ")?;
        }
        self.conn.execute(
            "INSERT INTO audit_log(ts, event, payload, prev_hash, hash) VALUES (?, ?, ?, ?, ?)",
            params![ts, event, body, prev, hash],
        )?;
        if commit && owned {
            self.conn.execute_batch("COMMIT")?;
        }
        Ok(hash)
    }
    pub fn audit_verify(&self) -> Result<AuditVerifyResult, Error> {
        let mut prev = GENESIS.to_string();
        let mut result = AuditVerifyResult {
            ok: true,
            checked: 0,
            first_bad_id: None,
            reason: None,
        };
        let mut statement = self.conn.prepare(
            "SELECT id, ts, event, payload, prev_hash, hash FROM audit_log ORDER BY id ASC",
        )?;
        let mut cursor = statement.query([])?;
        while let Some(row) = cursor.next()? {
            let id: i64 = row.get(0)?;
            let fields = (1..6)
                .map(|i| row.get::<_, String>(i))
                .collect::<Result<Vec<_>, _>>()?;
            let reason = if fields[3] != prev {
                Some(format!(
                    "row {id}: prev_hash mismatch (recorded={}..., expected={}...)",
                    fields[3].chars().take(12).collect::<String>(),
                    prev.chars().take(12).collect::<String>()
                ))
            } else if fields[4]
                != crate::digest::sha256(
                    format!("{prev}|{}|{}|{}", fields[0], fields[1], fields[2]).as_bytes(),
                )
            {
                Some(format!("row {id}: hash mismatch"))
            } else {
                None
            };
            if reason.is_some() {
                result.ok = false;
                result.first_bad_id = Some(id);
                result.reason = reason;
                return Ok(result);
            }
            prev = fields[4].clone();
            result.checked += 1;
        }
        Ok(result)
    }
    pub fn gc_scan(&self, dry_run: bool) -> Result<Value, Error> {
        let today = now_iso((self.clock)())?;
        let mut statement = self.conn.prepare("SELECT id FROM facts WHERE status = 'active' AND valid_to IS NOT NULL AND valid_to < ?")?;
        let ids = statement
            .query_map([&today[..10]], |r| r.get::<_, i64>(0))?
            .collect::<Result<Vec<_>, _>>()?;
        if !dry_run && !ids.is_empty() {
            if self.conn.is_autocommit() {
                self.conn.execute_batch("BEGIN")?;
            }
            let sql = format!(
                "UPDATE facts SET status = 'expired' WHERE id IN ({})",
                vec!["?"; ids.len()].join(",")
            );
            self.conn.execute(&sql, rusqlite::params_from_iter(&ids))?;
            self.conn.execute_batch("COMMIT")?;
        }
        let kept: i64 = self.conn.query_row(
            "SELECT COUNT(*) FROM facts WHERE status = 'active'",
            [],
            |r| r.get(0),
        )?;
        Ok(json!({"expired":ids.len(),"kept_active":kept}))
    }
}
