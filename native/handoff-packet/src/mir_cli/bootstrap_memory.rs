//! Explicit-path bootstrap memory validation, projections and isolated staging.
use super::{Error, Host, authored};
use crate::executor_brief_render::python_value_repr;
use crate::mir_cli::memory;
use crate::mir_core::memory::store;
use rusqlite::backup::{Backup, StepResult};
use rusqlite::{Connection, OpenFlags, OptionalExtension};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

fn sql_error(error: rusqlite::Error) -> Error {
    store_error(store::Error::Sql(error))
}

pub(super) fn store_error(error: store::Error) -> Error {
    Error::new(error.python_class(), error.to_string())
}

/// Opens the supplied memory DB using the Python store's optional vec behavior.
pub(super) fn connect(path: &Path) -> Result<store::Connection, Error> {
    store::connect(
        path,
        store::ConnectOptions {
            timeout: None,
            vec_loading: store::VecLoading::Bundled,
        },
    )
    .map_err(store_error)
}

/// Creates a distinct snapshot in the source directory, including committed WAL data.
pub fn stage_memory_db(db_path: &Path) -> Result<PathBuf, Error> {
    let parent = db_path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|error| authored::io_error(parent, error))?;
    let temporary = tempfile::Builder::new()
        .prefix(".memory.bootstrap.")
        .suffix(".db")
        .tempfile_in(parent)
        .map_err(|error| authored::io_error(parent, error))?;
    let (file, staged_path) = temporary
        .keep()
        .map_err(|error| authored::io_error(parent, error.error))?;
    drop(file);
    if !db_path.exists() {
        return Ok(staged_path);
    }
    let source = Connection::open_with_flags(
        db_path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(sql_error)?;
    // CPython `source.backup(destination)`: step(-1) copies every page and
    // retries after 250 ms while the source is busy or locked.
    let mut destination = Connection::open(&staged_path).map_err(sql_error)?;
    let backup = Backup::new(&source, &mut destination).map_err(sql_error)?;
    while backup.step(-1).map_err(sql_error)? != StepResult::Done {
        std::thread::sleep(Duration::from_millis(250));
    }
    Ok(staged_path)
}

/// Builds both generated sections before reading the existing project files.
pub fn build_projection_updates(
    root: &Path,
    db_path: &Path,
    host: &mut impl Host,
) -> Result<BTreeMap<PathBuf, String>, Error> {
    let targets = {
        let connection = host.bootstrap_memory_connect(db_path)?;
        [
            (
                root.join("docs/memory-map.md"),
                memory::render_memory_map_section(&connection.conn).map_err(sql_error)?,
            ),
            (
                root.join("tasks/lessons.md"),
                memory::render_lessons_section(&connection.conn).map_err(sql_error)?,
            ),
        ]
    };
    let mut updates = BTreeMap::new();
    for (path, generated) in targets {
        let existing = if path.is_file() {
            authored::read_text(&path)?
        } else {
            String::new()
        };
        updates.insert(path, memory::inject_markers(&existing, &generated));
    }
    Ok(updates)
}

fn archives(onboarding: &Value) -> Result<Vec<&Value>, Error> {
    if !onboarding.is_object() {
        return Err(authored::attribute_error(onboarding, "get"));
    }
    let Some(value) = onboarding.get("archives") else {
        return Ok(Vec::new());
    };
    match value {
        Value::Array(items) => Ok(items.iter().collect()),
        Value::Object(items) => Ok(items.keys().map(|_| &Value::Null).collect()),
        Value::String(text) => Ok(text.chars().map(|_| &Value::Null).collect()),
        _ => Err(Error::new(
            "TypeError",
            format!("'{}' object is not iterable", python_type(value)),
        )),
    }
}

fn python_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(number) if number.is_f64() => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// Checks each authored FTS query against its exact archive slug and relative path.
pub fn validate_content_memory_acceptance(
    _root: &Path,
    db_path: &Path,
    slug: &str,
    onboarding: &Value,
    host: &mut impl Host,
) -> Result<(Vec<String>, Value), Error> {
    let mut errors = Vec::new();
    let mut results = Vec::new();
    let expected_archive = format!("{slug}-content");
    let connection = host.bootstrap_memory_connect(db_path)?;
    let entries = archives(onboarding)?;
    for archive in &entries {
        if !archive.is_object() {
            errors.push("content onboarding archive entry must be an object".to_owned());
            continue;
        }
        let classification = &archive["classification"];
        let acceptance = &archive["acceptance"];
        if !acceptance.is_object() {
            errors.push(format!(
                "content classification {} lacks acceptance",
                python_value_repr(classification)
            ));
            continue;
        }
        let (Some(query), Some(expected_path)) = (
            acceptance["query"].as_str(),
            acceptance["expected_path"].as_str(),
        ) else {
            errors.push(format!(
                "content classification {} has invalid acceptance",
                python_value_repr(classification)
            ));
            continue;
        };
        let passed = connection
            .conn
            .query_row(
                concat!(
                    "SELECT a.slug, d.relative_path FROM external_chunks_fts f ",
                    "JOIN external_chunks c ON c.id = f.rowid ",
                    "JOIN external_documents d ON d.id = c.document_id ",
                    "JOIN external_archives a ON a.id = d.archive_id ",
                    "WHERE external_chunks_fts MATCH ? ",
                    "AND a.slug = ? AND d.relative_path = ? LIMIT 1"
                ),
                [query, &expected_archive, expected_path],
                |_| Ok(()),
            )
            .optional()
            .map_err(sql_error)?
            .is_some();
        results.push(json!({
            "classification": classification, "query": query,
            "expected_path": expected_path, "status": if passed { "pass" } else { "fail" }
        }));
        if !passed {
            errors.push(format!(
                "project-specific memory query returned no matching path for {}: {} -> {}",
                python_value_repr(classification),
                crate::executor_execute::repr(query),
                crate::executor_execute::repr(expected_path)
            ));
        }
    }
    drop(connection);
    let classifications: Vec<_> = entries
        .into_iter()
        .filter(|item| item.is_object())
        .map(|item| {
            json!({
                "classification": item["classification"], "path": item["path"],
                "formats": item["formats"], "document_count": item["document_count"],
                "indexed_document_count": item["indexed_document_count"]
            })
        })
        .collect();
    let receipt = json!({
        "status": if errors.is_empty() { "pass" } else { "fail" },
        "manifest": "config/content-onboarding.json", "archive_slug": expected_archive,
        "classifications": classifications, "queries": results
    });
    Ok((errors, receipt))
}
