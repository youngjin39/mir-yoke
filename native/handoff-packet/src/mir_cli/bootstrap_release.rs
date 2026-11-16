//! Release identity, byte guards and Git ownership helpers for the library port.
use super::authored::{
    atomic_write_text, attribute_error, decode, json_text, python_str, read_error, read_text, run,
    valid_commit,
};
use super::{Error, Host};
use crate::mir_cli::bootstrap_adoption::{is_python_space, python_splitlines};
use regex::Regex;
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::Path, sync::LazyLock};

pub fn release_payload_digests(root: &Path) -> Result<BTreeMap<String, String>, Error> {
    let payload = match json_text(&root.join("config/adopter-payload.json")) {
        Ok(v) => v,
        Err(e) if e.class == "JSONDecodeError" || e.class != "UnicodeDecodeError" => {
            return Ok(BTreeMap::new());
        }
        Err(e) => return Err(e),
    };
    if !payload.is_object() {
        return Err(attribute_error(&payload, "get"));
    }
    let mut result = BTreeMap::new();
    let files = payload.get("files").cloned().unwrap_or_else(|| json!([]));
    // Python iterates strings and mapping keys too, none of which are dict records.
    if files.is_string() || files.is_object() {
        return Ok(result);
    }
    let Some(files) = files.as_array() else {
        let class = if files.is_null() {
            "NoneType"
        } else if files.is_boolean() {
            "bool"
        } else if files.as_number().is_some_and(|n| n.is_f64()) {
            "float"
        } else {
            "int"
        };
        return Err(Error::new(
            "TypeError",
            format!("'{class}' object is not iterable"),
        ));
    };
    for item in files.iter().filter(|v| v.is_object()) {
        result.insert(python_str(&item["path"]), python_str(&item["sha256"]));
    }
    Ok(result)
}
pub fn is_safe_existing_project_file(root: &Path, path: &Path) -> bool {
    let Ok(resolved) = path.canonicalize() else {
        return false;
    };
    // On Windows canonicalize adds a verbatim prefix; both operands must use it.
    let resolved_root = if cfg!(windows) {
        root.canonicalize().ok()
    } else {
        Some(root.into())
    };
    if !resolved_root.is_some_and(|root| resolved.starts_with(root)) {
        return false;
    }
    let Ok(relative) = path.strip_prefix(root) else {
        return false;
    };
    let mut current = root.to_path_buf();
    for part in relative.components() {
        current.push(part);
        if current.is_symlink() {
            return false;
        }
    }
    path.is_file()
}
// load_boundary's validation is kept distinct from adopter policy validation.
fn safe_relative(value: &Value) -> bool {
    value.as_str().is_some_and(|s| {
        !s.is_empty()
            && !s.contains('\\')
            && !s.starts_with('/')
            && !s.split('/').any(|p| p == "..")
    })
}
fn boundary(root: &Path, host: &mut impl Host) -> Result<Option<Value>, Error> {
    let mut value = match json_text(&root.join("config/adopter-boundary.json")) {
        Ok(v) => v,
        Err(e) if e.class == "UnicodeDecodeError" => return Err(e),
        Err(_) => return Ok(None),
    };
    if !value.is_object()
        || !(value["schema_version"].as_f64() == Some(1.0) || value["schema_version"] == true)
    {
        return Ok(None);
    }
    if let Some(schema_ref) = value["$schema"].as_str() {
        let schema = match json_text(&root.join("config").join(schema_ref)) {
            Ok(schema) => schema,
            Err(e) if e.class == "UnicodeDecodeError" => return Err(e),
            Err(_) => return Ok(None),
        };
        match host.validate_boundary_schema(&value, &schema) {
            Ok(()) => {}
            Err(e) if e.class == "ValidationError" => return Ok(None),
            Err(e) => return Err(e),
        }
    }
    let Some(markers) = value["provider_markers"].as_array() else {
        return Ok(None);
    };
    if markers.is_empty() || !markers.iter().all(safe_relative) {
        return Ok(None);
    }
    let Some(markers) = value["provider_text_markers"].as_array() else {
        return Ok(None);
    };
    if markers.iter().any(|m| {
        !m.is_object()
            || !safe_relative(&m["path"])
            || !m["contains"].as_str().is_some_and(|s| !s.is_empty())
    }) {
        return Ok(None);
    }
    // PurePosixPath removes repeated separators and '.' parts before returning the boundary.
    fn relative(value: &mut Value) {
        if let Some(text) = value.as_str() {
            let text = text
                .split('/')
                .filter(|s| !s.is_empty() && *s != ".")
                .collect::<Vec<_>>()
                .join("/");
            *value = json!(if text.is_empty() { "." } else { &text });
        }
    }
    if let Some(markers) = value["provider_markers"].as_array_mut() {
        markers.iter_mut().for_each(relative);
    }
    if let Some(markers) = value["provider_text_markers"].as_array_mut() {
        for marker in markers {
            relative(&mut marker["path"]);
        }
    }
    Ok(Some(value))
}
pub fn is_raw_provider_checkout(root: &Path, host: &mut impl Host) -> Result<bool, Error> {
    let Some(boundary) = boundary(root, host)? else {
        return Ok(false);
    };
    let output = run(root, &["git", "rev-parse", "HEAD"], true, host)?;
    let stdout = decode(output.stdout)?;
    let commit = stdout.trim_matches(is_python_space);
    if output.returncode != 0 || !valid_commit(commit) {
        return Ok(false);
    }
    for relative in [
        "config/adopter-boundary.json",
        "config/adopter-payload.json",
    ] {
        let path = root.join(relative);
        let object = format!("{commit}:{relative}");
        let output = run(root, &["git", "show", &object], false, host)?;
        if output.returncode != 0 || !is_safe_existing_project_file(root, &path) {
            return Ok(false);
        }
        if fs::read(&path).map_err(|e| read_error(&path, e))? != output.stdout {
            return Ok(false);
        }
    }
    let digests = release_payload_digests(root)?;
    let contract = root.join("CLAUDE.md");
    if !is_safe_existing_project_file(root, &contract) {
        return Ok(false);
    }
    let digest = crate::digest::sha256(&fs::read(&contract).map_err(|e| read_error(&contract, e))?);
    if digests.get("CLAUDE.md") != Some(&digest) {
        return Ok(false);
    }
    let mut has_contract = false;
    for marker in boundary["provider_text_markers"]
        .as_array()
        .into_iter()
        .flatten()
    {
        if marker["path"] == "CLAUDE.md"
            && let Some(contains) = marker["contains"].as_str()
            && read_text(&contract)?.contains(contains)
        {
            has_contract = true;
            break;
        }
    }
    let has_payload = boundary["provider_markers"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .any(|relative| {
            let path = root.join(relative);
            path.exists() || path.is_symlink()
        });
    Ok(has_contract && has_payload)
}
pub fn rewrite_release_matched(
    root: &Path,
    updates: &[(String, String)],
) -> Result<Vec<String>, Error> {
    let entries = release_payload_digests(root)?;
    let mut changed = vec![];
    for (relative, body) in updates {
        let path = root.join(relative);
        let Some(expected) = entries.get(relative).filter(|s| !s.is_empty()) else {
            continue;
        };
        if !is_safe_existing_project_file(root, &path) {
            continue;
        }
        if crate::digest::sha256(&fs::read(&path).map_err(|e| read_error(&path, e))?) == *expected {
            atomic_write_text(&path, body)?;
            changed.push(relative.clone());
        }
    }
    Ok(changed)
}
static SCHEME: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(r"^[A-Za-z][A-Za-z0-9+.-]*://"));
fn remove_user(value: &str) -> &str {
    if let Some((user, tail)) = value.split_once('@')
        && !user.is_empty()
        && !user.contains('/')
    {
        return tail;
    }
    value
}
// urlsplit boundary used here: no decoding, userinfo ignored, default ports elided.
fn split_url(raw: &str, scheme_end: usize) -> Option<String> {
    let raw: String = raw
        .chars()
        .filter(|c| !matches!(c, '\t' | '\r' | '\n'))
        .collect();
    let rest = raw.get(scheme_end..)?;
    let end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
    let authority = rest[..end].rsplit('@').next().unwrap_or("");
    let (host, port) = if let Some(tail) = authority.strip_prefix('[') {
        let (host, tail) = tail.split_once(']')?;
        if host.parse::<std::net::Ipv6Addr>().is_err() && !host.starts_with('v') {
            return None;
        }
        (
            host,
            if tail.is_empty() {
                None
            } else {
                Some(tail.strip_prefix(':')?)
            },
        )
    } else {
        if authority.contains(['[', ']']) {
            return None;
        }
        authority
            .split_once(':')
            .map_or((authority, None), |(host, port)| (host, Some(port)))
    };
    let port = match port {
        None | Some("") => 0,
        Some(s) if s.bytes().all(|b| b.is_ascii_digit()) => s.parse::<u16>().ok()?,
        Some(_) => return None,
    };
    let scheme = raw[..scheme_end - 3].to_lowercase();
    let host =
        if port != 0 && !((scheme == "ssh" && port == 22) || (scheme == "https" && port == 443)) {
            format!("{host}:{port}")
        } else {
            host.into()
        };
    let path = &rest[end..];
    let path = &path[..path.find(['?', '#']).unwrap_or(path.len())];
    Some(format!(
        "{}/{path}",
        host.to_lowercase(),
        path = path.trim_start_matches('/')
    ))
}
pub fn normalise_git_url(value: &str) -> String {
    let raw = value.trim_matches(is_python_space).replace('\\', "/");
    let mut normalised = if let Some(found) = SCHEME.as_ref().ok().and_then(|p| p.find(&raw)) {
        split_url(&raw, found.end()).unwrap_or_else(|| remove_user(&raw[found.end()..]).into())
    } else {
        let value = remove_user(&raw);
        if let Some((head, tail)) = value.split_once(':')
            && !head.is_empty()
            && !head.contains('/')
        {
            format!("{head}/{tail}")
        } else {
            value.into()
        }
    };
    // Input is stripped and urlsplit drops newlines: Python "$" never sees a final newline.
    if let Some(body) = normalised.strip_suffix(".git/") {
        normalised.truncate(body.len());
    } else if let Some(body) = normalised.strip_suffix(".git") {
        normalised.truncate(body.len());
    }
    normalised.trim_end_matches('/').to_lowercase()
}
const OWNERSHIP_GUIDANCE: &str = concat!(
    "Git push remote still targets the Mir Yoke provider. ",
    "Rename it (for example: git remote rename origin mir-yoke-upstream), ",
    "disable provider pushes (git remote set-url --push mir-yoke-upstream DISABLED), ",
    "then optionally add a product-owned origin."
);
fn sorted_lines(bytes: Vec<u8>) -> Result<Vec<String>, Error> {
    let stdout = decode(bytes)?;
    let mut lines: Vec<_> = python_splitlines(&stdout)
        .into_iter()
        .map(|s| s.trim_matches(is_python_space))
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect();
    lines.sort();
    Ok(lines)
}
pub fn source_control_ownership(root: &Path, host: &mut impl Host) -> Result<Value, Error> {
    let config = match json_text(&root.join("config/capability-sources.json")) {
        Ok(v) => Some(v),
        Err(e) if e.class == "UnicodeDecodeError" => return Err(e),
        Err(_) => None,
    };
    let provider = config
        .as_ref()
        .and_then(|c| c.get("source"))
        .and_then(|s| s.get("url"))
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty());
    let Some(provider) = provider else {
        return Ok(
            json!([["Git ownership cannot be verified: provider source is unavailable."],
            {"status":"provider_source_unavailable"}]),
        );
    };
    let provider = normalise_git_url(provider);
    let remotes = run(root, &["git", "remote"], true, host)?;
    if remotes.returncode != 0 {
        return Ok(json!([[],{"status":"local_only","provider":provider,"remotes":[]}]));
    }
    let mut evidence = vec![];
    let mut rejected = vec![];
    for remote in sorted_lines(remotes.stdout)? {
        let completed = run(
            root,
            &["git", "remote", "get-url", "--push", "--all", &remote],
            true,
            host,
        )?;
        let urls = if completed.returncode == 0 {
            sorted_lines(completed.stdout)?
        } else {
            vec![]
        };
        let mut destinations: Vec<_> = urls.iter().map(|s| normalise_git_url(s)).collect();
        if destinations.contains(&provider) {
            rejected.push(remote.clone());
        }
        destinations.sort();
        evidence.push(json!({"name":remote,"push_destinations":destinations}));
    }
    if !rejected.is_empty() {
        return Ok(
            json!([[format!("{OWNERSHIP_GUIDANCE} Provider push remote(s): {}.",
            rejected.join(", "))],{"status":"provider_push_rejected","provider":provider,
            "remotes":evidence}]),
        );
    }
    Ok(
        json!([[],{"status":if evidence.is_empty() {"local_only"} else {"product_owned"},
        "provider":provider,"remotes":evidence}]),
    )
}
