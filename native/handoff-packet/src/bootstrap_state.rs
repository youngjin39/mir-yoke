//! Version 1 state determination only. The pinned shell remains the caller.
//! Receipt/manifest objects tolerate unknown fields and use the last duplicate
//! key, like jq. Shared by state and enforcement without a subprocess hop.
use regex::Regex;
use serde_json::{Value, json};
use std::{
    fs,
    path::Path,
    process::{Command, Stdio},
};

const OUTPUTS: [&str; 4] = [
    "spec/STATE.md",
    "spec/index.yaml",
    "spec/graph.yaml",
    "spec/gaps.yaml",
];

pub(super) fn read_json(path: &Path) -> Option<Value> {
    serde_json::from_slice(&fs::read(path).ok()?).ok()
}
pub(super) fn regular(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|m| m.is_file())
}
pub(super) fn linked(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|m| m.is_symlink())
}
fn hash(value: &Value, min: usize, max: usize) -> bool {
    value.as_str().is_some_and(|s| {
        (min..=max).contains(&s.len())
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}
fn matches_hash(path: &Path, expected: &Value) -> bool {
    fs::read(path)
        .is_ok_and(|bytes| expected.as_str() == Some(crate::digest::sha256(&bytes).as_str()))
}
fn executable(path: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::metadata(path).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
    }
    #[cfg(not(unix))]
    {
        path.is_file()
    }
}
pub(super) fn logical_directory(path: &Path) -> Option<std::path::PathBuf> {
    use std::path::{Component, PathBuf};
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().ok()?.join(path)
    };
    let mut logical = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::ParentDir => {
                logical.pop();
            }
            Component::CurDir => {}
            _ => logical.push(component.as_os_str()),
        }
    }
    fs::canonicalize(logical).ok()
}
fn unsupported(path: &str) -> bool {
    path.contains('\\')
        || path.chars().any(char::is_control)
        || (path.as_bytes().get(1) == Some(&b':') && path.as_bytes()[0].is_ascii_alphabetic())
}
fn relative(path: &str) -> bool {
    !path.starts_with('/')
        && !path.starts_with("../")
        && !path.contains("/../")
        && !path.ends_with("/..")
}
// Command substitution removes trailing newlines; jq -r leaves strings raw.
fn raw(value: &Value, default: &str) -> String {
    match value {
        Value::Null | Value::Bool(false) => default.into(),
        Value::String(s) => s.trim_end_matches('\n').into(),
        _ => value.to_string(),
    }
}
fn values(value: &Value) -> Vec<&Value> {
    match value {
        Value::Array(a) => a.iter().collect(),
        Value::Object(o) => o.values().collect(),
        _ => Vec::new(),
    }
}
fn provider(root: &Path) -> bool {
    let profile = root.join(".mir/repo-profile.toml");
    if !regular(&profile) {
        return false;
    }
    let Ok(text) = fs::read_to_string(profile) else {
        return false;
    };
    let field = |name: &str, value: &str| {
        Regex::new(&format!(
            r#"(?m)^[\t\r\n\x0b\x0c ]*{name}[\t ]*=[\t ]*"{value}""#
        ))
        .is_ok_and(|re| re.is_match(&text))
    };
    if !field("slug", "mir-yoke") || !field("repository_type", "public_harness_template") {
        return false;
    }
    Command::new("git")
        .args(["--no-replace-objects", "--no-lazy-fetch", "-C"])
        .arg(root)
        .args(["remote", "get-url", "origin"])
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .is_ok_and(|o| {
            matches!(
                std::str::from_utf8(&o.stdout).map(|s| s.trim_end_matches('\n')),
                Ok("https://github.com/youngjin39/mir-yoke.git"
                    | "git@github.com:youngjin39/mir-yoke.git")
            )
        })
}
fn native_verdict(root: &Path, receipt: &Value) -> Option<bool> {
    if std::env::var_os("MIR_NATIVE_HOOKS").is_some_and(|v| v == "0")
        || linked(&root.join(".mir"))
        || linked(&root.join(".mir/bin"))
    {
        return None;
    }
    let pin = &receipt["native_evaluator"];
    let path = root.join(".mir/bin/bootstrap-gate");
    if pin["path"] != ".mir/bin/bootstrap-gate"
        || !hash(&pin["sha256"], 64, 64)
        || !regular(&path)
        || !executable(&path)
        || !matches_hash(&path, &pin["sha256"])
    {
        return None;
    }
    let result = Command::new(path)
        .arg(root)
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .ok()?;
    match (result.status.code(), result.stdout.as_slice()) {
        (Some(0), b"ready\n") => Some(true),
        (Some(1), b"invalid\n") => Some(false),
        _ => None,
    }
}
fn settings_hash(path: &Path, expected: &Value) -> bool {
    fs::read(path)
        .ok()
        .and_then(|bytes| crate::bootstrap_json::hook_hash(&bytes))
        .as_deref()
        == expected.as_str()
}
fn adoption(root: &Path, receipt: &Value) -> bool {
    if let Some(verdict) = native_verdict(root, receipt) {
        return verdict;
    }
    let path = root.join("config/bootstrap-adoption.json");
    if !regular(&path) || !matches_hash(&path, &receipt["manifest"]["sha256"]) {
        return false;
    }
    let Some(manifest) = read_json(&path) else {
        return false;
    };
    let source = raw(&manifest["mir_yoke_source_commit"], "");
    if source.is_empty() || source != raw(&receipt["source"]["mir_yoke_commit"], "") {
        return false;
    }
    let mut declared: Vec<String> = values(&manifest["surfaces"])
        .into_iter()
        .flat_map(|s| values(&s["evidence_paths"]))
        .map(|v| raw(v, "null"))
        .collect();
    declared.sort();
    declared.dedup();
    let Some(rows) = receipt["evidence"].as_array().filter(|a| !a.is_empty()) else {
        return false;
    };
    let mut paths = Vec::new();
    for row in rows {
        let Some(path) = row["path"].as_str() else {
            return false;
        };
        if path.is_empty() || !relative(path) || !hash(&row["sha256"], 64, 64) {
            return false;
        }
        paths.push(path.to_string());
        // jq @tsv escapes controls and backslashes before read -r sees the path.
        let escaped = path
            .replace('\\', "\\\\")
            .replace('\t', "\\t")
            .replace('\r', "\\r")
            .replace('\n', "\\n");
        let file = root.join(escaped);
        if !regular(&file)
            || (!matches_hash(&file, &row["sha256"])
                && (path != ".claude/settings.json" || !settings_hash(&file, &row["sha256"])))
        {
            return false;
        }
    }
    paths.sort();
    !declared.is_empty() && paths == declared
}
fn runtime(root: &Path, cli: &Value) -> bool {
    if cli["externalized"] != true
        || !hash(&cli["sha256"], 64, 64)
        || !hash(&cli["runtime_manifest_sha256"], 64, 64)
        || !hash(&cli["source_commit"], 40, 64)
        || !hash(&cli["constraints_sha256"], 64, 64)
    {
        return false;
    }
    for name in ["executable", "runtime_manifest", "source_url"] {
        if !cli[name].as_str().is_some_and(|s| !s.is_empty()) {
            return false;
        }
    }
    let cli_name = raw(&cli["executable"], "");
    let Some(project) = root.to_str() else {
        return false;
    };
    if cli_name == project || cli_name.starts_with(&format!("{project}/")) {
        return false;
    }
    let path = Path::new(&cli_name);
    if !executable(path) || !matches_hash(path, &cli["sha256"]) {
        return false;
    }
    // Bash cd defaults to logical traversal: collapse dirname/.. before pwd -P
    // resolves symlinks. A linked bin directory must not change the runtime root.
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let Some(runtime_root) = logical_directory(&parent.join("..")) else {
        return false;
    };
    let manifest_name = raw(&cli["runtime_manifest"], "");
    let manifest = Path::new(&manifest_name);
    if manifest.as_os_str() != runtime_root.join("runtime-manifest.json").as_os_str()
        || !regular(manifest)
        || !matches_hash(manifest, &cli["runtime_manifest_sha256"])
    {
        return false;
    }
    Command::new(path)
        .args(["runtime-manifest", "verify", "--runtime-root"])
        .arg(runtime_root)
        .arg("--manifest")
        .arg(manifest)
        .arg("--source-url")
        .arg(raw(&cli["source_url"], ""))
        .arg("--source-commit")
        .arg(raw(&cli["source_commit"], ""))
        .arg("--constraints-sha256")
        .arg(raw(&cli["constraints_sha256"], ""))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|s| s.success())
}
fn greenfield(root: &Path, receipt: &Value) -> bool {
    let architecture = &receipt["architecture_initialization"];
    let Some(outputs) = architecture["evidence"]["output_hashes"].as_object() else {
        return false;
    };
    if receipt["capabilities"]["status"] != "ready"
        || !matches!(
            receipt["slim"]["status"].as_str(),
            Some("applied" | "already_slim")
        )
        || architecture["attested"] != true
        || outputs.len() != 4
        || !OUTPUTS
            .iter()
            .all(|p| outputs.get(*p).is_some_and(|v| hash(v, 64, 64)))
    {
        return false;
    }
    if !runtime(root, &receipt["cli"])
        || root.join(".mir/slim-transaction.json").exists()
        || root.join(".mir/slim.lock").exists()
    {
        return false;
    }
    let boundary_path = root.join("config/adopter-boundary.json");
    if !regular(&boundary_path) {
        return false;
    }
    // The shell ignores jq extraction errors here; a malformed boundary supplies
    // no markers. Its schema validation belongs to the separate adoption checker.
    let boundary = read_json(&boundary_path).unwrap_or(Value::Null);
    for marker in values(&boundary["provider_markers"]) {
        let path = raw(marker, "null");
        if path.is_empty() {
            continue;
        }
        let file = root.join(&path);
        if !relative(&path) || file.exists() || linked(&file) {
            return false;
        }
    }
    for marker in values(&boundary["provider_text_markers"]) {
        let (path, text) = (raw(&marker["path"], ""), raw(&marker["contains"], ""));
        if path.is_empty() || text.is_empty() {
            continue;
        }
        if !relative(&path) {
            return false;
        }
        if fs::read(root.join(&path))
            .is_ok_and(|b| b.windows(text.len()).any(|w| w == text.as_bytes()))
        {
            return false;
        }
    }
    OUTPUTS
        .iter()
        .all(|path| regular(&root.join(path)) && matches_hash(&root.join(path), &outputs[*path]))
}

pub fn evaluate(root: &Path) -> (Value, i32) {
    let unsupported_result = || {
        (
            json!({"schema":"mir.bootstrap-state@1","supported":false,"state":null,"mode":null,"shell_exit":null}),
            64,
        )
    };
    let Some(root_text) = root.to_str() else {
        return unsupported_result();
    };
    if cfg!(windows) || unsupported(root_text) {
        return unsupported_result();
    }
    let receipt_path = root.join(".mir/bootstrap-receipt.json");
    let provider_source = provider(root);
    // The shell decides exemption/missing/linked receipt before opening JSON.
    // In particular, never open a FIFO or device while checking for a receipt.
    let receipt = if !provider_source && regular(&receipt_path) {
        read_json(&receipt_path).unwrap_or(Value::Null)
    } else {
        Value::Null
    };
    let is_adoption = receipt["mode"] == "existing_repository_adoption"
        || root.join("config/bootstrap-adoption.json").exists();
    let mut mode = if is_adoption {
        "adoption"
    } else {
        "greenfield"
    };
    let state = if provider_source {
        mode = "provider";
        "template_maintainer".into()
    } else if !receipt_path.is_file() {
        "missing".into()
    } else if linked(&receipt_path) {
        "invalid".into()
    } else {
        let status = raw(&receipt["status"], "invalid");
        if status == "restart_required" || (status == "ready" && !is_adoption) {
            for key in ["executable", "runtime_manifest"] {
                if receipt["cli"][key].as_str().is_some_and(unsupported) {
                    return unsupported_result();
                }
            }
        }
        match status.as_str() {
            "restart_required" if !runtime(root, &receipt["cli"]) => "invalid".into(),
            "ready"
                if !(if is_adoption {
                    adoption(root, &receipt)
                } else {
                    greenfield(root, &receipt)
                }) =>
            {
                "invalid".into()
            }
            _ => status,
        }
    };
    let code = i32::from(state != "ready" && mode != "provider");
    (
        json!({"schema":"mir.bootstrap-state@1","supported":true,"state":state,"mode":mode,"shell_exit":code}),
        code,
    )
}
