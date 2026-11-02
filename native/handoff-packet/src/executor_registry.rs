//! Native writes matching the Python JobRegistry contract.
use rusqlite::{Connection, params, params_from_iter, types::Value as SqlValue};
use serde_json::Value;
use std::{
    fs, io,
    path::{Path, PathBuf},
};

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Sql(rusqlite::Error),
    Text(crate::Error),
    Shape,
}
impl From<io::Error> for Error {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}
impl From<rusqlite::Error> for Error {
    fn from(e: rusqlite::Error) -> Self {
        Self::Sql(e)
    }
}
impl From<crate::Error> for Error {
    fn from(e: crate::Error) -> Self {
        Self::Text(e)
    }
}
pub type Result<T> = std::result::Result<T, Error>;
const DDL: &str = include_str!("executor_registry.sql");
const EXTRA: &[&str] = &[
    "target_agent",
    "execution_backend",
    "resolved_model",
    "resolved_reasoning_effort",
    "agent_definition_path",
    "agent_definition_sha256",
    "identity_json",
    "dispatch_options_json",
    "ai_run_metadata",
    "dispatch_brief_path",
    "allow_harness_self_modify",
    "resume_count",
    "last_resumed_at",
];
const COLUMNS: &[&str] = &[
    "job_id",
    "change_id",
    "category",
    "family",
    "repo_root",
    "codex_args",
    "dispatch_brief_path",
    "allow_harness_self_modify",
    "resume_count",
    "last_resumed_at",
    "timeout_seconds",
    "status",
    "exit_code",
    "stdout",
    "stderr",
    "duration_seconds",
    "started_at",
    "completed_at",
    "cancel_requested",
    "target_agent",
    "execution_backend",
    "resolved_model",
    "resolved_reasoning_effort",
    "agent_definition_path",
    "agent_definition_sha256",
    "identity_json",
    "dispatch_options_json",
    "ai_run_metadata",
];

fn quoted(text: &str) -> Result<String> {
    let encoded = serde_json::to_string(text).map_err(|_| Error::Shape)?;
    let mut out = String::new();
    for c in encoded.chars() {
        if c.is_ascii() && c != '\u{7f}' {
            out.push(c);
        } else {
            for unit in c.encode_utf16(&mut [0; 2]) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    Ok(out)
}
pub(crate) fn python_float(value: f64) -> Result<String> {
    let encoded = serde_json::to_string(&value).map_err(|_| Error::Shape)?;
    let sign = if encoded.starts_with('-') { "-" } else { "" };
    let magnitude = encoded.trim_start_matches('-');
    let (mantissa, exponent) = match magnitude.split_once(['e', 'E']) {
        Some((m, e)) => (m, e.parse::<i32>().map_err(|_| Error::Shape)?),
        None => (magnitude, 0),
    };
    let decimal = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let all: String = mantissa.chars().filter(|c| *c != '.').collect();
    let Some(first) = all.find(|c| c != '0') else {
        return Ok(format!("{sign}0.0"));
    };
    let exponent = exponent + decimal - first as i32 - 1;
    let digits = all[first..].trim_end_matches('0');
    if !(-4..16).contains(&exponent) {
        let fraction = if digits.len() > 1 {
            format!(".{}", &digits[1..])
        } else {
            String::new()
        };
        return Ok(format!(
            "{sign}{}{fraction}e{}{:02}",
            &digits[..1],
            if exponent < 0 { '-' } else { '+' },
            exponent.abs()
        ));
    }
    if exponent < 0 {
        return Ok(format!(
            "{sign}0.{}{}",
            "0".repeat((-exponent - 1) as usize),
            digits
        ));
    }
    let decimal = (exponent + 1) as usize;
    if decimal >= digits.len() {
        return Ok(format!(
            "{sign}{digits}{}.0",
            "0".repeat(decimal - digits.len())
        ));
    }
    Ok(format!(
        "{sign}{}.{}",
        &digits[..decimal],
        &digits[decimal..]
    ))
}

pub(crate) fn json(value: &Value, spaced: bool) -> Result<String> {
    Ok(match value {
        Value::String(s) => quoted(s)?,
        Value::Array(items) => format!(
            "[{}]",
            items
                .iter()
                .map(|v| json(v, spaced))
                .collect::<Result<Vec<_>>>()?
                .join(if spaced { ", " } else { "," })
        ),
        Value::Object(items) => format!(
            "{{{}}}",
            items
                .iter()
                .map(|(k, v)| Ok(format!(
                    "{}{}{}",
                    quoted(k)?,
                    if spaced { ": " } else { ":" },
                    json(v, spaced)?
                )))
                .collect::<Result<Vec<_>>>()?
                .join(if spaced { ", " } else { "," })
        ),
        Value::Number(n) if n.is_f64() => python_float(n.as_f64().ok_or(Error::Shape)?)?,
        _ => value.to_string(),
    })
}
fn sql(value: &Value) -> Result<SqlValue> {
    Ok(match value {
        Value::Null => SqlValue::Null,
        Value::Bool(b) => SqlValue::Integer(i64::from(*b)),
        Value::String(s) => SqlValue::Text(s.clone()),
        Value::Number(n) => {
            if let Some(n) = n.as_i64() {
                SqlValue::Integer(n)
            } else {
                SqlValue::Real(n.as_f64().ok_or(Error::Shape)?)
            }
        }
        _ => return Err(Error::Shape),
    })
}
fn redact(pattern: &str, text: &str, replacement: &str) -> Result<String> {
    let mut out = String::new();
    let mut end = 0;
    for m in crate::captures(pattern, text, true)? {
        out.push_str(&text[end..m.start]);
        out.push_str(replacement);
        end = m.end;
    }
    out.push_str(&text[end..]);
    Ok(out)
}
/// Redact before truncating by Unicode scalar count, as in jobs.py.
pub fn sanitize(text: &str) -> Result<String> {
    let mut out = redact(
        r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----(?s:.)*?(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\z)",
        text,
        "[REDACTED_PRIVATE_KEY]",
    )?;
    let secret = r"(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?key|authorization|bearer|password|secret|token)(?:[_-]?key)?";
    let pat = format!(
        r#"\b({secret})(["']?)(\s*(?:=|:)\s*)("[^"]*"|'[^']*'|(?:(?:bearer|basic)\s+)?[^\s,;]+)"#
    );
    let mut replaced = String::new();
    let mut end = 0;
    for m in crate::captures(&pat, &out, true)? {
        replaced.push_str(&out[end..m.start]);
        let group = |i: usize| m.groups[i].as_deref().unwrap_or("");
        replaced.push_str(group(1));
        if group(2).is_empty() {
            replaced.push_str("=[REDACTED]");
        } else {
            replaced.push_str(group(2));
            replaced.push_str(group(3));
            let quote = group(4).chars().next().filter(|c| matches!(c, '\'' | '"'));
            if let Some(c) = quote {
                replaced.push(c);
            }
            replaced.push_str("[REDACTED]");
            if let Some(c) = quote {
                replaced.push(c);
            }
        }
        end = m.end;
    }
    replaced.push_str(&out[end..]);
    out = redact(r"\bbearer\s+[^\s,;]+", &replaced, "Bearer [REDACTED]")?;
    out = redact(
        r"\b(?:sk[-_](?:proj[-_]|svcacct[-_]|ant[-_])?[a-z0-9_-]{12,}|(?:gh[pousr]|github_pat)_[a-z0-9_]{20,}|xox[baprs]-[a-z0-9-]{12,}|AKIA[A-Z0-9]{16}|AIza[0-9A-Za-z_-]{20,})",
        &out,
        "[REDACTED_TOKEN]",
    )?;
    const MARKER: &str = "\n...[truncated]...\n";
    if out.chars().count() > 16384 {
        out = out.chars().take(16384 - MARKER.len()).collect::<String>() + MARKER;
    }
    Ok(out)
}
fn private(path: &Path) -> Result<()> {
    match fs::symlink_metadata(path) {
        Ok(meta) if meta.is_file() => {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
            }
            #[cfg(windows)]
            {
                // Like Python chmod(0600), Windows changes the read-only
                // attribute here; it does not replace inherited ACLs.
                let mut permissions = meta.permissions();
                // Clearing the attribute is the intent; the lint targets Unix modes.
                #[allow(clippy::permissions_set_readonly_false)]
                permissions.set_readonly(false);
                fs::set_permissions(path, permissions)?;
            }
            Ok(())
        }
        Ok(_) => Ok(()),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e.into()),
    }
}
pub struct JobRegistry {
    db: Connection,
    path: PathBuf,
}
impl JobRegistry {
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
            fs::create_dir_all(parent)?;
        }
        let mut options = fs::OpenOptions::new();
        options.read(true).write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(path) {
            Ok(_) => (),
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {
                if !fs::symlink_metadata(path)?.is_file() {
                    return Err(Error::Shape);
                }
                private(path)?;
            }
            Err(e) => return Err(e.into()),
        }
        let resolved = crate::supply::plain(fs::canonicalize(path)?);
        let db = Connection::open_with_flags(
            &resolved,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_WRITE | rusqlite::OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )?;
        db.busy_timeout(std::time::Duration::from_secs(5))?;
        db.execute_batch(DDL)?;
        let names = db
            .prepare("PRAGMA table_info(jobs)")?
            .query_map([], |r| r.get::<_, String>(1))?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        db.execute_batch("BEGIN")?;
        for name in EXTRA {
            if !names.iter().any(|n| n == name) {
                let kind = if matches!(*name, "allow_harness_self_modify" | "resume_count") {
                    "INTEGER NOT NULL DEFAULT 0"
                } else {
                    "TEXT"
                };
                if let Err(e) =
                    db.execute_batch(&format!("ALTER TABLE jobs ADD COLUMN {name} {kind}"))
                {
                    db.execute_batch("ROLLBACK")?;
                    return Err(e.into());
                }
            }
        }
        db.execute_batch("COMMIT")?;
        let registry = Self {
            db,
            path: path.to_owned(),
        };
        registry.protect()?;
        Ok(registry)
    }
    pub fn connection(&self) -> &Connection {
        &self.db
    }
    fn protect(&self) -> Result<()> {
        for suffix in ["", "-journal", "-shm", "-wal"] {
            let mut path = self.path.as_os_str().to_owned();
            path.push(suffix);
            private(Path::new(&path))?;
        }
        Ok(())
    }
    fn write(&self, query: &str, values: &[SqlValue]) -> Result<usize> {
        let changed = self.db.execute(query, params_from_iter(values))?;
        self.protect()?;
        Ok(changed)
    }
    /// Insert a complete serialized Python JobRecord (including its defaults).
    pub fn insert(&self, record: &Value) -> Result<()> {
        let mut values = Vec::new();
        for name in COLUMNS {
            let value = &record[*name];
            values.push(match *name {
                "codex_args" => {
                    let args = value
                        .as_array()
                        .ok_or(Error::Shape)?
                        .iter()
                        .map(|v| Ok(Value::String(sanitize(v.as_str().ok_or(Error::Shape)?)?)))
                        .collect::<Result<Vec<_>>>()?;
                    SqlValue::Text(json(&Value::Array(args), true)?)
                }
                "ai_run_metadata" if !value.is_null() => SqlValue::Text(json(value, false)?),
                "stdout" | "stderr" if !value.is_null() => {
                    SqlValue::Text(sanitize(value.as_str().ok_or(Error::Shape)?)?)
                }
                _ => sql(value)?,
            });
        }
        let placeholders = vec!["?"; COLUMNS.len()].join(",");
        self.write(
            &format!(
                "INSERT INTO jobs ({}) VALUES ({placeholders})",
                COLUMNS.join(",")
            ),
            &values,
        )?;
        Ok(())
    }
    pub fn update_route_metadata(
        &self,
        id: &str,
        backend: &Value,
        model: &Value,
        effort: &Value,
    ) -> Result<()> {
        self.write("UPDATE jobs SET execution_backend=?,resolved_model=?,resolved_reasoning_effort=? WHERE job_id=?", &[sql(backend)?,sql(model)?,sql(effort)?,SqlValue::Text(id.into())])?;
        Ok(())
    }
    pub fn update_ai_run_metadata(&self, id: &str, metadata: &Value) -> Result<()> {
        let value = if metadata.is_null() {
            SqlValue::Null
        } else {
            SqlValue::Text(json(metadata, false)?)
        };
        self.write(
            "UPDATE jobs SET ai_run_metadata=? WHERE job_id=?",
            &[value, SqlValue::Text(id.into())],
        )?;
        Ok(())
    }
    pub fn update_status(&self, id: &str, status: &str, options: &Value) -> Result<()> {
        let mut sets = vec!["status=?".to_owned()];
        let mut values = vec![SqlValue::Text(status.into())];
        for name in [
            "exit_code",
            "stdout",
            "stderr",
            "duration_seconds",
            "completed_at",
        ] {
            let value = &options[name];
            if !value.is_null() {
                sets.push(format!("{name}=?"));
                values.push(if matches!(name, "stdout" | "stderr") {
                    SqlValue::Text(sanitize(value.as_str().ok_or(Error::Shape)?)?)
                } else {
                    sql(value)?
                });
            } else if options["clear_existing_result"] == true {
                sets.push(format!("{name}=NULL"));
            }
        }
        values.push(SqlValue::Text(id.into()));
        self.write(
            &format!("UPDATE jobs SET {} WHERE job_id=?", sets.join(",")),
            &values,
        )?;
        Ok(())
    }
    pub fn cancel(&self, id: &str) -> Result<bool> {
        Ok(self.write(
            "UPDATE jobs SET cancel_requested=1 WHERE job_id=?",
            &[SqlValue::Text(id.into())],
        )? > 0)
    }
    pub fn mark_resumed(&self, id: &str, at: &str) -> Result<()> {
        self.write("UPDATE jobs SET resume_count=COALESCE(resume_count,0)+1,last_resumed_at=?,status='running',exit_code=NULL,stdout=NULL,stderr=NULL,duration_seconds=NULL,completed_at=NULL,cancel_requested=0 WHERE job_id=?",&[SqlValue::Text(at.into()),SqlValue::Text(id.into())])?;
        Ok(())
    }
    pub fn record_artifact_sweep(
        &self,
        id: &str,
        path: &str,
        files: i64,
        bytes: i64,
        at: &str,
    ) -> Result<()> {
        self.db.execute(
            "INSERT INTO artifact_sweeps (job_id,path,files,bytes,swept_at) VALUES (?,?,?,?,?)",
            params![id, path, files, bytes, at],
        )?;
        self.protect()
    }
}
