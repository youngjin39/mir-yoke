//! Core adoption boundary classification and transactional slim provider.
//!
//! Library-only: callers provide process and environment observations through `Host`.
use super::main_host::abspath;
use super::{Error, Host, authored};
use crate::adoption_fs as confined;
use crate::python_decimal;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::{collections::BTreeMap, collections::BTreeSet, fs};

fn outside_subset() -> Error {
    Error::new(
        "NotImplementedError",
        "core adoption input outside native supported subset",
    )
}

fn admit_path(path: &Path) -> Result<&str, Error> {
    path.to_str().ok_or_else(outside_subset)
}

fn admit_profile(profile: &toml::Value) -> Result<(), Error> {
    let mut pending = vec![profile];
    while let Some(value) = pending.pop() {
        match value {
            toml::Value::Float(number) if !number.is_finite() => return Err(outside_subset()),
            toml::Value::Datetime(_) => return Err(outside_subset()),
            toml::Value::Array(items) => pending.extend(items),
            toml::Value::Table(items) => pending.extend(items.values()),
            _ => {}
        }
    }
    Ok(())
}

fn parse_json(text: &str) -> Result<Value, Error> {
    use crate::python_json::Value as PythonValue;
    let value =
        crate::python_json::parse(text).map_err(|e| Error::new(e.exception, e.to_string()))?;
    let mut pending = vec![(&value, 0)];
    let mut supported = true;
    while let Some((value, depth)) = pending.pop() {
        if depth > 128 {
            supported = false;
        }
        match value {
            PythonValue::String(text) => supported &= !text.has_surrogates(),
            PythonValue::Number(number) => {
                supported &= if number.is_integer() {
                    number.token.parse::<i64>().is_ok() || number.token.parse::<u64>().is_ok()
                } else {
                    number.token.parse::<f64>().is_ok_and(f64::is_finite)
                };
            }
            PythonValue::Array(items) => pending.extend(items.iter().map(|v| (v, depth + 1))),
            PythonValue::Object(items) => {
                for (key, value) in items.iter() {
                    supported &= !key.has_surrogates();
                    pending.push((value, depth + 1));
                }
            }
            _ => {}
        }
    }
    let result = if supported {
        Ok(value.to_serde())
    } else {
        Err(outside_subset())
    };
    drop_json(value);
    result
}

fn drop_json(value: crate::python_json::Value) {
    use crate::python_json::Value as PythonValue;
    // Avoid recursive drops for Python-only deeply nested values.
    let mut pending = vec![value];
    while let Some(value) = pending.pop() {
        match value {
            PythonValue::Array(items) => pending.extend(items),
            PythonValue::Object(items) => {
                pending.extend(items.into_entries().into_iter().map(|(_, v)| v))
            }
            _ => {}
        }
    }
}

fn json_text(path: &Path) -> Result<Value, Error> {
    admit_file_type(path)?;
    parse_json(&read_text(path)?)
}

fn read_text(path: &Path) -> Result<String, Error> {
    authored::decode(fs::read(path).map_err(|error| path_error(path, error))?)
}

fn admit_file_type(path: &Path) -> Result<(), Error> {
    if let Ok(metadata) = fs::metadata(path)
        && !metadata.is_dir()
        && !metadata.is_file()
    {
        return Err(outside_subset());
    }
    Ok(())
}

// shortcut: the Value API cannot carry Python-only JSON scalars or deep containers.
// Refuse these before recovery/mutation; extend the typed provider when this API is widened.
fn preflight_value(path: &Path) -> Result<Option<Value>, Error> {
    // Never turn a special file into a speculative blocking read.
    admit_file_type(path)?;
    if !path.is_file() {
        return Ok(None);
    }
    match json_text(path) {
        Ok(value) => Ok(Some(value)),
        Err(error) if error.class == "NotImplementedError" => Err(error),
        Err(_) => Ok(None),
    }
}

fn preflight_schema(path: &Path, value: &Value) -> Result<(), Error> {
    if let Some(schema_ref) = value["$schema"].as_str() {
        // Match the reader's one schema load, without following schemas recursively.
        preflight_value(&path.parent().unwrap_or(Path::new(".")).join(schema_ref))?;
    }
    Ok(())
}

fn preflight_inputs(root: &Path) -> Result<(), Error> {
    admit_path(root)?;
    let profile = root.join(".mir/repo-profile.toml");
    admit_file_type(&profile)?;
    if let Err(error) = load_profile(root)
        && error.class == "NotImplementedError"
    {
        return Err(error);
    }
    preflight_value(&root.join(JOURNAL))?;
    preflight_value(&root.join(".mir/bootstrap-receipt.json"))?;
    let path = root.join("config/adopter-boundary.json");
    if let Some(boundary) = preflight_value(&path)? {
        preflight_schema(&path, &boundary)?;
        for marker in boundary["provider_markers"]
            .as_array()
            .into_iter()
            .flatten()
        {
            if let Ok(relative) = relative(marker) {
                check_marker_names(&root.join(relative))?;
            }
        }
        if let Ok(relative) = relative(&boundary["payload_manifest"]) {
            let path = root.join(relative);
            if let Some(payload) = preflight_value(&path)? {
                preflight_schema(&path, &payload)?;
            }
        }
    }
    Ok(())
}

fn check_marker_names(path: &Path) -> Result<(), Error> {
    let mut pending = vec![path.to_owned()];
    while let Some(path) = pending.pop() {
        admit_path(&path)?;
        if !path_is_symlink(&path).map_err(|_| outside_subset())?
            && path_is_dir(&path).map_err(|_| outside_subset())?
        {
            let entries = fs::read_dir(&path).map_err(|_| outside_subset())?;
            for entry in entries {
                pending.push(entry.map_err(|_| outside_subset())?.path());
            }
        }
    }
    Ok(())
}

fn caught_json(error: &Error) -> bool {
    matches!(
        error.class,
        "OSError"
            | "FileNotFoundError"
            | "PermissionError"
            | "IsADirectoryError"
            | "NotADirectoryError"
            | "JSONDecodeError"
    )
}

fn process_alive(value: &Value, host: &mut impl Host) -> Result<bool, Error> {
    let pid = match value {
        Value::Bool(value) => i64::from(*value),
        Value::Number(number) if number.is_i64() || number.is_u64() => {
            number.as_i64().ok_or_else(|| {
                Error::new("OverflowError", "Python int too large to convert to C long")
            })?
        }
        _ => return Ok(false),
    };
    if pid <= 0 {
        return Ok(false);
    }
    if pid > i64::from(i32::MAX) {
        return Err(Error::new(
            "OverflowError",
            "signed integer is greater than maximum",
        ));
    }
    host.slim_process_alive(pid)
}

fn lock_pid(text: &str) -> Result<i64, Error> {
    let text = crate::python_json::python_strip(text);
    let mut normalized = String::new();
    for (index, character) in text.chars().enumerate() {
        if (index == 0 && matches!(character, '+' | '-')) || character == '_' {
            normalized.push(character);
        } else if let Some(digit) = python_decimal::decimal_digit(character) {
            normalized.push(char::from(b'0' + digit as u8));
        } else {
            return Ok(-1);
        }
    }
    let digits = normalized.trim_start_matches(['+', '-']);
    if digits.is_empty()
        || digits.starts_with('_')
        || digits.ends_with('_')
        || digits.contains("__")
    {
        return Ok(-1);
    }
    let normalized = normalized.replace('_', "");
    if normalized.trim_start_matches(['+', '-']).len() > 4300 {
        return Ok(-1);
    }
    if normalized.starts_with('-') {
        return Ok(-1);
    }
    match normalized.parse::<i64>() {
        Ok(value) if value <= i64::from(i32::MAX) => Ok(value),
        Ok(_) => Err(Error::new(
            "OverflowError",
            "signed integer is greater than maximum",
        )),
        Err(_) => Err(Error::new(
            "OverflowError",
            "Python int too large to convert to C long",
        )),
    }
}

fn validated_mir_directory(root: &Path) -> Result<(), Error> {
    let path = root.join(".mir");
    let metadata = fs::symlink_metadata(&path).map_err(|e| {
        slim(format!(
            "slim requires a real .mir directory: {}",
            path_error(&path, e)
        ))
    })?;
    let resolved = fs::canonicalize(&path).map_err(|e| {
        slim(format!(
            "slim requires a real .mir directory: {}",
            path_error(&path, e)
        ))
    })?;
    if metadata.is_symlink() || !metadata.is_dir() || !resolved.starts_with(root) {
        return Err(slim(
            "slim requires a real .mir directory inside the adopter repository",
        ));
    }
    Ok(())
}

fn quarantine_root(root: &Path) -> Result<PathBuf, Error> {
    let path = root.join(".mir/slim-quarantine");
    if !present(&path)? {
        confined::mkdir(root, &path, 0o700).map_err(|e| {
            slim(format!(
                "cannot create slim quarantine root: {}",
                path_error(&path, e)
            ))
        })?;
    }
    safe_directory(root, &path, "slim quarantine root")?;
    Ok(path)
}

fn valid_transaction_id(value: &Value) -> bool {
    value.as_str().is_some_and(|id| {
        id.len() == 32
            && id
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    })
}

fn admit_direct_rollback(journal: &Value) -> Result<(), Error> {
    if !valid_transaction_id(&journal["transaction_id"]) {
        return Err(outside_subset());
    }
    let paths = journal["paths"].as_array().ok_or_else(outside_subset)?;
    for path in paths {
        payload_relative(&json!(authored::python_str(path))).map_err(|_| outside_subset())?;
    }
    Ok(())
}

/// Direct library seam for the independently recorded core adoption family.
pub fn core_adoption_operation(
    root: &Path,
    operation: &str,
    input: &Value,
    host: &mut impl Host,
) -> Result<Value, Error> {
    match operation {
        "load_profile" => load_profile(root),
        "load_boundary" => load_boundary(root, host),
        "is_provider_owner" => {
            is_provider_owner(&input["profile"], &input["boundary"]).map(Value::Bool)
        }
        "safe_relative" => payload_relative(input.get("value").unwrap_or(input)).map(Value::String),
        "load_journal" => load_journal(root).map(|value| value.unwrap_or(Value::Null)),
        "quarantine_root" => quarantine_root(root).map(|path| json!(path)),
        "rollback_journal" => {
            let journal = input.get("journal").unwrap_or(input);
            admit_direct_rollback(journal)?;
            rollback_journal(root, journal, host).map(|errors| json!(errors))
        }
        "recover" => {
            let root = slim_root(root, host)?;
            admit_path(&root)?;
            recover(&root, host)
        }
        "apply" => {
            let external = input["external_cli"]
                .as_str()
                .ok_or_else(|| Error::new("TypeError", "external_cli must be a path string"))?;
            apply_adopter_slim(
                root,
                Path::new(external),
                input["defer_commit"] == true,
                host,
            )
        }
        "commit" => commit_adopter_slim(root, &input["report"], host).map(|()| Value::Null),
        "rollback" => rollback_adopter_slim(root, &input["report"], host).map(|()| Value::Null),
        _ => Err(Error::new(
            "ValueError",
            format!("unknown core adoption operation: {operation}"),
        )),
    }
}

pub(super) fn load_profile(root: &Path) -> Result<Value, Error> {
    let result = (|| {
        let path = root.join(".mir/repo-profile.toml");
        admit_file_type(&path)?;
        let bytes = fs::read(&path).map_err(|e| path_error(&path, e))?;
        let text =
            super::super::bootstrap_adoption::decode(bytes).map_err(authored::adopt_error)?;
        let profile: toml::Value = toml::from_str(&text).map_err(|e| {
            if e.message().contains("too large") || e.message().contains("out of range") {
                return outside_subset();
            }
            let mut message = crate::mir_core::tomllib::tomllib_error(&e, &text);
            if message == "unmapped TOML parse error" && e.message().contains("newline") {
                let offset = e.span().map_or(text.len(), |span| span.start);
                let prefix = &text[..offset];
                let line = prefix.bytes().filter(|b| *b == b'\n').count() + 1;
                let column = prefix.rsplit('\n').next().unwrap_or("").chars().count() + 1;
                message = format!("Expected newline or end of document after a statement (at line {line}, column {column})");
            }
            if message == "unmapped TOML parse error" {
                return outside_subset();
            }
            Error::new("TOMLDecodeError", message)
        })?;
        admit_profile(&profile)?;
        serde_json::to_value(profile).map_err(|e| Error::new("ValueError", e.to_string()))
    })();
    let profile: Value = result.map_err(|e: Error| {
        if !caught_json(&e) && e.class != "TOMLDecodeError" {
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

fn payload_relative(value: &Value) -> Result<String, Error> {
    relative(value).map_err(|e| slim(e.message.replace("boundary", "payload")))
}

pub(super) fn load_boundary(root: &Path, host: &mut impl Host) -> Result<Value, Error> {
    let path = root.join("config/adopter-boundary.json");
    let mut boundary = json_text(&path).map_err(|e| {
        if !caught_json(&e) && e.class != "TOMLDecodeError" {
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
        let schema = json_text(
            &path
                .parent()
                .ok_or_else(|| slim("missing parent directory"))?
                .join(schema_ref),
        )
        .map_err(|e| {
            if caught_json(&e) {
                Error::new("BoundaryError", format!("invalid {}: {e}", path.display()))
            } else {
                e
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
    if !profile.is_object() {
        return Err(Error::new(
            "TypeError",
            format!("'{}' object is not subscriptable", python_type(profile)),
        ));
    }
    let repo = profile
        .get("repo")
        .ok_or_else(|| Error::new("KeyError", "'repo'"))?;
    if !repo.is_object() {
        return Err(Error::new("AssertionError", ""));
    }
    if !boundary.is_object() {
        return Err(authored::attribute_error(boundary, "get"));
    }
    let owners = boundary["provider_owners"].as_array().ok_or_else(|| {
        Error::new(
            "BoundaryError",
            "config/adopter-boundary.json requires provider_owners",
        )
    })?;
    Ok(owners.iter().any(|owner| {
        owner.is_object()
            && python_equal(&profile["repo"]["slug"], &owner["slug"])
            && owner["repository_types"].as_array().is_some_and(|types| {
                types
                    .iter()
                    .any(|kind| python_equal(kind, &profile["repo"]["repository_type"]))
            })
    }))
}

fn python_equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Bool(boolean), Value::Number(number))
        | (Value::Number(number), Value::Bool(boolean)) => {
            number.as_f64() == Some(if *boolean { 1.0 } else { 0.0 })
        }
        (Value::Number(left), Value::Number(right)) if left.is_f64() && right.is_f64() => {
            left.as_f64() == right.as_f64()
        }
        (Value::Number(left), Value::Number(right)) if left.is_f64() => {
            float_integer_equal(left.as_f64(), right)
        }
        (Value::Number(left), Value::Number(right)) if right.is_f64() => {
            float_integer_equal(right.as_f64(), left)
        }
        (Value::Array(left), Value::Array(right)) => {
            left.len() == right.len() && left.iter().zip(right).all(|(l, r)| python_equal(l, r))
        }
        (Value::Object(left), Value::Object(right)) => {
            left.len() == right.len()
                && left.iter().all(|(key, value)| {
                    right
                        .get(key)
                        .is_some_and(|other| python_equal(value, other))
                })
        }
        _ => left == right,
    }
}

fn float_integer_equal(float: Option<f64>, integer: &serde_json::Number) -> bool {
    let Some(float) = float.filter(|number| number.is_finite() && number.fract() == 0.0) else {
        return false;
    };
    if let Some(integer) = integer.as_i64() {
        return (i64::MIN as f64..-(i64::MIN as f64)).contains(&float) && float as i64 == integer;
    }
    integer.as_u64().is_some_and(|integer| {
        (0.0..18446744073709551616.0).contains(&float) && float as u64 == integer
    })
}

fn hashable(value: &Value) -> Result<(), Error> {
    if value.is_array() || value.is_object() {
        return Err(Error::new(
            "TypeError",
            format!("unhashable type: '{}'", python_type(value)),
        ));
    }
    Ok(())
}

fn python_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) if n.is_f64() => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

const JOURNAL: &str = ".mir/slim-transaction.json";
const LOCK: &str = ".mir/slim.lock";
fn slim(message: impl Into<String>) -> Error {
    Error::new("SlimError", message)
}
fn slim_io(error: impl std::fmt::Display) -> Error {
    slim(error.to_string())
}
fn fd_error(error: std::io::Error) -> Error {
    let class = match error.kind() {
        std::io::ErrorKind::NotFound => "FileNotFoundError",
        std::io::ErrorKind::PermissionDenied => "PermissionError",
        std::io::ErrorKind::IsADirectory => "IsADirectoryError",
        std::io::ErrorKind::NotADirectory => "NotADirectoryError",
        std::io::ErrorKind::AlreadyExists => "FileExistsError",
        std::io::ErrorKind::Interrupted => "InterruptedError",
        std::io::ErrorKind::WouldBlock => "BlockingIOError",
        std::io::ErrorKind::BrokenPipe => "BrokenPipeError",
        _ => "OSError",
    };
    let text = crate::executor_brief_profile::python_os_error_text(&error);
    let message = error
        .raw_os_error()
        .map_or(text.clone(), |errno| format!("[Errno {errno}] {text}"));
    Error::new(class, message)
}
fn path_error(path: &Path, error: std::io::Error) -> Error {
    if path.as_os_str().as_encoded_bytes().contains(&0) {
        return Error::new("ValueError", "embedded null byte");
    }
    let message = crate::executor_brief_profile::python_os_error_message(&error, path);
    Error::new(fd_error(error).class, message)
}

fn path_metadata(path: &Path, follow: bool) -> Result<Option<fs::Metadata>, Error> {
    let result = if follow {
        fs::metadata(path)
    } else {
        fs::symlink_metadata(path)
    };
    match result {
        Ok(metadata) => Ok(Some(metadata)),
        Err(error)
            if matches!(error.raw_os_error(), Some(2 | 20 | 9))
                || error.raw_os_error()
                    == Some(if cfg!(target_os = "macos") { 62 } else { 40 })
                || (error.kind() == std::io::ErrorKind::InvalidInput
                    && path.as_os_str().as_encoded_bytes().contains(&0)) =>
        {
            Ok(None)
        }
        Err(error) => Err(path_error(path, error)),
    }
}

fn path_exists(path: &Path) -> Result<bool, Error> {
    Ok(path_metadata(path, true)?.is_some())
}
fn path_is_symlink(path: &Path) -> Result<bool, Error> {
    Ok(path_metadata(path, false)?.is_some_and(|metadata| metadata.is_symlink()))
}
fn path_is_file(path: &Path) -> Result<bool, Error> {
    Ok(path_metadata(path, true)?.is_some_and(|metadata| metadata.is_file()))
}
fn path_is_dir(path: &Path) -> Result<bool, Error> {
    Ok(path_metadata(path, true)?.is_some_and(|metadata| metadata.is_dir()))
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
    let expanded = host.expanduser(root)?;
    let root = fs::canonicalize(&expanded).map_err(|e| path_error(&expanded, e))?;
    validated_mir_directory(&root)?;
    Ok(root)
}
fn safe_directory(root: &Path, path: &Path, label: &str) -> Result<(), Error> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| slim(format!("{label} escapes the adopter repository")))?;
    let mut current = root.to_owned();
    for part in relative.components() {
        current.push(part);
        let metadata = fs::symlink_metadata(&current).map_err(|e| {
            slim(format!(
                "{label} is unavailable: {}",
                path_error(&current, e)
            ))
        })?;
        if metadata.is_symlink() {
            return Err(slim(format!("{label} contains a symlinked path component")));
        }
    }
    if !path_is_dir(path)?
        || !fs::canonicalize(path)
            .map_err(|e| path_error(path, e))?
            .starts_with(root)
    {
        return Err(slim(format!("{label} is not a real adopter directory")));
    }
    Ok(())
}
fn safe_parent(root: &Path, path: &Path) -> Result<bool, Error> {
    safe_parent_with_lstat(root, path, |path| fs::symlink_metadata(path))
}

fn safe_parent_with_lstat(
    root: &Path,
    path: &Path,
    mut lstat: impl FnMut(&Path) -> std::io::Result<fs::Metadata>,
) -> Result<bool, Error> {
    let Ok(relative) = path.strip_prefix(root) else {
        return Ok(false);
    };
    let mut current = root.to_owned();
    for part in relative.components() {
        current.push(part);
        if present(&current)? {
            let Ok(metadata) = lstat(&current) else {
                return Ok(false);
            };
            if metadata.is_symlink() || !metadata.is_dir() {
                return Ok(false);
            }
        } else {
            confined::mkdir(root, &current, 0o777).map_err(|e| path_error(&current, e))?;
        }
    }
    Ok(true)
}
fn prune(path: &Path, root: &Path) {
    let mut current = path.parent();
    while let Some(path) = current.filter(|p| *p != root && p.starts_with(root)) {
        if confined::parent(root, path)
            .and_then(|parent| parent.unlink(&parent.name, true))
            .is_err()
        {
            break;
        }
        current = path.parent();
    }
}
fn present(path: &Path) -> Result<bool, Error> {
    if path_exists(path)? {
        return Ok(true);
    }
    path_is_symlink(path)
}
fn unlink(root: &Path, path: &Path) -> Result<(), Error> {
    let parent = match confined::parent(root, path) {
        Ok(parent) => parent,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(path_error(path, error)),
    };
    unlink_name(&parent, &parent.name, path)
}
fn unlink_name(
    parent: &confined::Parent,
    name: &std::ffi::OsStr,
    path: &Path,
) -> Result<(), Error> {
    match parent.unlink(name, false) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(path_error(path, e)),
    }
}
fn confined_move(
    root: &Path,
    source: &Path,
    destination: &Path,
    host: &mut impl Host,
) -> Result<(), Error> {
    host.slim_before_move(root, source, destination);
    let movement = confined::Move::prepare(root, source, destination).map_err(|_| {
        Error::new(
            "OSError",
            format!(
                "unsafe slim move: {} -> {}",
                source.strip_prefix(root).unwrap_or(source).display(),
                destination
                    .strip_prefix(root)
                    .unwrap_or(destination)
                    .display(),
            ),
        )
    })?;
    host.slim_replace(source, destination, &mut || {
        movement.rename().map_err(|e| {
            let mut error = path_error(Path::new(source.file_name().unwrap_or_default()), e);
            error.message.push_str(&format!(
                " -> {}",
                crate::executor_execute::repr(
                    &destination
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                )
            ));
            error
        })
    })
}
fn atomic_journal(root: &Path, journal: &Value, host: &mut impl Host) -> Result<(), Error> {
    let path = root.join(JOURNAL);
    let directory = confined::parent(root, &path).map_err(fd_error)?;
    let body = format!(
        "{}\n",
        authored::pretty(journal, true)?.replace('\u{7f}', "\\u007f")
    );
    let temp = tempfile::Builder::new()
        .prefix(".slim-transaction.json.")
        .rand_bytes(8)
        .disable_cleanup(true)
        .make_in(root.join(".mir"), |path| {
            directory.create(path.file_name().unwrap_or_default(), 0o600)
        })
        .map_err(fd_error)?;
    let (mut file, temp_path) = temp.into_parts();
    let temp_name = temp_path.file_name().unwrap_or_default().to_owned();
    let operation = (|| {
        host.slim_write(&mut file, body.as_bytes(), "journal-file")
            .map_err(fd_error)?;
        host.slim_fsync(&file, "journal-file").map_err(fd_error)?;
        drop(file);
        confined_move(root, &temp_path, &path, host)?;
        let sync_file = directory
            .sync_file()
            .map_err(|e| path_error(Path::new("."), e))?;
        host.slim_fsync(&sync_file, "journal-directory")
            .map_err(fd_error)
    })();
    // Keep finally cleanup on the originally opened directory after a parent swap.
    unlink_name(&directory, &temp_name, Path::new(&temp_name))?;
    operation
}
fn load_journal(root: &Path) -> Result<Option<Value>, Error> {
    let path = root.join(JOURNAL);
    if path_is_symlink(&path)? {
        return Err(slim("cannot recover unsafe slim journal symlink"));
    }
    if !path_exists(&path)? {
        return Ok(None);
    }
    if !path_is_file(&path)? {
        return Err(slim("cannot recover non-file slim journal"));
    }
    let mut journal = json_text(&path).map_err(|e| {
        if caught_json(&e) {
            slim(format!("cannot recover invalid slim journal: {e}"))
        } else {
            e
        }
    })?;
    let valid_id = valid_transaction_id(&journal["transaction_id"]);
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
fn rollback_journal(
    root: &Path,
    journal: &Value,
    host: &mut impl Host,
) -> Result<Vec<String>, Error> {
    validated_mir_directory(root)?;
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
        .map(authored::python_str)
    {
        let source = root.join(&relative);
        let destination = quarantine.join(&relative);
        let source_present = present(&source)?;
        let destination_present = present(&destination)?;
        if source_present && !destination_present {
            continue;
        }
        let error = if source_present || !destination_present {
            Some("ambiguous rollback state".to_owned())
        } else if !safe_file(root, &destination) {
            Some("quarantine source is unsafe".into())
        } else if !safe_parent(
            root,
            source
                .parent()
                .ok_or_else(|| slim("missing source parent"))?,
        )? {
            Some("restore parent is unsafe".into())
        } else {
            confined_move(root, &destination, &source, host)
                .err()
                .map(|e| e.message)
        };
        if let Some(error) = error {
            errors.push(format!("{relative}: {error}"));
        }
    }
    if errors.is_empty() {
        prune(&quarantine.join("placeholder"), &root.join(".mir"));
        unlink(root, &root.join(JOURNAL))?;
        unlink(root, &root.join(LOCK))?;
    }
    Ok(errors)
}
fn recover(root: &Path, host: &mut impl Host) -> Result<Value, Error> {
    let journal = load_journal(root)?;
    let lock = root.join(LOCK);
    if present(&lock)? && !safe_file(root, &lock) {
        return Err(slim("cannot recover unsafe slim lock"));
    }
    if let Some(journal) = journal {
        if process_alive(&journal["pid"], host)? {
            return Err(slim("another adopter slim transaction is active"));
        }
        let receipt = root.join(".mir/bootstrap-receipt.json");
        if present(&receipt)? && !safe_file(root, &receipt) {
            return Err(slim("cannot recover with an unsafe bootstrap receipt"));
        }
        let receipt = if present(&receipt)? {
            match json_text(&receipt) {
                Ok(value) => value,
                Err(error) if caught_json(&error) => json!({}),
                Err(error) => return Err(error),
            }
        } else {
            json!({})
        };
        if !receipt.is_object() {
            return Err(authored::attribute_error(&receipt, "get"));
        }
        if receipt["status"] == "ready"
            && receipt["slim"].is_object()
            && receipt["slim"]["transaction_id"] == journal["transaction_id"]
        {
            unlink(root, &root.join(JOURNAL))?;
            unlink(root, &lock)?;
            return Ok(json!({"status":"committed", "transaction_id":journal["transaction_id"]}));
        } else {
            let errors = rollback_journal(root, &journal, host)?;
            if !errors.is_empty() {
                return Err(slim(format!(
                    "slim recovery incomplete: {}",
                    errors.join("; ")
                )));
            }
            return Ok(json!({"status":"rolled_back", "transaction_id":journal["transaction_id"]}));
        }
    } else if path_is_file(&lock)? {
        let pid = match read_text(&lock) {
            Ok(text) => lock_pid(&text)?,
            Err(error) if caught_json(&error) || error.class == "UnicodeDecodeError" => -1,
            Err(error) => return Err(error),
        };
        if pid > 0 && host.slim_process_alive(pid)? {
            return Err(slim("another adopter slim transaction is active"));
        }
        unlink(root, &lock)?;
    }
    Ok(json!({"status":"clean"}))
}

pub(super) fn commit_adopter_slim(
    root: &Path,
    report: &Value,
    host: &mut impl Host,
) -> Result<(), Error> {
    if !report.is_object() {
        return Err(authored::attribute_error(report, "get"));
    }
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
    for path in [root.join(JOURNAL), root.join(LOCK)] {
        let parent = confined::parent(&root, &path).map_err(|e| path_error(&path, e))?;
        parent
            .unlink(&parent.name, false)
            .map_err(|e| path_error(&path, e))?;
    }
    Ok(())
}
pub(super) fn rollback_adopter_slim(
    root: &Path,
    report: &Value,
    host: &mut impl Host,
) -> Result<(), Error> {
    if !report.is_object() {
        return Err(authored::attribute_error(report, "get"));
    }
    if report["status"] != "applied" {
        return Ok(());
    }
    let root = slim_root(root, host)?;
    let journal = load_journal(&root)?
        .filter(|v| v["transaction_id"] == report["transaction_id"])
        .ok_or_else(|| slim("slim rollback cannot match the durable transaction journal"))?;
    let errors = rollback_journal(&root, &journal, host)?;
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
        let current = fs::read(&path).map_err(|e| {
            slim(format!(
                "cannot read release control {relative}: {}",
                path_error(&path, e)
            ))
        })?;
        if current != output.stdout {
            return Err(slim(format!(
                "release control changed after Phase 1; slim made no changes: {relative}"
            )));
        }
    }
    Ok(())
}
fn findings(root: &Path, boundary: &Value) -> Result<(Vec<String>, Vec<String>), Error> {
    let mut paths = Vec::new();
    for relative in boundary["provider_markers"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
    {
        if present(&root.join(relative))? {
            paths.push(relative.to_owned());
        }
    }
    let mut text = Vec::new();
    for marker in boundary["provider_text_markers"]
        .as_array()
        .into_iter()
        .flatten()
    {
        let path = marker["path"].as_str().ok_or_else(outside_subset)?;
        let contains = marker["contains"].as_str().ok_or_else(outside_subset)?;
        match read_text(&root.join(path)) {
            Ok(body) if body.contains(contains) => text.push(path.to_owned()),
            Ok(_) => {}
            Err(error) if caught_json(&error) => {}
            Err(error) => return Err(error),
        }
    }
    Ok((paths, text))
}
fn payload(root: &Path, boundary: &Value, host: &mut impl Host) -> Result<Value, Error> {
    let manifest_relative = relative(&boundary["payload_manifest"])
        .map_err(|e| slim(e.message.replace("boundary", "payload")))?;
    let path = root.join(manifest_relative);
    let mut payload = json_text(&path).map_err(|e| {
        if caught_json(&e) {
            slim(format!("cannot read adopter payload manifest: {e}"))
        } else {
            e
        }
    })?;
    if !payload.is_object()
        || !(payload["schema_version"].as_f64() == Some(1.0) || payload["schema_version"] == true)
    {
        return Err(slim(
            "adopter payload manifest must be a schema_version=1 object",
        ));
    }
    if let Some(schema_ref) = payload["$schema"].as_str() {
        let schema = json_text(
            &path
                .parent()
                .ok_or_else(|| slim("missing parent directory"))?
                .join(schema_ref),
        )
        .map_err(|e| {
            if caught_json(&e) || e.class == "ValidationError" {
                slim(format!("invalid adopter payload manifest: {e}"))
            } else {
                e
            }
        })?;
        host.validate_boundary_schema(&payload, &schema)
            .map_err(|e| {
                if caught_json(&e) || e.class == "ValidationError" {
                    slim(format!("invalid adopter payload manifest: {e}"))
                } else {
                    e
                }
            })?;
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
        if !item["sha256"]
            .as_str()
            .is_some_and(|s| s.chars().count() == 64)
        {
            return Err(slim(format!("invalid adopter payload digest: {relative}")));
        }
        hashable(&item["disposition"])?;
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
    let mut output = host.slim_run_clean(&super::CommandRequest {
        argv: argv.iter().map(|s| (*s).to_owned()).collect(),
        cwd: root.to_owned(),
        environment: BTreeMap::new(),
        stdin_null: true,
        capture_output: true,
        text: true,
        check: false,
    })?;
    output.stdout = authored::decode(output.stdout)?.into_bytes();
    output.stderr = authored::decode(output.stderr)?.into_bytes();
    Ok(output)
}
fn external_cli(root: &Path, path: &Path, host: &mut impl Host) -> Result<PathBuf, Error> {
    let expanded = host.expanduser(path)?;
    let absolute = if expanded.is_absolute() {
        expanded
    } else {
        host.cwd()?.join(expanded)
    };
    let preserve_double_slash = absolute.as_os_str().as_encoded_bytes().starts_with(b"//")
        && !absolute.as_os_str().as_encoded_bytes().starts_with(b"///");
    let mut lexical = abspath(&absolute);
    if preserve_double_slash {
        lexical = PathBuf::from(format!("/{}", admit_path(&lexical)?));
    }
    let resolved = fs::canonicalize(&lexical).map_err(|e| {
        slim(format!(
            "external Mir CLI is unavailable: {}",
            path_error(&lexical, e)
        ))
    })?;
    if !path_is_file(&resolved)? || resolved.starts_with(root) {
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
        let detail = if !crate::python_json::python_strip(&stderr).is_empty() {
            crate::python_json::python_strip(&stderr)
        } else if !crate::python_json::python_strip(&stdout).is_empty() {
            crate::python_json::python_strip(&stdout)
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
            if crate::python_json::python_strip(&stderr).is_empty() {
                format!("exit {}", output.returncode)
            } else {
                crate::python_json::python_strip(&stderr).into()
            },
        ));
    }
    let report = match crate::python_json::parse(&authored::decode(output.stdout)?) {
        Ok(report) => report,
        Err(error) if error.exception == "JSONDecodeError" => {
            return Ok((false, "capability status did not return JSON".into()));
        }
        Err(error) => return Err(Error::new(error.exception, error.to_string())),
    };
    if !report.is_object() {
        drop_json(report);
        return Ok((
            false,
            "capability status did not return a JSON object".into(),
        ));
    }
    // Only these fields affect verification. Python-only extension values remain typed.
    let read_only = report["change_evidence"]
        .as_object()
        .is_some_and(|evidence| {
            evidence.len() == 2
                && evidence
                    .get("status")
                    .and_then(crate::python_json::Value::as_str)
                    == Some("not-applicable")
                && evidence
                    .get("reason")
                    .and_then(crate::python_json::Value::as_str)
                    == Some("read-only-operation")
        });
    let ready = matches!(report["ready"], crate::python_json::Value::Bool(true))
        && (report["changed_paths"]
            .as_array()
            .is_some_and(Vec::is_empty)
            || read_only);
    drop_json(report);
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
    admit_path(path)?;
    if path_is_symlink(path)? || path_is_file(path)? {
        result.push(path.to_owned());
    } else if path_exists(path)? {
        marker_descendants(path, result)?;
    }
    Ok(())
}

fn marker_descendants(path: &Path, result: &mut Vec<PathBuf>) -> Result<(), Error> {
    marker_directory_files(path, result)?;
    // Match rglob's selector over Path.walk: filter all sibling directories before
    // visiting their descendants, while the directory walk itself remains depth first.
    let mut walk = vec![path.to_owned()];
    while let Some(directory) = walk.pop() {
        let Ok(entries) = fs::read_dir(&directory) else {
            continue;
        };
        let mut children = Vec::new();
        for entry in entries {
            let entry = entry.map_err(fd_error)?;
            if entry.file_type().is_ok_and(|kind| kind.is_dir()) {
                children.push(entry.path());
            }
        }
        for child in &children {
            marker_directory_files(child, result)?;
        }
        walk.extend(children.into_iter().rev());
    }
    Ok(())
}

fn marker_directory_files(path: &Path, result: &mut Vec<PathBuf>) -> Result<(), Error> {
    // pathlib.rglob suppresses OSError from scandir and its iterator.
    if let Ok(entries) = fs::read_dir(path) {
        let entries: Result<Vec<_>, _> = entries.collect();
        if let Ok(entries) = entries {
            for entry in entries {
                let child = entry.path();
                admit_path(&child)?;
                // The rglob filter checks is_file first; the top marker checks is_symlink first.
                if path_is_file(&child)? || path_is_symlink(&child)? {
                    result.push(child.clone());
                }
            }
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
    admit_path(external)?;
    let root = slim_root(root, host)?;
    preflight_inputs(&root)?;
    recover(&root, host)?;
    let boundary = load_boundary(&root, host).map_err(|e| {
        if e.class == "BoundaryError" {
            slim(e.message)
        } else {
            e
        }
    })?;
    let profile = load_profile(&root).map_err(|e| {
        if e.class == "BoundaryError" {
            slim(e.message)
        } else {
            e
        }
    })?;
    if let Err(error) = release_controls(&root, &profile, host) {
        if error.class != "SlimError" {
            return Err(error);
        }
        if profile["repo"]["slug"] == "mir-yoke" {
            hashable(&profile["repo"]["repository_type"])?;
        }
        if profile["repo"]["slug"] == "mir-yoke"
            && ["public_harness_template", "template_transitional"]
                .iter()
                .any(|kind| profile["repo"]["repository_type"] == *kind)
        {
            return Ok(json!({"status":"not_applicable","removed":[],"preserved_modified":[]}));
        }
        return Err(error);
    }
    if is_provider_owner(&profile, &boundary)? {
        return Ok(json!({"status":"not_applicable","removed":[],"preserved_modified":[]}));
    }
    let (paths, text) = findings(&root, &boundary)?;
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
        if !present(&target)? {
            continue;
        }
        if !safe_file(&root, &target) {
            preserved.insert(relative.to_owned());
            unsafe_remove.insert(relative.to_owned());
        } else if crate::digest::sha256(&fs::read(&target).map_err(|e| path_error(&target, e))?)
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
                .into_owned();
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
    validated_mir_directory(&root)?;
    let quarantine_root = quarantine_root(&root)?;
    let directory = confined::parent(&root, &root.join(LOCK)).map_err(fd_error)?;
    let mut lock = directory.create(&directory.name, 0o600).map_err(|e| {
        if e.kind() == std::io::ErrorKind::AlreadyExists {
            slim("another adopter slim transaction is active")
        } else {
            path_error(&root.join(LOCK), e)
        }
    })?;
    let pid = host.slim_pid();
    host.slim_write(&mut lock, pid.to_string().as_bytes(), "lock")
        .map_err(fd_error)?;
    host.slim_fsync(&lock, "lock").map_err(fd_error)?;
    drop(lock);
    let transaction = host.slim_transaction_id();
    let quarantine = quarantine_root.join(&transaction);
    let relatives: Vec<_> = moves
        .iter()
        .map(|p| {
            p.strip_prefix(&root)
                .unwrap_or(&root)
                .to_string_lossy()
                .into_owned()
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
                .into_owned();
            if !safe_file(&root, source) {
                return Err(slim(format!(
                    "provider path became unsafe before move: {relative}"
                )));
            }
            if let Some(expected) = hashes.get(&relative)
                && crate::digest::sha256(&fs::read(source).map_err(|e| path_error(source, e))?)
                    != *expected
            {
                return Err(slim(format!(
                    "provider path changed before move: {relative}"
                )));
            }
            let destination = quarantine.join(&relative);
            if present(&destination)? {
                return Err(slim(format!(
                    "slim quarantine destination already exists: {relative}"
                )));
            }
            if !safe_parent(
                &root,
                destination
                    .parent()
                    .ok_or_else(|| slim("missing destination parent"))?,
            )? {
                return Err(slim(format!(
                    "slim quarantine destination parent is unsafe: {relative}"
                )));
            }
            confined_move(&root, source, &destination, host)?;
            removed.push(relative);
            prune(source, &root);
        }
        let (mut paths, text) = findings(&root, &boundary)?;
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
        let errors = rollback_journal(&root, &journal, host)?;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_unlink_parent_remains_a_noop() {
        let scratch = Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/stage-e01");
        fs::create_dir_all(&scratch).expect("scratch");
        let temp = tempfile::tempdir_in(scratch).expect("synthetic root");
        let root = fs::canonicalize(temp.path()).expect("canonical root");
        unlink(&root, &root.join("missing/entry")).expect("missing parent is already absent");
        assert_eq!(fs::read_dir(root).expect("unchanged root").count(), 0);
    }
    #[cfg(unix)]
    #[test]
    fn journal_publication_refuses_parent_swap() {
        check_journal_publication_swap(false);
    }
    #[cfg(unix)]
    #[test]
    fn journal_publication_refuses_root_ancestor_swap() {
        check_journal_publication_swap(true);
    }
    #[cfg(unix)]
    fn check_journal_publication_swap(ancestor: bool) {
        struct Swap {
            outside: PathBuf,
            publication_parent: PathBuf,
            ancestor: bool,
            seeded: Option<PathBuf>,
        }
        impl Host for Swap {
            fn env(&mut self, _: &str) -> Option<String> {
                None
            }
            fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error> {
                Ok(path.to_owned())
            }
            fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error> {
                Ok(path.to_owned())
            }
            fn is_dir(&mut self, path: &Path) -> bool {
                path.is_dir()
            }
            fn writable(&mut self, _: &Path) -> bool {
                true
            }
            fn device(&mut self, _: &Path) -> Result<u64, Error> {
                Ok(0)
            }
            fn slim_before_move(&mut self, root: &Path, source: &Path, destination: &Path) {
                use std::os::unix::fs::symlink;
                let seeded = self
                    .publication_parent
                    .join(source.file_name().expect("temp basename"));
                fs::write(&seeded, b"OUTSIDE-TEMP").expect("seed outside temp");
                self.seeded = Some(seeded);
                let parent = if self.ancestor {
                    root.parent().expect("root ancestor")
                } else {
                    destination.parent().expect("journal parent")
                };
                fs::rename(parent, parent.with_file_name(".mir-saved")).expect("swap parent");
                symlink(&self.outside, parent).expect("redirect journal parent");
            }
        }
        let scratch = Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/stage-e01");
        fs::create_dir_all(&scratch).expect("scratch");
        let temp = tempfile::tempdir_in(scratch).expect("synthetic root");
        let root = temp.path().join("container/root");
        fs::create_dir_all(root.join(".mir")).expect("journal parent");
        let outside = temp.path().join("outside");
        fs::create_dir(&outside).expect("outside");
        let publication_parent = if ancestor {
            outside.join("root/.mir")
        } else {
            outside.clone()
        };
        fs::create_dir_all(&publication_parent).expect("outside journal parent");
        fs::write(publication_parent.join("slim-transaction.json"), b"OUTSIDE").expect("sentinel");
        let mut host = Swap {
            outside: outside.clone(),
            publication_parent: publication_parent.clone(),
            ancestor,
            seeded: None,
        };
        let result = atomic_journal(&root, &json!({"status":"moving"}), &mut host);
        assert!(
            result.is_err(),
            "journal publication accepted substituted parent"
        );
        assert_eq!(
            fs::read(publication_parent.join("slim-transaction.json")).expect("sentinel"),
            b"OUTSIDE"
        );
        assert_eq!(
            fs::read(host.seeded.expect("seam reached")).expect("outside temp"),
            b"OUTSIDE-TEMP"
        );
        assert_eq!(
            fs::read_dir(publication_parent)
                .expect("outside entries")
                .count(),
            2
        );
    }

    #[test]
    fn private_path_helpers_match_pinned_records() {
        let fixture = crate::python_json::parse(include_str!(
            "../../tests/fixtures/stage-e01-core-adoption.json"
        ))
        .expect("pinned helper records must parse");
        let cases = fixture["private_helpers"]
            .as_array()
            .expect("helper records");
        assert_eq!(cases.len(), 5);
        for case in cases {
            let scratch = tempfile::tempdir().expect("synthetic helper root");
            let root = scratch.path();
            let outside = root
                .parent()
                .expect("temporary parent")
                .join("core-adoption-outside");
            if let Some(initial) = case["initial"].as_object() {
                for (name, entry) in initial.iter() {
                    assert_eq!(entry["kind"].as_str(), Some("dir"));
                    fs::create_dir_all(root.join(name.as_str().expect("directory name")))
                        .expect("helper directory");
                }
            }
            let root_text = root.to_str().expect("UTF-8 synthetic root");
            let path = PathBuf::from(
                case["input"]["path"]
                    .as_str()
                    .expect("helper path")
                    .replace("<root>", root_text)
                    .replace("<outside>", outside.to_str().expect("UTF-8 sibling")),
            );
            let result = match case["operation"].as_str().expect("helper operation") {
                "private_safe_file" => Ok(json!(safe_file(root, &path))),
                "private_safe_directory" => {
                    safe_directory(root, &path, case["input"]["label"].as_str().expect("label"))
                        .map(|()| json!(path))
                }
                "private_safe_parent" => safe_parent(root, &path).map(Value::Bool),
                "private_safe_parent_lstat_failure" => {
                    safe_parent_with_lstat(root, &path, |current| {
                        if current == path {
                            Err(std::io::Error::from_raw_os_error(13))
                        } else {
                            fs::symlink_metadata(current)
                        }
                    })
                    .map(Value::Bool)
                }
                other => panic!("unrecognized pinned helper: {other}"),
            };
            let actual = match result {
                Ok(value) => json!({"value":value}),
                Err(error) => {
                    json!({"error":[error.class,error.message.replace(root_text,"<root>")]})
                }
            };
            assert_eq!(actual, case["expected"].to_serde(), "{}", case["name"]);
        }
        drop_json(fixture);
    }

    #[cfg(unix)]
    #[test]
    fn raw_filename_is_declined_without_filesystem_access() {
        use std::os::unix::ffi::OsStringExt;
        let raw = PathBuf::from(std::ffi::OsString::from_vec(b"raw-\xff".to_vec()));
        let error = admit_path(&raw).expect_err("raw bytes cannot enter a String journal");
        assert_eq!(error.class, "NotImplementedError");
        assert_eq!(check_marker_names(&raw), Err(error));
    }
}
