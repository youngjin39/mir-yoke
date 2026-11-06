//! Connection and migration parity with memory/store.py (vec disabled slice).
use rusqlite::{Connection as Sqlite, OpenFlags};
use std::{ffi::CString, fmt, path::Path, time::Duration};
#[derive(Debug)]
pub enum Error {
    Sql(rusqlite::Error),
    Io(std::io::Error),
    Nul(std::ffi::NulError),
    InvalidAlias(String),
    Snapshot(&'static str),
}
impl Error {
    pub fn python_hierarchy(&self) -> Vec<&'static str> {
        let mut classes = vec![self.python_class()];
        if matches!(self, Self::Snapshot(_)) {
            classes.push("RuntimeError");
        }
        classes.extend(["Exception", "BaseException", "object"]);
        classes
    }
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
            Self::InvalidAlias(_) => "ValueError",
            Self::Snapshot(_) => "ReadOnlySnapshotUnavailable",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Sql(rusqlite::Error::SqliteFailure(e, _))
                if e.code == rusqlite::ErrorCode::CannotOpen =>
            {
                f.write_str("unable to open database file")
            }
            Self::Sql(e) => e.fmt(f),
            Self::Io(e) => e.fmt(f),
            Self::Nul(_) => f.write_str("embedded null character"),
            Self::InvalidAlias(alias) => write!(f, "invalid SQL alias: {alias}"),
            Self::Snapshot(message) => f.write_str(message),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(match self {
            Self::Sql(e) => e,
            Self::Io(e) => e,
            Self::Nul(e) => e,
            Self::InvalidAlias(_) | Self::Snapshot(_) => return None,
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

pub fn current_fact_filter_sql(alias: &str) -> Result<String, Error> {
    if !alias
        .bytes()
        .enumerate()
        .all(|(i, b)| b == b'_' || b.is_ascii_alphabetic() || (i > 0 && b.is_ascii_digit()))
        || alias.is_empty()
    {
        return Err(Error::InvalidAlias(crate::executor_execute::repr(alias)));
    }
    Ok(format!(
        "AND NOT EXISTS (\n      SELECT 1 FROM facts terminal\n       WHERE terminal.subject_entity_id = {alias}.subject_entity_id\n         AND terminal.predicate = 'status' AND terminal.status = 'active'\n         AND terminal.polarity = 'asserted' AND (\n           lower(trim(terminal.object_literal)) IN ('archived', 'rejected', 'superseded', 'superseded-design', 'historical', 'historical-snapshot', 'historical-manual-snapshot', 'historical-ledger', 'applied-ledger-v1', 'done')\n           OR lower(trim(terminal.object_literal)) LIKE 'historical%'\n           OR lower(trim(terminal.object_literal)) LIKE 'superseded%'\n         ))"
    ))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SnapshotFileState {
    device: u64,
    inode: u64,
    size: u64,
    mtime_ns: i128,
    ctime_ns: i128,
}
impl SnapshotFileState {
    pub fn size(&self) -> u64 {
        self.size
    }
    pub fn fields(&self) -> [&'static str; 5] {
        ["device", "inode", "size", "mtime_ns", "ctime_ns"]
    }
}
#[cfg(unix)]
pub fn snapshot_file_state(path: &Path) -> Result<Option<SnapshotFileState>, Error> {
    let stat = match std::fs::metadata(path) {
        Ok(stat) => stat,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.into()),
    };
    Ok(Some(metadata_state(&stat)))
}
#[cfg(unix)]
fn metadata_state(stat: &std::fs::Metadata) -> SnapshotFileState {
    use std::os::unix::fs::MetadataExt;
    SnapshotFileState {
        device: stat.dev(),
        inode: stat.ino(),
        size: stat.len(),
        mtime_ns: i128::from(stat.mtime()) * 1_000_000_000 + i128::from(stat.mtime_nsec()),
        ctime_ns: i128::from(stat.ctime()) * 1_000_000_000 + i128::from(stat.ctime_nsec()),
    }
}
#[cfg(unix)]
pub fn snapshot_handle_state(file: &std::fs::File) -> Result<SnapshotFileState, Error> {
    Ok(metadata_state(&file.metadata()?))
}
// Python 3.12 stat uses creation time for ctime on Windows.
#[cfg(windows)]
pub fn snapshot_file_state(path: &Path) -> Result<Option<SnapshotFileState>, Error> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::{
        FILE_FLAG_BACKUP_SEMANTICS, FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE,
    };
    let file = match std::fs::OpenOptions::new()
        .access_mode(0)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
        .open(path)
    {
        Ok(file) => file,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.into()),
    };
    snapshot_handle_state(&file).map(Some)
}
#[cfg(windows)]
#[allow(unsafe_code)] // The existing Win32 call borrows an owned file handle.
pub fn snapshot_handle_state(file: &std::fs::File) -> Result<SnapshotFileState, Error> {
    use std::os::windows::{fs::MetadataExt, io::AsRawHandle};
    use windows_sys::Win32::Storage::FileSystem::{
        BY_HANDLE_FILE_INFORMATION, GetFileInformationByHandle,
    };
    let stat = file.metadata()?;
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    // SAFETY: file owns a live handle; info is writable for this synchronous call.
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let ns = |ticks| (i128::from(ticks) - 116_444_736_000_000_000i128) * 100;
    Ok(SnapshotFileState {
        device: u64::from(info.dwVolumeSerialNumber),
        inode: (u64::from(info.nFileIndexHigh) << 32) | u64::from(info.nFileIndexLow),
        size: stat.file_size(),
        mtime_ns: ns(stat.last_write_time()),
        ctime_ns: ns(stat.creation_time()),
    })
}
pub type SnapshotState = std::collections::BTreeMap<&'static str, Option<SnapshotFileState>>;
pub fn immutable_snapshot_state(path: &Path) -> Result<SnapshotState, Error> {
    let mut state = SnapshotState::new();
    for (key, suffix) in [("database", ""), ("wal", "-wal"), ("journal", "-journal")] {
        let mut name = path.as_os_str().to_os_string();
        name.push(suffix);
        state.insert(key, snapshot_file_state(Path::new(&name))?);
    }
    Ok(state)
}
pub fn assert_immutable_snapshot_state(path: &Path, expected: &SnapshotState) -> Result<(), Error> {
    let current = immutable_snapshot_state(path)?;
    for (key, message) in [
        (
            "wal",
            "immutable read refused because a non-empty SQLite WAL is present",
        ),
        (
            "journal",
            "immutable read refused because a non-empty SQLite rollback journal is present",
        ),
    ] {
        if current[key].is_some_and(|s| s.size > 0) {
            return Err(Error::Snapshot(message));
        }
    }
    if current != *expected {
        return Err(Error::Snapshot(
            "immutable read refused because SQLite database or journal files changed during the snapshot interval",
        ));
    }
    Ok(())
}
fn resolved(path: &Path) -> Result<std::path::PathBuf, Error> {
    match path.canonicalize() {
        Ok(path) => Ok(path),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(std::path::absolute(path)?),
        Err(e) => Err(e.into()),
    }
}
/// Optimistic validation, not a SQLite lock. Final validation also runs on body errors.
pub fn immutable_snapshot_guard<T>(
    path: &Path,
    body: impl FnOnce() -> Result<T, Error>,
) -> Result<T, Error> {
    let path = resolved(path)?;
    let before = immutable_snapshot_state(&path)?;
    assert_immutable_snapshot_state(&path, &before)?;
    let result = body();
    assert_immutable_snapshot_state(&path, &before)?;
    result
}
pub fn connect_read_only(path: &Path) -> Result<Connection, Error> {
    let path = resolved(path)?;
    let conn = immutable_snapshot_guard(&path, || {
        let uri = file_uri(path.as_os_str().as_encoded_bytes(), cfg!(windows));
        let raw = Sqlite::open_with_flags(
            format!("{uri}?mode=ro&immutable=1"),
            OpenFlags::SQLITE_OPEN_READ_ONLY
                | OpenFlags::SQLITE_OPEN_URI
                | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )?;
        raw.execute_batch("PRAGMA query_only=ON")?;
        Ok(raw)
    })?;
    Ok(Connection {
        conn,
        vec_available: false,
        vec_reason: "vec loading disabled by immutable reader",
    })
}

// Resolved native paths; the platform argument makes both URI grammars testable.
fn file_uri(path: &[u8], windows: bool) -> String {
    let normalized;
    let path = if windows {
        normalized = path
            .iter()
            .map(|&b| if b == b'\\' { b'/' } else { b })
            .collect::<Vec<_>>();
        normalized
            .strip_prefix(b"//?/UNC")
            .unwrap_or_else(|| normalized.strip_prefix(b"//?/").unwrap_or(&normalized))
    } else {
        path
    };
    let prefix = if windows && path.get(1) == Some(&b':') {
        "file:///"
    } else if windows && path.starts_with(b"//") {
        "file:"
    } else if windows {
        "file:/"
    } else {
        "file://"
    };
    let mut uri = prefix.to_string();
    for (i, b) in path.iter().enumerate() {
        if b.is_ascii_alphanumeric() || b"/-._~".contains(b) || (windows && i == 1 && *b == b':') {
            uri.push(char::from(*b));
        } else {
            uri.push_str(&format!("%{b:02X}"));
        }
    }
    uri
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn file_uri_matches_path_as_uri() {
        for (path, windows, expected) in [
            ("/tmp/a b/\u{e9}?#", false, "file:///tmp/a%20b/%C3%A9%3F%23"),
            (r"C:\a b\db", true, "file:///C:/a%20b/db"),
            (r"\\server\share\a b", true, "file://server/share/a%20b"),
            (r"\\?\C:\a b\db", true, "file:///C:/a%20b/db"),
            (
                r"\\?\UNC\server\share\a b",
                true,
                "file://server/share/a%20b",
            ),
        ] {
            assert_eq!(file_uri(path.as_bytes(), windows), expected);
        }
    }
}
