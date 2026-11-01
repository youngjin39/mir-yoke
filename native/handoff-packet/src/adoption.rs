//! Partial adoption-only evaluator. None means defer unchanged to the shell.
//! Unknown JSON fields are tolerated just as jq tolerates them; ambiguous shapes
//! and duplicate JSON keys are deliberately outside this evaluator's contract.
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

fn json(bytes: &[u8]) -> Option<Value> {
    let value = serde_json::from_slice(bytes).ok()?;
    // serde_json normally keeps the last duplicate key. Refuse that ambiguity.
    let mut objects: Vec<BTreeSet<String>> = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'{' => objects.push(BTreeSet::new()),
            b'}' => {
                objects.pop()?;
            }
            b'"' => {
                let start = i;
                i += 1;
                while i < bytes.len() && bytes[i] != b'"' {
                    if bytes[i] == b'\\' {
                        i += 1;
                    }
                    i += 1;
                }
                let end = i.checked_add(1)?;
                let mut next = end;
                while bytes.get(next).is_some_and(u8::is_ascii_whitespace) {
                    next += 1;
                }
                if bytes.get(next) == Some(&b':') {
                    let key: String = serde_json::from_slice(bytes.get(start..end)?).ok()?;
                    if !objects.last_mut()?.insert(key) {
                        return None;
                    }
                }
            }
            _ => {}
        }
        i += 1;
    }
    Some(value)
}

// jq uses IEEE-754 numbers. Only exactly representable signed integers are
// admitted here; other spellings and values must be decided by the shell.
fn jq_exact(value: &Value) -> bool {
    match value {
        Value::Number(n) => n
            .as_i64()
            .is_some_and(|n| n.unsigned_abs() <= 9_007_199_254_740_991),
        Value::Array(values) => values.iter().all(jq_exact),
        Value::Object(values) => values.values().all(jq_exact),
        _ => true,
    }
}

fn settings_hook_digest(bytes: &[u8]) -> Option<Option<String>> {
    let settings = json(bytes)?;
    if !jq_exact(&settings) {
        return None;
    }
    let Some(hooks) = settings.get("hooks").and_then(Value::as_object) else {
        return Some(None);
    };
    if hooks.is_empty() {
        return Some(None);
    }
    // Default serde_json maps sort keys as jq -S does. jq also escapes DEL.
    let mut canonical = serde_json::to_string(&serde_json::json!({"hooks": hooks}))
        .ok()?
        .replace('\u{7f}', "\\u007f");
    canonical.push('\n');
    Some(Some(crate::digest::sha256(canonical.as_bytes())))
}

fn text(value: &Value) -> Option<&str> {
    let s = value.as_str()?;
    // jq's command substitution and @tsv escaping change these strings.
    (!s.chars().any(|c| c.is_control() || c == '\\')).then_some(s)
}

fn hash(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub fn evaluate(root: &Path) -> Option<bool> {
    // POSIX shell path and hash-program spelling are the measured contract.
    // Windows dispatch remains shell until a real bash/native parity lane exists.
    if cfg!(windows) || root.to_str()?.chars().any(|c| c.is_control() || c == '\\') {
        return None;
    }
    let profile = root.join(".mir/repo-profile.toml");
    if profile.exists() {
        let profile = fs::read_to_string(profile).ok()?;
        // Provider exemption belongs to shell (including its git-origin check).
        if profile.contains("mir-yoke") && profile.contains("public_harness_template") {
            return None;
        }
    }
    let receipt_path = root.join(".mir/bootstrap-receipt.json");
    let receipt_meta = fs::symlink_metadata(&receipt_path).ok()?;
    if receipt_meta.is_symlink() && receipt_path.is_file() {
        return Some(false);
    }
    if !receipt_meta.is_file() {
        return None;
    }
    let receipt = json(&fs::read(receipt_path).ok()?)?;
    if receipt.get("status")?.as_str()? != "ready" {
        return None;
    }
    let manifest_path = root.join("config/bootstrap-adoption.json");
    let mode = match receipt.get("mode") {
        None | Some(Value::Null) | Some(Value::Bool(false)) => "",
        Some(value) => text(value)?,
    };
    if mode != "existing_repository_adoption" && !manifest_path.exists() {
        return None;
    }
    if fs::symlink_metadata(&manifest_path).ok()?.is_symlink() && manifest_path.is_file() {
        return Some(false);
    }
    if !fs::symlink_metadata(&manifest_path).ok()?.is_file() {
        return None;
    }
    let manifest_bytes = fs::read(&manifest_path).ok()?;
    let manifest = json(&manifest_bytes)?;
    let expected = text(receipt.get("manifest")?.get("sha256")?)?;
    let source = text(manifest.get("mir_yoke_source_commit")?)?;
    let receipt_source = text(receipt.get("source")?.get("mir_yoke_commit")?)?;
    if crate::digest::sha256(&manifest_bytes) != expected
        || source.is_empty()
        || source != receipt_source
    {
        return Some(false);
    }
    let surfaces = manifest.get("surfaces")?;
    let surface_values: Vec<&Value> = match surfaces {
        Value::Object(o) => o.values().collect(),
        Value::Array(a) => a.iter().collect(),
        _ => return None,
    };
    let mut declared = BTreeSet::new();
    for surface in surface_values {
        if let Some(paths) = surface.get("evidence_paths") {
            if paths.is_null() {
                continue;
            }
            for path in paths.as_array()? {
                declared.insert(text(path)?);
            }
        }
    }
    let evidence = receipt.get("evidence")?.as_array()?;
    let mut rows = Vec::new();
    for row in evidence {
        let path = text(row.get("path")?)?;
        let sha = text(row.get("sha256")?)?;
        if !hash(sha) {
            return Some(false);
        }
        rows.push((path, sha));
    }
    let mut paths: Vec<_> = rows.iter().map(|(path, _)| *path).collect();
    paths.sort();
    let declared: Vec<_> = declared.into_iter().collect();
    if paths.is_empty() || declared.is_empty() || paths != declared {
        return Some(false);
    }
    for (path, sha) in rows {
        if path.is_empty()
            || path.starts_with('/')
            || path.starts_with("../")
            || path.contains("/../")
            || path.ends_with("/..")
        {
            return Some(false);
        }
        let is_settings = path == ".claude/settings.json";
        let path = root.join(path);
        match fs::symlink_metadata(&path) {
            Ok(meta) if meta.is_file() => {}
            Ok(_) => return Some(false),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Some(false),
            Err(_) => return None,
        }
        // Shell rejects only a leaf symlink; ancestor symlinks remain equivalent.
        let bytes = fs::read(path).ok()?;
        if crate::digest::sha256(&bytes) != sha
            && (!is_settings || settings_hook_digest(&bytes)?.as_deref() != Some(sha))
        {
            return Some(false);
        }
    }
    Some(true)
}
