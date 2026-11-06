//! Connection and migration parity with memory/store.py (vec disabled slice).
use rusqlite::{Connection as Sqlite, OpenFlags};
use std::{ffi::CString, fmt, path::Path, time::Duration};
#[derive(Debug)]
pub enum Error {
    Sql(rusqlite::Error),
    Io(std::io::Error),
    Nul(std::ffi::NulError),
}
impl Error {
    pub fn python_class(&self) -> &'static str {
        match self {
            Self::Sql(rusqlite::Error::MultipleStatement) => "ProgrammingError",
            Self::Sql(rusqlite::Error::SqliteFailure(e, _))
                if e.code == rusqlite::ErrorCode::ConstraintViolation =>
            {
                "IntegrityError"
            }
            Self::Sql(_) => "OperationalError",
            Self::Io(_) => "OSError",
            Self::Nul(_) => "ValueError",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Sql(e) => e.fmt(f),
            Self::Io(e) => e.fmt(f),
            Self::Nul(_) => f.write_str("embedded null character"),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(match self {
            Self::Sql(e) => e,
            Self::Io(e) => e,
            Self::Nul(e) => e,
        })
    }
}
impl From<rusqlite::Error> for Error {
    fn from(e: rusqlite::Error) -> Self {
        Self::Sql(e)
    }
}
impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}
pub struct Connection {
    pub conn: Sqlite,
    pub vec_available: bool,
    pub vec_reason: &'static str,
}
pub fn connect(path: &Path, timeout: Option<f64>) -> Result<Connection, Error> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let conn = Sqlite::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_CREATE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    conn.busy_timeout(Duration::from_millis(
        (timeout.unwrap_or(5.0).max(0.0) * 1000.0) as u64,
    ))?;
    conn.execute_batch(
        "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;",
    )?;
    Ok(Connection {
        conn,
        vec_available: false,
        vec_reason: "vec loading disabled by caller",
    })
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MigrationEntry {
    pub version: String,
    pub name: String,
    pub body: String,
}
pub fn migrations() -> Vec<MigrationEntry> {
    macro_rules! embedded {
        ($($name:literal),*) => { vec![$(MigrationEntry {
            version: $name[..3].into(), name: $name.into(),
            body: include_str!(concat!("../../../../../src/mir/core/engine/memory/migrations/", $name)).into(),
        }),*] };
    }
    embedded!(
        "001_initial.sql",
        "002_metaswarm_fields.sql",
        "003_mir_additions.sql",
        "004_indexes_and_search.sql",
        "014_canonicalize_predicates.sql",
        "015_external_store.sql",
        "016_mir_sign_nonces.sql",
        "017_adr53_context_metadata.sql",
        "018_external_archive_history_globs.sql"
    )
}
pub fn discover(root: &Path) -> Result<Vec<MigrationEntry>, Error> {
    let pattern = regex::Regex::new(r"^([0-9]{3})_[a-z0-9_]+\.sql$")
        .map_err(|e| Error::Io(std::io::Error::other(e)))?;
    let mut entries = Vec::new();
    for entry in std::fs::read_dir(root)? {
        let entry = entry?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| std::io::Error::other("non-UTF-8 migration filename"))?;
        if let Some(m) = pattern.captures(&name) {
            entries.push(MigrationEntry {
                version: m[1].into(),
                name,
                body: std::fs::read_to_string(entry.path())?,
            });
        }
    }
    entries.sort_by(|a, b| a.version.cmp(&b.version));
    Ok(entries)
}
pub const SCHEMA_MIGRATIONS_DDL: &str = "CREATE TABLE IF NOT EXISTS schema_migrations (\n  version    TEXT PRIMARY KEY,\n  name       TEXT NOT NULL,\n  applied_at TEXT NOT NULL\n);";
pub fn complete_statements(body: &str) -> Result<Vec<String>, Error> {
    let (mut buffer, mut statements) = (String::new(), Vec::new());
    for line in body.split_inclusive('\n') {
        buffer.push_str(line);
        if complete(&buffer)? {
            statements.push(buffer.trim().into());
            buffer.clear();
        }
    }
    if !buffer.trim().is_empty() {
        statements.push(buffer.trim().into());
    }
    Ok(statements)
}
// SQLite's trigger-aware parser avoids a second SQL grammar. No connection access.
#[allow(unsafe_code)]
fn complete(sql: &str) -> Result<bool, Error> {
    let text = CString::new(sql).map_err(Error::Nul)?;
    // SAFETY: text owns a NUL-terminated buffer alive for this synchronous call.
    Ok(unsafe { rusqlite::ffi::sqlite3_complete(text.as_ptr()) } != 0)
}
pub fn apply_entries(conn: &Sqlite, entries: &[MigrationEntry]) -> Result<Vec<String>, Error> {
    if !conn.is_autocommit() {
        conn.execute_batch("COMMIT")?;
    }
    conn.execute_batch(SCHEMA_MIGRATIONS_DDL)?;
    let before: std::collections::HashSet<String> = conn
        .prepare("SELECT version FROM schema_migrations")?
        .query_map([], |r| r.get(0))?
        .collect::<Result<_, _>>()?;
    let mut applied = Vec::new();
    for m in entries {
        if before.contains(&m.version) {
            continue;
        }
        let tx = conn.unchecked_transaction()?;
        for statement in complete_statements(&m.body)? {
            tx.execute(&statement, [])?;
        }
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(std::io::Error::other)?;
        tx.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%S', ?, 'unixepoch') || printf('.%06d+00:00', ?))", rusqlite::params![m.version, m.name, now.as_secs().to_string(), now.subsec_micros()])?;
        tx.commit()?;
        applied.push(m.version.clone());
    }
    Ok(applied)
}
pub fn apply_migrations(conn: &Sqlite) -> Result<Vec<String>, Error> {
    apply_entries(conn, &migrations())
}
pub fn schema_version(conn: &Sqlite) -> Result<Option<String>, Error> {
    Ok(
        conn.query_row("SELECT MAX(version) FROM schema_migrations", [], |r| {
            r.get(0)
        })?,
    )
}
pub fn latest_schema_version() -> Option<String> {
    migrations().last().map(|m| m.version.clone())
}
