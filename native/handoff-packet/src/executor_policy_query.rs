//! Buffered policy query. Uncertain parsing or diagnostics decline before output.
use crate::executor_policy::{Policy, load_data};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
};

type Output = (String, String, i32);

// Strict JSON intentionally declines Python extensions, invalid Unicode and deep
// inputs: Python remains the diagnostic oracle for every unadmitted input.
fn read(path: &Path) -> Option<Value> {
    let value: Value = serde_json::from_slice(&fs::read(path).ok()?).ok()?;
    value.is_object().then_some(value)
}

fn uncertain(value: &Value) -> bool {
    match value {
        // Rust trim and Python strip differ for these four control characters.
        Value::String(text) => text.contains(['\u{1c}', '\u{1d}', '\u{1e}', '\u{1f}']),
        Value::Array(items) => items.iter().any(uncertain),
        Value::Object(items) => items.values().any(uncertain),
        _ => false,
    }
}

fn named_path(value: &str, account: &Path, _env: &BTreeMap<String, String>) -> Option<PathBuf> {
    // pathlib and std print alternate Windows separators/UNC prefixes differently.
    #[cfg(windows)]
    if value.contains('/') && !value.starts_with("~/") {
        return None;
    }
    let path = if value.starts_with('~') {
        #[cfg(unix)]
        let home = _env
            .get("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| account.to_owned());
        #[cfg(windows)]
        let home = account.to_owned();
        if value == "~" {
            home
        } else {
            // Includes ~other-account and Windows backslash spellings.
            let rest = value.strip_prefix("~/")?;
            if home.as_os_str().is_empty() {
                return None;
            }
            home.join(rest.trim_start_matches('/'))
        }
    } else {
        value.into()
    };
    // POSIX pathlib retains exactly two leading slashes; std components do not.
    #[cfg(unix)]
    if path.to_str()?.starts_with("//") {
        return None;
    }
    // pathlib removes current-directory and repeated separators, preserving '..'.
    let path: PathBuf = path
        .components()
        .filter(|c| *c != std::path::Component::CurDir)
        .collect();
    Some(if path.as_os_str().is_empty() {
        PathBuf::from(".")
    } else {
        path
    })
}

fn load(root: &Path, account: &Path, env: &BTreeMap<String, String>) -> Option<Policy> {
    let mut warning = String::new();
    let data = load_data(
        root,
        account,
        env,
        &mut warning,
        |path| read(path).ok_or_else(|| "query JSON admission".into()),
        |value| {
            let path = named_path(value, account, env).ok_or("query path admission")?;
            path.to_str().ok_or("query path encoding")?;
            Ok(path)
        },
    )
    .ok()?;
    let declared = data
        .get("delegation")
        .and_then(|d| d.get("mode"))
        .or_else(|| data.get("mode"));
    // Python's frozenset membership raises TypeError on these shapes.
    if declared.is_some_and(|v| v.is_array() || v.is_object()) || uncertain(&data) {
        return None;
    }
    let mut policy = Policy::resolve(&data);
    warning.push_str(&policy.warning);
    policy.warning = warning;
    Some(policy)
}

fn python_json(value: &Value) -> Option<String> {
    let text = serde_json::to_string(value).ok()?;
    let mut output = String::new();
    for ch in text.chars() {
        if ch >= '\u{7f}' {
            for unit in ch.encode_utf16(&mut [0; 2]) {
                output.push_str(&format!("\\u{unit:04x}"));
            }
        } else {
            output.push(ch);
        }
    }
    Some(output)
}

/// `account` is passwd home on Unix and Python's account profile on Windows.
/// Roots retain their spelling: resolving symlinks or '..' changes config lookup.
pub fn query(
    raw: &[OsString],
    cwd: &Path,
    account: &Path,
    env: &BTreeMap<String, String>,
) -> Option<Output> {
    let mut args = raw.iter();
    if args.next()? != "policy-resolve" {
        return None;
    }
    let mut category = None;
    let mut root = cwd.to_owned();
    let mut format = "json";
    let mut seen = BTreeSet::new();
    while let Some(arg) = args.next() {
        let arg = arg.to_str()?;
        let (key, inline) = arg
            .split_once('=')
            .map_or((arg, None), |(k, v)| (k, Some(v)));
        if !matches!(key, "--category" | "--repo-root" | "--format") || !seen.insert(key) {
            return None;
        }
        let value = if let Some(value) = inline {
            value
        } else {
            let value = args.next()?.to_str()?;
            if value.starts_with('-') {
                return None;
            }
            value
        };
        match key {
            "--category" => category = Some(value),
            "--repo-root" => {
                root = if value.is_empty() {
                    PathBuf::from(".")
                } else {
                    value.into()
                }
            }
            "--format" => format = value,
            _ => return None,
        }
    }
    if !matches!(format, "json" | "text") {
        return None;
    }
    let category = category?;
    let root = if root.is_absolute() {
        root
    } else {
        cwd.join(root)
    };
    let policy = load(&root, account, env)?;
    let result = policy.category(category);
    let stdout = if format == "json" {
        format!(
            "{{\"model\": {}, \"reasoning_effort\": {}}}\n",
            python_json(&result["model"])?,
            python_json(&result["reasoning_effort"])?
        )
    } else {
        format!(
            "model={}\nreasoning_effort={}\n",
            result["model"].as_str().unwrap_or(""),
            result["reasoning_effort"].as_str().unwrap_or("")
        )
    };
    Some((stdout, policy.warning, 0))
}

/// Process adapter; never guess an account identity from a session HOME on Unix.
pub fn run(raw: &[OsString], cwd: &Path) -> Option<Output> {
    let env: BTreeMap<String, String> = std::env::vars_os()
        .map(|(k, v)| Some((k.into_string().ok()?, v.into_string().ok()?)))
        .collect::<Option<_>>()?;
    if env.get("PYTHONIOENCODING").is_some_and(|s| {
        !matches!(
            s.split(':')
                .next()
                .unwrap_or("")
                .to_ascii_lowercase()
                .as_str(),
            "" | "utf8" | "utf-8" | "utf_8"
        )
    }) {
        return None;
    }
    #[cfg(unix)]
    let account = crate::account_home::get()?;
    #[cfg(windows)]
    let account = crate::executor_policy::windows_account_home(&env).ok()?;
    query(raw, cwd, &account, &env)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_expanduser_keeps_account_with_repeated_slashes() {
        let account = PathBuf::from("/account");
        let env = BTreeMap::from([("HOME".into(), "/account".into())]);
        assert_eq!(
            named_path("~//policy.json", &account, &env),
            Some(account.join("policy.json"))
        );
    }

    #[test]
    fn python_json_ascii_controls_and_surrogate_pairs() {
        assert_eq!(
            python_json(&serde_json::json!("\u{7f}\u{e9}\u{1f600}\n\"\\")),
            Some(r#""\u007f\u00e9\ud83d\ude00\n\"\\""#.into())
        );
        assert_eq!(python_json(&Value::Null), Some("null".into()));
    }
}
