//! Resolve npm command shims without changing explicit CODEX_BIN overrides.
use std::collections::BTreeMap;
use std::ffi::OsString;

pub fn windows_codex_binary(path: &str, pathext: &str, is_file: impl Fn(&str) -> bool) -> String {
    if !path.is_empty() {
        let extensions = if pathext.is_empty() {
            ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WS;.MSC"
        } else {
            pathext
        };
        for directory in path.split(';') {
            for extension in extensions.split(';').filter(|ext| !ext.is_empty()) {
                let separator = if directory.is_empty()
                    || directory.ends_with(['\\', '/'])
                    || directory.ends_with(':')
                {
                    ""
                } else {
                    "\\"
                };
                let candidate = format!(
                    "{directory}{separator}codex{}",
                    extension.trim_end_matches('.')
                );
                if is_file(&candidate) {
                    return candidate;
                }
            }
        }
    }
    "codex".into()
}

pub fn resolve(environment: &BTreeMap<OsString, OsString>) -> String {
    let value = |name: &str| {
        environment.iter().find_map(|(key, value)| {
            let key = key.to_str()?;
            (key == name || cfg!(windows) && key.eq_ignore_ascii_case(name))
                .then(|| value.to_str())
                .flatten()
        })
    };
    if let Some(binary) = value("CODEX_BIN").filter(|s| !s.is_empty()) {
        return binary.to_owned();
    }
    if cfg!(windows) {
        windows_codex_binary(
            value("PATH").unwrap_or(""),
            value("PATHEXT").unwrap_or(""),
            |candidate| std::path::Path::new(candidate).is_file(),
        )
    } else {
        "codex".into()
    }
}
