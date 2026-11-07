//! Library-only bootstrap identity, argument and storage policy.
#[path = "bootstrap_content.rs"]
mod content;
use super::bootstrap_adoption::is_python_space;
use crate::executor_execute::repr;
pub use content::{
    acceptance_query, build_content_onboarding, content_archive_args, content_archive_globs,
    discoverable_content_files, load_content_onboarding, parse_content_archives,
    project_definition_text, project_relative, scan_content_candidates, supported_content_files,
};
use regex::Regex;
use serde_json::{Value, json};
use std::{
    fmt,
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error {
    pub class: &'static str,
    pub message: String,
}
impl Error {
    pub fn new(class: &'static str, message: impl Into<String>) -> Self {
        Self {
            class,
            message: message.into(),
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for Error {}

/// All process environment and storage observations are supplied by the caller.
pub trait Host {
    fn env(&mut self, name: &str) -> Option<String>;
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error>;
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error>;
    fn is_dir(&mut self, path: &Path) -> bool;
    fn writable(&mut self, path: &Path) -> bool;
    fn device(&mut self, path: &Path) -> Result<u64, Error>;
}
pub const EXTERNAL_STORAGE_PATHS: [(&str, &str); 3] = [
    ("UV_CACHE_DIR", "uv/cache"),
    ("UV_PYTHON_INSTALL_DIR", "uv/python"),
    ("MIR_CAPABILITY_HOME", "mir/capabilities"),
];

#[derive(Debug, Clone)]
pub struct ParseOutput {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
    pub value: Option<Value>,
}
const USAGE: &str = concat!(
    "usage: mir bootstrap [-h] [--project-root PROJECT_ROOT] [--slug SLUG]\n",
    "                     --profile PROFILE [--purpose PURPOSE] [--stack STACK]\n",
    "                     [--archive CLASSIFICATION=PATH]\n",
    "                     [--storage-root STORAGE_ROOT] [--json] [--finalize]\n",
    "                     [--architecture-initialized]\n",
    "                     [--skip-capability-activation]\n",
);
const OPTIONS: [&str; 14] = [
    "--help",
    "--project-root",
    "--slug",
    "--profile",
    "--purpose",
    "--stack",
    "--archive",
    "--storage-root",
    "--json",
    "--finalize",
    "--architecture-initialized",
    "--skip-capability-activation",
    "--allow-incomplete",
    "-h",
];
fn parse_error(message: String) -> ParseOutput {
    ParseOutput {
        code: 2,
        stdout: String::new(),
        stderr: format!("{USAGE}mir bootstrap: error: {message}\n"),
        value: None,
    }
}
fn help() -> String {
    format!(
        "{USAGE}\noptions:\n{}",
        concat!(
            "  -h, --help            show this help message and exit\n",
            "  --project-root PROJECT_ROOT\n",
            "  --slug SLUG\n",
            "  --profile PROFILE     required project archetype; no implicit code_app\n",
            "                        default\n",
            "  --purpose PURPOSE     non-placeholder project mission (required in phase 1)\n",
            "  --stack STACK         technology or working-medium item; repeat or pass\n",
            "                        comma-separated values\n",
            "  --archive CLASSIFICATION=PATH\n",
            "                        classify an existing content path for onboarding\n",
            "                        (content_workspace)\n",
            "  --storage-root STORAGE_ROOT\n",
            "                        shared external-volume root configured by setup.sh\n",
            "  --json\n",
            "  --finalize            phase 2: verify capabilities after restarting the\n",
            "                        agent runtime\n",
            "  --architecture-initialized\n",
            "                        attest that mir-core:design then mir-core:spec-\n",
            "                        architect initialized the project\n",
            "  --skip-capability-activation\n",
            "                        test/development only: leave bootstrap incomplete\n",
            "                        unless --allow-incomplete\n",
        )
    )
}
/// Mirror argparse's observable namespace and its stdout/stderr exit boundary.
pub fn parse(argv: &[String], cwd: &Path) -> ParseOutput {
    let mut value = json!({"project_root": cwd, "slug": null, "profile": null,
        "purpose": null, "stack": [], "archive": [], "storage_root": null,
        "json": false, "finalize": false, "architecture_initialized": false,
        "skip_capability_activation": false, "allow_incomplete": false});
    let mut unknown = Vec::new();
    let mut index = 0;
    let mut positional = false;
    while index < argv.len() {
        let arg = &argv[index];
        if arg == "--" {
            positional = true;
            unknown.push(arg.clone());
            index += 1;
            continue;
        }
        let (authored, explicit) = arg
            .split_once('=')
            .map_or((arg.as_str(), None), |(name, value)| (name, Some(value)));
        if !positional && arg.starts_with("-h") && arg != "-h" {
            return parse_error(format!(
                "argument -h/--help: ignored explicit argument {}",
                repr(explicit.unwrap_or(&arg[2..]))
            ));
        }
        let matches: Vec<_> = OPTIONS
            .iter()
            .copied()
            .filter(|option| {
                !positional
                    && (*option == authored
                        || authored.starts_with("--") && option.starts_with(authored))
            })
            .collect();
        let option = if OPTIONS.contains(&authored) && !positional {
            authored
        } else if matches.len() == 1 {
            matches[0]
        } else if matches.len() > 1 {
            return parse_error(format!(
                "ambiguous option: {authored} could match {}",
                matches.join(", ")
            ));
        } else {
            unknown.push(arg.clone());
            index += 1;
            continue;
        };
        let flag = matches!(
            option,
            "--help"
                | "-h"
                | "--json"
                | "--finalize"
                | "--architecture-initialized"
                | "--skip-capability-activation"
                | "--allow-incomplete"
        );
        if flag {
            if let Some(explicit) = explicit {
                let option = if matches!(option, "--help" | "-h") {
                    "-h/--help"
                } else {
                    option
                };
                return parse_error(format!(
                    "argument {option}: ignored explicit argument {}",
                    repr(explicit)
                ));
            }
            if matches!(option, "--help" | "-h") {
                return ParseOutput {
                    code: 0,
                    stdout: help(),
                    stderr: String::new(),
                    value: None,
                };
            }
            value[option.trim_start_matches('-').replace('-', "_")] = json!(true);
        } else {
            let raw = if let Some(explicit) = explicit {
                explicit
            } else {
                index += 1;
                let Some(next) = argv.get(index).filter(|next| !is_option(next)) else {
                    return parse_error(format!("argument {option}: expected one argument"));
                };
                next
            };
            let key = option.trim_start_matches('-').replace('-', "_");
            if matches!(option, "--stack" | "--archive") {
                if let Some(items) = value[&key].as_array_mut() {
                    items.push(json!(raw));
                }
            } else if matches!(option, "--project-root" | "--storage-root") {
                value[&key] = json!(authored_path(raw));
            } else {
                value[&key] = json!(raw);
            }
        }
        index += 1;
    }
    if value["profile"].is_null() {
        return parse_error("the following arguments are required: --profile".into());
    }
    if !unknown.is_empty() {
        return parse_error(format!("unrecognized arguments: {}", unknown.join(" ")));
    }
    ParseOutput {
        code: 0,
        stdout: String::new(),
        stderr: String::new(),
        value: Some(value),
    }
}
fn is_option(value: &str) -> bool {
    let negative_number =
        Regex::new(r"^-\d+$|^-\d*\.\d+$").is_ok_and(|pattern| pattern.is_match(value));
    value.starts_with('-') && value != "-" && !value.contains(' ') && !negative_number
}
fn authored_path(raw: &str) -> String {
    // pathlib removes redundant separators and dot segments, but preserves `..`.
    let leading = if raw.starts_with("//") && !raw.starts_with("///") {
        "//"
    } else if raw.starts_with('/') {
        "/"
    } else {
        ""
    };
    let parts: Vec<_> = raw
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect();
    let path = format!("{leading}{}", parts.join("/"));
    if path.is_empty() { ".".into() } else { path }
}

pub fn normalise_slug(raw: &str) -> Result<String, Error> {
    let mut slug = String::new();
    let mut replacing = false;
    for ch in raw.trim_matches(is_python_space).to_lowercase().chars() {
        if ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '_' || ch == '-' {
            slug.push(ch);
            replacing = false;
        } else if !replacing {
            slug.push('-');
            replacing = true;
        }
    }
    let slug = slug.trim_matches(['-', '_']);
    if slug.is_empty() || slug.len() > 64 {
        return Err(Error::new(
            "ValueError",
            format!(
                "project slug {} cannot be normalized to a valid slug",
                repr(raw)
            ),
        ));
    }
    Ok(slug.into())
}
pub fn normalise_stack(values: &[String]) -> Vec<String> {
    let mut stack = Vec::new();
    for item in values
        .iter()
        .flat_map(|value| value.split(','))
        .map(|item| item.trim_matches(is_python_space))
    {
        if !item.is_empty() && !stack.iter().any(|value| value == item) {
            stack.push(item.to_owned());
        }
    }
    stack
}
fn placeholder(value: &str) -> bool {
    // Python's word class is letters/numbers/underscore, excluding combining marks.
    let value = value.replace(['\u{130}', '\u{131}'], "i");
    Regex::new(concat!(
        r"(?i)(?:^|[^\p{L}\p{N}_])",
        r"(?:describe|placeholder|replace[ -]?me|tbd|todo|unknown)",
        r"(?:$|[^\p{L}\p{N}_])",
    ))
    .is_ok_and(|pattern| pattern.is_match(&value))
}
pub fn validate_project_identity(purpose: Option<&str>, stack: &[String]) -> Vec<String> {
    let mut errors = Vec::new();
    if purpose.is_none_or(|value| value.trim_matches(is_python_space).is_empty()) {
        errors.push("--purpose is required during bootstrap phase 1".into());
    } else if purpose.is_some_and(|value| value.contains(['\n', '\r'])) {
        errors.push("--purpose must be a single line".into());
    } else if purpose.is_some_and(placeholder) {
        errors.push("--purpose must not contain placeholder text".into());
    }
    if stack.is_empty() {
        errors.push("at least one --stack value is required during bootstrap phase 1".into());
    }
    for item in stack {
        if placeholder(item) {
            errors.push(format!(
                "--stack must not contain placeholder text: {}",
                repr(item)
            ));
        }
    }
    errors
}

fn expanded(host: &mut impl Host, path: &Path) -> Result<PathBuf, Error> {
    let path = host.expanduser(path)?;
    host.resolve(&path)
}
pub fn storage_preflight(
    root: &Path,
    requested: Option<&Path>,
    host: &mut impl Host,
) -> Result<(Vec<String>, Value), Error> {
    let Some(requested) = requested else {
        return Ok((
            Vec::new(),
            json!({"mode": "host-default", "root": null,
            "same_filesystem_as_project": null, "large_payloads": {}}),
        ));
    };
    let storage = expanded(host, requested)?;
    let environment = host.resolve(&root.join(".venv"))?;
    let mut report = json!({"mode": "external-first", "root": storage,
        "project_environment": environment, "same_filesystem_as_project": false,
        "large_payloads": {}});
    let mut errors = Vec::new();
    if !host.is_dir(&storage) {
        errors.push(format!(
            "external storage root is not a directory: {}",
            storage.display()
        ));
        return Ok((errors, report));
    }
    if !host.writable(&storage) {
        errors.push(format!(
            "external storage root is not writable: {}",
            storage.display()
        ));
    }
    let mut configured = Vec::new();
    for (name, relative) in EXTERNAL_STORAGE_PATHS {
        let expected = host.resolve(&storage.join(relative))?;
        let Some(raw) = host.env(name).filter(|raw| !raw.is_empty()) else {
            errors.push(format!(
                "{name} is not configured; invoke bootstrap through setup.sh \
                with --storage-root"
            ));
            continue;
        };
        let actual = expanded(host, Path::new(&raw))?;
        report["large_payloads"][name] = json!(actual);
        if actual != expected {
            errors.push(format!(
                "{name} must resolve to {}, got {}",
                expected.display(),
                actual.display()
            ));
        } else if !host.is_dir(&actual) {
            errors.push(format!("{name} directory is missing: {}", actual.display()));
        } else {
            configured.push(actual);
        }
    }
    let runtime_id = host.env("MIR_BOOTSTRAP_RUNTIME_ID").unwrap_or_default();
    let runtime_root = host.resolve(&storage.join("mir/cli").join(&runtime_id))?;
    for (name, leaf) in [("UV_TOOL_DIR", "tools"), ("UV_TOOL_BIN_DIR", "bin")] {
        let Some(raw) = host.env(name).filter(|raw| !raw.is_empty()) else {
            errors.push(format!(
                "{name} is not configured; invoke bootstrap through setup.sh \
                with --storage-root"
            ));
            continue;
        };
        let actual = expanded(host, Path::new(&raw))?;
        report["large_payloads"][name] = json!(actual);
        if runtime_id.is_empty() || actual != runtime_root.join(leaf) {
            errors.push(format!(
                "{name} must use the setup-derived project runtime under \
                {}, got {}",
                storage.join("mir/cli").display(),
                actual.display()
            ));
        } else if !host.is_dir(&actual) {
            errors.push(format!("{name} directory is missing: {}", actual.display()));
        } else {
            configured.push(actual);
        }
    }
    let environment = host.resolve(&root.join(".venv"))?;
    match host
        .env("UV_PROJECT_ENVIRONMENT")
        .filter(|raw| !raw.is_empty())
    {
        None => {
            errors.push("UV_PROJECT_ENVIRONMENT is not configured for project-local .venv".into())
        }
        Some(raw) => {
            let actual = expanded(host, Path::new(&raw))?;
            if actual != environment {
                errors.push(format!(
                    "UV_PROJECT_ENVIRONMENT must resolve to {}, got {}",
                    environment.display(),
                    actual.display()
                ));
            }
        }
    }
    let same_filesystem = (|| {
        let project_device = host.device(root)?;
        if configured.len() != EXTERNAL_STORAGE_PATHS.len() + 2
            || host.device(&storage)? != project_device
        {
            return Ok(false);
        }
        for path in &configured {
            if host.device(path)? != project_device {
                return Ok(false);
            }
        }
        Ok::<_, Error>(true)
    })();
    match same_filesystem {
        Err(error) => {
            if !matches!(
                error.class,
                "OSError"
                    | "FileNotFoundError"
                    | "PermissionError"
                    | "NotADirectoryError"
                    | "IsADirectoryError"
            ) {
                return Err(error);
            }
            errors.push(format!("external storage filesystem check failed: {error}"));
        }
        Ok(same) => {
            report["same_filesystem_as_project"] = json!(same);
            if !same {
                errors.push(
                    "external storage root and project must use the same filesystem \
                    so uv can clone/link cached packages instead of copying them"
                        .into(),
                );
            }
        }
    }
    Ok((errors, report))
}
