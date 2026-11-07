//! Explicit-input defaults for the bootstrap coordinator's library host.
//!
//! Not yet oracle-proven: the core adoption mirrors here (`load_profile`, `load_boundary`,
//! `is_provider_owner`, `apply_adopter_slim`, `rollback_adopter_slim` and their helpers) are
//! scripted in every bootstrap-main record. They need the core adoption family's own frozen
//! records before any caller switch relies on them.
use super::{Error, Host, authored, memory};
use crate::mir_core::{config::loader, memory::external_store::ExternalStore};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::{collections::BTreeMap, collections::BTreeSet, fs, io::Write};

fn config_error(error: loader::ConfigLoadError) -> Error {
    Error::new(error.class, error.message)
}

pub(super) fn load_config(root: &Path, home: &Path) -> Result<Value, Error> {
    loader::load_config(Some(root), home, root)
        .map(|config| config.to_dict())
        .map_err(config_error)
}

pub(super) fn resolve_memory_db(root: &Path, cfg: &Value, home: &Path) -> Result<PathBuf, Error> {
    let config = loader::ResolvedConfig::from_dict(cfg)
        .map_err(|e| config_error(loader::validation_error("ResolvedConfig", cfg, e)))?;
    loader::resolve_memory_db(root, &config, home).map_err(config_error)
}

pub(super) fn load_profile(root: &Path) -> Result<Value, Error> {
    let result = (|| {
        let text = authored::read_text(&root.join(".mir/repo-profile.toml"))?;
        let profile: toml::Value = toml::from_str(&text).map_err(|e| {
            Error::new(
                "TOMLDecodeError",
                crate::mir_core::tomllib::tomllib_error(&e, &text),
            )
        })?;
        serde_json::to_value(profile).map_err(|e| Error::new("ValueError", e.to_string()))
    })();
    let profile: Value = result.map_err(|e: Error| {
        if e.class == "UnicodeDecodeError" {
            return e;
        }
        Error::new(
            "BoundaryError",
            format!("cannot classify adopter payload without a readable Profile: {e}"),
        )
    })?;
    if !profile["repo"].is_object() {
        return Err(Error::new(
            "BoundaryError",
            "cannot classify adopter payload because Profile [repo] is missing",
        ));
    }
    Ok(profile)
}

fn relative(value: &Value) -> Result<String, Error> {
    let invalid = || {
        Error::new(
            "BoundaryError",
            format!(
                "invalid adopter boundary path: {}",
                crate::executor_brief_render::python_value_repr(value)
            ),
        )
    };
    let text = value
        .as_str()
        .filter(|s| !s.is_empty() && !s.contains('\\'))
        .ok_or_else(invalid)?;
    if text.starts_with('/') || text.split('/').any(|p| p == "..") {
        return Err(Error::new(
            "BoundaryError",
            format!(
                "unsafe adopter boundary path: {}",
                crate::executor_execute::repr(text)
            ),
        ));
    }
    let parts: Vec<_> = text
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    Ok(if parts.is_empty() {
        ".".into()
    } else {
        parts.join("/")
    })
}

pub(super) fn load_boundary(root: &Path, host: &mut impl Host) -> Result<Value, Error> {
    let path = root.join("config/adopter-boundary.json");
    let mut boundary = authored::json_text(&path).map_err(|e| {
        if e.class == "UnicodeDecodeError" {
            return e;
        }
        Error::new(
            "BoundaryError",
            format!("cannot read {}: {e}", path.display()),
        )
    })?;
    if !boundary.is_object()
        || !(boundary["schema_version"].as_f64() == Some(1.0) || boundary["schema_version"] == true)
    {
        return Err(Error::new(
            "BoundaryError",
            format!("{} must be a schema_version=1 object", path.display()),
        ));
    }
    if let Some(schema_ref) = boundary["$schema"].as_str() {
        let schema = authored::json_text(
            &path
                .parent()
                .ok_or_else(|| slim("missing parent directory"))?
                .join(schema_ref),
        )
        .map_err(|e| {
            if e.class == "UnicodeDecodeError" {
                e
            } else {
                Error::new("BoundaryError", format!("invalid {}: {e}", path.display()))
            }
        })?;
        host.validate_boundary_schema(&boundary, &schema)
            .map_err(|e| {
                if e.class == "ValidationError" {
                    Error::new("BoundaryError", format!("invalid {}: {e}", path.display()))
                } else {
                    e
                }
            })?;
    }
    let markers = boundary["provider_markers"]
        .as_array_mut()
        .filter(|v| !v.is_empty())
        .ok_or_else(|| {
            Error::new(
                "BoundaryError",
                "config/adopter-boundary.json requires non-empty provider_markers",
            )
        })?;
    for marker in markers {
        *marker = json!(relative(marker)?);
    }
    let markers = boundary["provider_text_markers"]
        .as_array_mut()
        .ok_or_else(|| {
            Error::new(
                "BoundaryError",
                "config/adopter-boundary.json requires provider_text_markers",
            )
        })?;
    for marker in markers {
        if !marker.is_object() {
            return Err(Error::new(
                "BoundaryError",
                "provider_text_markers entries must be objects",
            ));
        }
        marker["path"] = json!(relative(&marker["path"])?);
        if !marker["contains"].as_str().is_some_and(|s| !s.is_empty()) {
            return Err(Error::new(
                "BoundaryError",
                "provider text markers require non-empty contains",
            ));
        }
    }
    Ok(boundary)
}

pub(super) fn is_provider_owner(profile: &Value, boundary: &Value) -> Result<bool, Error> {
    let owners = boundary["provider_owners"].as_array().ok_or_else(|| {
        Error::new(
            "BoundaryError",
            "config/adopter-boundary.json requires provider_owners",
        )
    })?;
    Ok(owners.iter().any(|owner| {
        owner.is_object()
            && profile["repo"]["slug"] == owner["slug"]
            && owner["repository_types"]
                .as_array()
                .is_some_and(|types| types.contains(&profile["repo"]["repository_type"]))
    }))
}

pub(super) fn abspath(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for part in path.components() {
        match part {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                normalized.pop();
            }
            part => normalized.push(part.as_os_str()),
        }
    }
    normalized
}

pub(super) fn context_main(
    root: &Path,
    db: &Path,
    home: &Path,
    now: &str,
) -> Result<(i32, String), Error> {
    let cfg = load_config(root, home)?;
    let connection = memory::connect(db)?;
    let clock = || now.to_owned();
    let store =
        ExternalStore::new(&connection, &clock).map_err(|e| Error::new(e.kind, e.message))?;
    crate::mir_cli::context::do_sync(&store, &cfg, root, home)
        .map_err(|e| Error::new(e.kind, e.message))
}

pub(super) fn run_doctor(root: &Path, db: &Path, home: &Path) -> Result<(i32, Value), Error> {
    crate::mir_cli::memory::run_doctor(root, Some(db), home, std::time::SystemTime::now, |path| {
        crate::mir_core::memory::store::connect(
            path,
            crate::mir_core::memory::store::ConnectOptions {
                timeout: None,
                vec_loading: crate::mir_core::memory::store::VecLoading::Bundled,
            },
        )
    })
    .map_err(|e| Error::new(e.python_class(), e.to_string()))
}

const JOURNAL: &str = ".mir/slim-transaction.json";
const LOCK: &str = ".mir/slim.lock";
fn slim(message: impl Into<String>) -> Error {
    Error::new("SlimError", message)
}
fn slim_io(error: impl std::fmt::Display) -> Error {
    slim(error.to_string())
}
fn safe_file(root: &Path, path: &Path) -> bool {
    super::release::is_safe_existing_project_file(root, path)
}
fn slim_root(root: &Path, host: &mut impl Host) -> Result<PathBuf, Error> {
    let platform = host.platform_system();
    if platform == "Windows" {
        return Err(slim(concat!(
            "Native Windows adopter slim is unsupported; run setup.sh inside WSL ",
            "or use agent-guided existing-repository/reference adaptation"
        )));
    }
    if platform != "Darwin" && platform != "Linux" {
        return Err(slim(concat!(
            "Adopter slim supports macOS, Linux, and WSL; use agent-guided ",
            "existing-repository/reference adaptation on this platform"
        )));
    }
    let root = fs::canonicalize(host.expanduser(root)?).map_err(slim_io)?;
    safe_directory(
        &root,
        &root.join(".mir"),
        "slim requires a real .mir directory",
    )?;
    Ok(root)
}
fn safe_directory(root: &Path, path: &Path, label: &str) -> Result<(), Error> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| slim(format!("{label} escapes the adopter repository")))?;
    let mut current = root.to_owned();
    for part in relative.components() {
        current.push(part);
        let metadata = fs::symlink_metadata(&current).map_err(slim_io)?;
        if metadata.is_symlink() {
            return Err(slim(format!("{label} contains a symlinked path component")));
        }
    }
    if !path.is_dir() || !fs::canonicalize(path).map_err(slim_io)?.starts_with(root) {
        return Err(slim(format!("{label} is not a real adopter directory")));
    }
    Ok(())
}
fn safe_parent(root: &Path, path: &Path) -> bool {
    let Ok(relative) = path.strip_prefix(root) else {
        return false;
    };
    let mut current = root.to_owned();
    for part in relative.components() {
        current.push(part);
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.is_symlink() || !metadata.is_dir() => return false,
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                if fs::create_dir(&current).is_err() {
                    return false;
                }
            }
            Err(_) => return false,
        }
    }
    true
}
fn prune(path: &Path, root: &Path) {
    let mut current = path.parent();
    while let Some(path) = current.filter(|p| *p != root && p.starts_with(root)) {
        if fs::remove_dir(path).is_err() {
            break;
        }
        current = path.parent();
    }
}
fn present(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}
fn unlink(path: &Path) -> Result<(), Error> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(slim_io(e)),
    }
}
fn atomic_journal(root: &Path, journal: &Value, host: &mut impl Host) -> Result<(), Error> {
    let path = root.join(JOURNAL);
    let body = format!("{}\n", authored::pretty(journal, true)?);
    authored::atomic_write_with(&path, &body, true, |source, destination| {
        host.replace(source, destination)
    })
}
fn load_journal(root: &Path) -> Result<Option<Value>, Error> {
    let path = root.join(JOURNAL);
    if path.is_symlink() {
        return Err(slim("cannot recover unsafe slim journal symlink"));
    }
    if !path.exists() {
        return Ok(None);
    }
    if !path.is_file() {
        return Err(slim("cannot recover non-file slim journal"));
    }
    let mut journal = authored::json_text(&path)
        .map_err(|e| slim(format!("cannot recover invalid slim journal: {e}")))?;
    let valid_id = journal["transaction_id"].as_str().is_some_and(|id| {
        id.len() == 32
            && id
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    });
    if !journal.is_object() || !valid_id || !journal["paths"].is_array() {
        return Err(slim("cannot recover malformed slim journal"));
    }
    for path in journal["paths"]
        .as_array_mut()
        .ok_or_else(|| slim("cannot recover malformed slim journal"))?
    {
        *path = json!(relative(path).map_err(|e| slim(e.message.replace("boundary", "payload")))?);
    }
    Ok(Some(journal))
}
fn rollback_journal(root: &Path, journal: &Value) -> Result<Vec<String>, Error> {
    safe_directory(
        root,
        &root.join(".mir"),
        "slim requires a real .mir directory",
    )?;
    let quarantine = root.join(".mir/slim-quarantine").join(
        journal["transaction_id"]
            .as_str()
            .ok_or_else(|| slim("cannot recover malformed slim journal"))?,
    );
    let mut errors = Vec::new();
    for relative in journal["paths"]
        .as_array()
        .ok_or_else(|| slim("invalid array"))?
        .iter()
        .rev()
        .filter_map(Value::as_str)
    {
        let source = root.join(relative);
        let destination = quarantine.join(relative);
        if present(&source) && !present(&destination) {
            continue;
        }
        let error = if present(&source) || !present(&destination) {
            Some("ambiguous rollback state".to_owned())
        } else if !safe_file(root, &destination) {
            Some("quarantine source is unsafe".into())
        } else if !safe_parent(
            root,
            source
                .parent()
                .ok_or_else(|| slim("missing source parent"))?,
        ) {
            Some("restore parent is unsafe".into())
        } else {
            fs::rename(&destination, &source)
                .err()
                .map(|e| e.to_string())
        };
        if let Some(error) = error {
            errors.push(format!("{relative}: {error}"));
        }
    }
    if errors.is_empty() {
        prune(&quarantine.join("placeholder"), &root.join(".mir"));
        unlink(&root.join(JOURNAL))?;
        unlink(&root.join(LOCK))?;
    }
    Ok(errors)
}
fn recover(root: &Path, host: &mut impl Host) -> Result<(), Error> {
    let journal = load_journal(root)?;
    let lock = root.join(LOCK);
    if present(&lock) && !safe_file(root, &lock) {
        return Err(slim("cannot recover unsafe slim lock"));
    }
    if let Some(journal) = journal {
        if let Some(pid) = journal["pid"].as_i64().filter(|pid| *pid > 0)
            && host.slim_process_alive(pid)?
        {
            return Err(slim("another adopter slim transaction is active"));
        }
        let receipt = root.join(".mir/bootstrap-receipt.json");
        if present(&receipt) && !safe_file(root, &receipt) {
            return Err(slim("cannot recover with an unsafe bootstrap receipt"));
        }
        let receipt = authored::json_text(&receipt).unwrap_or_else(|_| json!({}));
        if receipt["status"] == "ready"
            && receipt["slim"].is_object()
            && receipt["slim"]["transaction_id"] == journal["transaction_id"]
        {
            unlink(&root.join(JOURNAL))?;
            unlink(&lock)?;
        } else {
            let errors = rollback_journal(root, &journal)?;
            if !errors.is_empty() {
                return Err(slim(format!(
                    "slim recovery incomplete: {}",
                    errors.join("; ")
                )));
            }
        }
    } else if lock.is_file() {
        let pid = fs::read_to_string(&lock)
            .ok()
            .and_then(|s| s.trim().parse::<i64>().ok())
            .unwrap_or(-1);
        if pid > 0 && host.slim_process_alive(pid)? {
            return Err(slim("another adopter slim transaction is active"));
        }
        unlink(&lock)?;
    }
    Ok(())
}

pub(super) fn commit_adopter_slim(
    root: &Path,
    report: &Value,
    host: &mut impl Host,
) -> Result<(), Error> {
    if report["status"] != "applied" {
        return Ok(());
    }
    let root = slim_root(root, host)?;
    let journal = load_journal(&root)?
        .filter(|v| v["transaction_id"] == report["transaction_id"])
        .ok_or_else(|| slim("slim commit cannot match the durable transaction journal"))?;
    if journal["status"] != "verified" {
        return Err(slim("slim transaction was not verified before commit"));
    }
    fs::remove_file(root.join(JOURNAL)).map_err(slim_io)?;
    fs::remove_file(root.join(LOCK)).map_err(slim_io)
}
pub(super) fn rollback_adopter_slim(
    root: &Path,
    report: &Value,
    host: &mut impl Host,
) -> Result<(), Error> {
    if report["status"] != "applied" {
        return Ok(());
    }
    let root = slim_root(root, host)?;
    let journal = load_journal(&root)?
        .filter(|v| v["transaction_id"] == report["transaction_id"])
        .ok_or_else(|| slim("slim rollback cannot match the durable transaction journal"))?;
    let errors = rollback_journal(&root, &journal)?;
    if errors.is_empty() {
        Ok(())
    } else {
        Err(slim(format!(
            "slim rollback incomplete: {}",
            errors.join("; ")
        )))
    }
}

fn release_controls(root: &Path, profile: &Value, host: &mut impl Host) -> Result<(), Error> {
    let commit = profile["repo"]["profile_base_commit"]
        .as_str()
        .filter(|s| authored::valid_commit(s))
        .ok_or_else(|| {
            slim("slim requires a Git-bound profile_base_commit from greenfield Phase 1")
        })?;
    for relative in [
        "config/adopter-boundary.json",
        "config/adopter-payload.json",
    ] {
        let path = root.join(relative);
        if !safe_file(root, &path) {
            return Err(slim(format!(
                "release control is not a safe project file: {relative}"
            )));
        }
        let object = format!("{commit}:{relative}");
        let output = authored::run(root, &["git", "show", &object], false, host)?;
        if output.returncode != 0 {
            return Err(slim(format!(
                "cannot read release control {relative} from profile base commit {commit}"
            )));
        }
        let current = fs::read(&path)
            .map_err(|e| slim(format!("cannot read release control {relative}: {e}")))?;
        if current != output.stdout {
            return Err(slim(format!(
                "release control changed after Phase 1; slim made no changes: {relative}"
            )));
        }
    }
    Ok(())
}
fn findings(root: &Path, boundary: &Value) -> (Vec<String>, Vec<String>) {
    let paths = boundary["provider_markers"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .filter(|relative| present(&root.join(relative)))
        .map(str::to_owned)
        .collect();
    let text = boundary["provider_text_markers"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|marker| {
            let path = marker["path"].as_str()?;
            let contains = marker["contains"].as_str()?;
            authored::read_text(&root.join(path))
                .ok()?
                .contains(contains)
                .then(|| path.to_owned())
        })
        .collect();
    (paths, text)
}
fn payload(root: &Path, boundary: &Value, host: &mut impl Host) -> Result<Value, Error> {
    let manifest_relative = relative(&boundary["payload_manifest"])
        .map_err(|e| slim(e.message.replace("boundary", "payload")))?;
    let path = root.join(manifest_relative);
    let mut payload = authored::json_text(&path)
        .map_err(|e| slim(format!("cannot read adopter payload manifest: {e}")))?;
    if !payload.is_object()
        || !(payload["schema_version"].as_f64() == Some(1.0) || payload["schema_version"] == true)
    {
        return Err(slim(
            "adopter payload manifest must be a schema_version=1 object",
        ));
    }
    if let Some(schema_ref) = payload["$schema"].as_str() {
        let schema = authored::json_text(
            &path
                .parent()
                .ok_or_else(|| slim("missing parent directory"))?
                .join(schema_ref),
        )
        .map_err(|e| slim(format!("invalid adopter payload manifest: {e}")))?;
        host.validate_boundary_schema(&payload, &schema)
            .map_err(|e| slim(format!("invalid adopter payload manifest: {e}")))?;
    }
    let files = payload["files"]
        .as_array_mut()
        .ok_or_else(|| slim("adopter payload manifest requires a files array"))?;
    let mut seen = BTreeSet::new();
    for item in files {
        if !item.is_object() {
            return Err(slim("adopter payload file entries must be objects"));
        }
        let relative =
            relative(&item["path"]).map_err(|e| slim(e.message.replace("boundary", "payload")))?;
        if !seen.insert(relative.clone()) {
            return Err(slim(format!("duplicate adopter payload path: {relative}")));
        }
        item["path"] = json!(relative);
        if !item["sha256"].as_str().is_some_and(|s| s.len() == 64) {
            return Err(slim(format!("invalid adopter payload digest: {relative}")));
        }
        if item["disposition"] != "preserve" && item["disposition"] != "remove" {
            return Err(slim(format!(
                "invalid adopter payload disposition: {relative}"
            )));
        }
    }
    Ok(payload)
}
fn clean_run(
    root: &Path,
    argv: &[&str],
    host: &mut impl Host,
) -> Result<super::CommandOutput, Error> {
    host.slim_run_clean(&super::CommandRequest {
        argv: argv.iter().map(|s| (*s).to_owned()).collect(),
        cwd: root.to_owned(),
        environment: BTreeMap::new(),
        stdin_null: true,
        capture_output: true,
        text: true,
        check: false,
    })
}
fn external_cli(root: &Path, path: &Path, host: &mut impl Host) -> Result<PathBuf, Error> {
    let expanded = host.expanduser(path)?;
    let absolute = if expanded.is_absolute() {
        expanded
    } else {
        host.cwd()?.join(expanded)
    };
    let lexical = abspath(&absolute);
    let resolved = fs::canonicalize(&lexical)
        .map_err(|e| slim(format!("external Mir CLI is unavailable: {e}")))?;
    if !resolved.is_file() || resolved.starts_with(root) {
        return Err(slim(
            "slim requires a Mir CLI installed outside the adopter repository",
        ));
    }
    let resolved = resolved
        .to_str()
        .ok_or_else(|| slim("non-UTF-8 external CLI"))?;
    let output = clean_run(root, &[resolved, "bootstrap", "--help"], host)?;
    if output.returncode != 0 {
        let stderr = authored::decode(output.stderr)?;
        let stdout = authored::decode(output.stdout)?;
        let detail = if !stderr.trim().is_empty() {
            stderr.trim()
        } else if !stdout.trim().is_empty() {
            stdout.trim()
        } else {
            "unknown error"
        };
        return Err(slim(format!("external Mir CLI preflight failed: {detail}")));
    }
    Ok(lexical)
}
fn verify(root: &Path, cli: &Path, host: &mut impl Host) -> Result<(bool, String), Error> {
    let cli = cli.to_str().ok_or_else(|| slim("non-UTF-8 external CLI"))?;
    let root_arg = root
        .to_str()
        .ok_or_else(|| slim("non-UTF-8 project root"))?;
    let output = clean_run(
        root,
        &[
            cli,
            "capability",
            "status",
            "--project-root",
            root_arg,
            "--json",
        ],
        host,
    )?;
    if output.returncode != 0 {
        let stderr = authored::decode(output.stderr)?;
        return Ok((
            false,
            if stderr.trim().is_empty() {
                format!("exit {}", output.returncode)
            } else {
                stderr.trim().into()
            },
        ));
    }
    let report: Value = match serde_json::from_slice(&output.stdout) {
        Ok(report) => report,
        Err(_) => return Ok((false, "capability status did not return JSON".into())),
    };
    if !report.is_object() {
        return Ok((
            false,
            "capability status did not return a JSON object".into(),
        ));
    }
    let ready = report["ready"] == true
        && (report["changed_paths"] == json!([])
            || report["change_evidence"]
                == json!({"status":"not-applicable","reason":"read-only-operation"}));
    Ok((
        ready,
        if ready {
            "ready"
        } else {
            "capability status is not ready and read-only"
        }
        .into(),
    ))
}
fn marker_files(path: &Path, result: &mut Vec<PathBuf>) -> Result<(), Error> {
    if path.is_symlink() || path.is_file() {
        result.push(path.to_owned());
    } else if path.is_dir() {
        for entry in fs::read_dir(path).map_err(slim_io)? {
            marker_files(&entry.map_err(slim_io)?.path(), result)?;
        }
    }
    Ok(())
}
pub(super) fn apply_adopter_slim(
    root: &Path,
    external: &Path,
    defer_commit: bool,
    host: &mut impl Host,
) -> Result<Value, Error> {
    let root = slim_root(root, host)?;
    recover(&root, host)?;
    let boundary = load_boundary(&root, host).map_err(|e| slim(e.message))?;
    let profile = load_profile(&root).map_err(|e| slim(e.message))?;
    if let Err(error) = release_controls(&root, &profile, host) {
        if profile["repo"]["slug"] == "mir-yoke"
            && ["public_harness_template", "template_transitional"]
                .iter()
                .any(|kind| profile["repo"]["repository_type"] == *kind)
        {
            return Ok(json!({"status":"not_applicable","removed":[],"preserved_modified":[]}));
        }
        return Err(error);
    }
    if is_provider_owner(&profile, &boundary).map_err(|e| slim(e.message))? {
        return Ok(json!({"status":"not_applicable","removed":[],"preserved_modified":[]}));
    }
    let (paths, text) = findings(&root, &boundary);
    if !text.is_empty() {
        return Err(slim(format!(
            "product contract still contains provider identity markers: {}",
            text.join(", ")
        )));
    }
    let cli = external_cli(&root, external, host)?;
    let payload = payload(&root, &boundary, host)?;
    let mut moves = BTreeSet::new();
    let mut hashes = BTreeMap::new();
    let mut preserved = BTreeSet::new();
    let mut unsafe_remove = BTreeSet::new();
    for item in payload["files"]
        .as_array()
        .ok_or_else(|| slim("invalid array"))?
        .iter()
        .filter(|v| v["disposition"] == "remove")
    {
        let relative = item["path"]
            .as_str()
            .ok_or_else(|| slim("invalid adopter payload path"))?;
        let target = root.join(relative);
        if !present(&target) {
            continue;
        }
        if !safe_file(&root, &target) {
            preserved.insert(relative.to_owned());
            unsafe_remove.insert(relative.to_owned());
        } else if crate::digest::sha256(&fs::read(&target).map_err(slim_io)?)
            == item["sha256"]
                .as_str()
                .ok_or_else(|| slim("invalid adopter payload digest"))?
        {
            moves.insert(target);
            hashes.insert(
                relative.to_owned(),
                item["sha256"]
                    .as_str()
                    .ok_or_else(|| slim("invalid adopter payload digest"))?
                    .to_owned(),
            );
        } else {
            preserved.insert(relative.to_owned());
        }
    }
    let joined = |items: &BTreeSet<String>| items.iter().cloned().collect::<Vec<_>>().join(", ");
    if paths.is_empty() {
        if !unsafe_remove.is_empty() {
            return Err(slim(format!(
                "remove payload contains unsafe paths: {}",
                joined(&unsafe_remove)
            )));
        }
        if !moves.is_empty() {
            return Err(slim(format!(
                "unchanged remove payload remains without a provider marker: {}",
                moves
                    .iter()
                    .map(|p| p
                        .strip_prefix(&root)
                        .unwrap_or(&root)
                        .to_string_lossy()
                        .into_owned())
                    .collect::<Vec<_>>()
                    .join(", ")
            )));
        }
        let (ready, detail) = verify(&root, &cli, host)?;
        if !ready {
            return Err(slim(format!(
                "external CLI already-slim verification failed: {detail}"
            )));
        }
        return Ok(
            json!({"status":"already_slim","external_cli":cli,"removed":[],
            "preserved_modified":preserved,"verification":"ready"}),
        );
    }
    let ephemeral = boundary
        .get("ephemeral_globs")
        .cloned()
        .unwrap_or_else(|| json!([]));
    let ephemeral = ephemeral
        .as_array()
        .ok_or_else(|| slim("config/adopter-boundary.json ephemeral_globs must be an array"))?;
    let patterns = ephemeral
        .iter()
        .map(|v| relative(v).map_err(|e| slim(e.message.replace("boundary", "payload"))))
        .collect::<Result<Vec<_>, _>>()?;
    let mut conflicts = BTreeSet::new();
    for marker in paths {
        let mut files = Vec::new();
        marker_files(&root.join(marker), &mut files)?;
        for path in files {
            let relative = path
                .strip_prefix(&root)
                .unwrap_or(&root)
                .to_string_lossy()
                .replace('\\', "/");
            if !safe_file(&root, &path) {
                conflicts.insert(relative);
            } else if moves.contains(&path) {
                continue;
            } else if crate::mir_core::memory::external_store::matches_any(&relative, &patterns)
                .map_err(|e| slim(e.message))?
            {
                moves.insert(path);
            } else {
                conflicts.insert(relative);
            }
        }
    }
    if !conflicts.is_empty() {
        return Err(slim(format!(
            "provider marker contains preserved content; slim made no changes: {}",
            joined(&conflicts)
        )));
    }
    let quarantine_root = root.join(".mir/slim-quarantine");
    if !present(&quarantine_root) {
        let builder = &mut fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(&quarantine_root).map_err(slim_io)?;
    }
    safe_directory(&root, &quarantine_root, "slim quarantine root")?;
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut lock = options.open(root.join(LOCK)).map_err(|e| {
        if e.kind() == std::io::ErrorKind::AlreadyExists {
            slim("another adopter slim transaction is active")
        } else {
            slim_io(e)
        }
    })?;
    let pid = host.slim_pid();
    write!(lock, "{pid}").map_err(slim_io)?;
    lock.sync_all().map_err(slim_io)?;
    let transaction = host.slim_transaction_id();
    let quarantine = quarantine_root.join(&transaction);
    let relatives: Vec<_> = moves
        .iter()
        .map(|p| {
            p.strip_prefix(&root)
                .unwrap_or(&root)
                .to_string_lossy()
                .replace('\\', "/")
        })
        .collect();
    let mut journal = json!({"schema_version":1,"transaction_id":transaction,"pid":pid,
        "status":"moving","paths":relatives});
    let mut removed = Vec::new();
    let operation = (|| -> Result<(), Error> {
        atomic_journal(&root, &journal, host)?;
        for source in &moves {
            let relative = source
                .strip_prefix(&root)
                .unwrap_or(&root)
                .to_string_lossy()
                .replace('\\', "/");
            if !safe_file(&root, source) {
                return Err(slim(format!(
                    "provider path became unsafe before move: {relative}"
                )));
            }
            if let Some(expected) = hashes.get(&relative)
                && crate::digest::sha256(&fs::read(source).map_err(slim_io)?) != *expected
            {
                return Err(slim(format!(
                    "provider path changed before move: {relative}"
                )));
            }
            let destination = quarantine.join(&relative);
            if present(&destination) {
                return Err(slim(format!(
                    "slim quarantine destination already exists: {relative}"
                )));
            }
            if !safe_parent(
                &root,
                destination
                    .parent()
                    .ok_or_else(|| slim("missing destination parent"))?,
            ) {
                return Err(slim(format!(
                    "slim quarantine destination parent is unsafe: {relative}"
                )));
            }
            fs::rename(source, &destination).map_err(slim_io)?;
            removed.push(relative);
            prune(source, &root);
        }
        let (mut paths, text) = findings(&root, &boundary);
        paths.extend(text);
        if !paths.is_empty() {
            return Err(slim(format!(
                "provider boundary remains after slim: {}",
                paths.join(", ")
            )));
        }
        let (ready, detail) = verify(&root, &cli, host)?;
        if !ready {
            return Err(slim(format!(
                "external CLI post-slim verification failed: {detail}"
            )));
        }
        journal["status"] = json!("verified");
        atomic_journal(&root, &journal, host)
    })();
    if let Err(error) = operation {
        let errors = rollback_journal(&root, &journal)?;
        let detail = if errors.is_empty() {
            "rollback complete".into()
        } else {
            format!("rollback incomplete: {}", errors.join("; "))
        };
        return Err(slim(format!("{error}; {detail}")));
    }
    let report = json!({"status":"applied","transaction_id":transaction,"external_cli":cli,
        "removed":removed,"preserved_modified":preserved,
        "quarantine":quarantine.strip_prefix(&root).map_err(slim_io)?,"verification":"ready"});
    if !defer_commit {
        commit_adopter_slim(&root, &report, host)?;
    }
    Ok(report)
}
