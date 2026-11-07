//! Read-only content bootstrap identity and onboarding library.
use super::Error;
use crate::executor_brief_render::python_value_repr;
use crate::executor_execute::repr;
use crate::mir_cli::bootstrap_adoption::{self as adoption, is_python_space, phase2, wire};
use regex::Regex;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::LazyLock;

// Python re's Unicode word class is letters, numbers and underscore, not marks.
static CONTENT_WORDS: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(r"[\p{L}\p{N}_]+"));

fn value_error(message: impl Into<String>) -> Error {
    Error::new("ValueError", message)
}

fn adopt_error(error: adoption::Error) -> Error {
    Error::new(error.class(), error.to_string())
}

fn content_error(error: adoption::Error) -> Error {
    if let adoption::Error::Adoption(error) = error {
        value_error(error.to_string())
    } else {
        adopt_error(error)
    }
}

fn extension(path: &Path) -> String {
    path.extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_lowercase()
}

fn formats(files: &[PathBuf]) -> BTreeSet<String> {
    files.iter().map(|path| extension(path)).collect()
}

// Unlike canonicalize(), non-strict resolution keeps missing symlink targets.
fn resolve_content_path(
    path: &Path,
    active: &mut BTreeSet<PathBuf>,
    authored: &Path,
) -> Result<PathBuf, Error> {
    let mut resolved = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => continue,
            Component::ParentDir => {
                resolved.pop();
                continue;
            }
            component => resolved.push(component.as_os_str()),
        }
        if !resolved.is_symlink() {
            continue;
        }
        if !active.insert(resolved.clone()) {
            return Err(Error::new(
                "RuntimeError",
                format!("Symlink loop from {}", repr(&wire(authored))),
            ));
        }
        let target = fs::read_link(&resolved)
            .map_err(|error| adopt_error(adoption::io_error(&resolved, error)))?;
        let target = if target.is_absolute() {
            target
        } else {
            resolved.parent().unwrap_or(Path::new("")).join(target)
        };
        let key = resolved;
        resolved = resolve_content_path(&target, active, authored)?;
        active.remove(&key);
    }
    Ok(crate::supply::plain(resolved))
}

pub fn project_relative(root: &Path, raw: &str) -> Result<(PathBuf, String), Error> {
    let authored = Path::new(raw);
    if authored.is_absolute() {
        return Err(value_error(format!(
            "content archive path must be project-relative: {raw}"
        )));
    }
    let path = root.join(authored);
    let resolved = resolve_content_path(&path, &mut BTreeSet::new(), &path)?;
    let relative = resolved
        .strip_prefix(root)
        .map_err(|_| value_error(format!("content archive path escapes the project: {raw}")))?;
    let relative = wire(relative);
    if relative.is_empty() || relative == "." {
        return Err(value_error(
            "content archive path must name a file or directory, not project root",
        ));
    }
    Ok((resolved, relative))
}

pub fn discoverable_content_files(root: &Path, path: &Path) -> Result<Vec<PathBuf>, Error> {
    if path.is_symlink() {
        return Err(value_error(format!(
            "content archive path must not be a symlink: {}",
            wire(path.strip_prefix(root).unwrap_or(path))
        )));
    }
    let mut files = Vec::new();
    phase2::discover_content_typed(root, path, &mut files).map_err(content_error)?;
    files.sort();
    Ok(files)
}

pub fn supported_content_files(root: &Path, path: &Path) -> Result<Vec<PathBuf>, Error> {
    Ok(discoverable_content_files(root, path)?
        .into_iter()
        .filter(|candidate| phase2::TEXT_EXTENSIONS.contains(&extension(candidate).as_str()))
        .collect())
}

pub fn acceptance_query(body: &str, label: &str) -> Result<String, Error> {
    let words = CONTENT_WORDS
        .as_ref()
        .map_err(|error| Error::new("RuntimeError", error.to_string()))?;
    for token in words.find_iter(body).map(|token| token.as_str()) {
        let folded = token.replace(['\u{131}', '\u{130}'], "i").to_lowercase();
        let folded = folded.replace('\u{17f}', "s");
        if token.chars().count() >= 6
            && ![
                "describe",
                "placeholder",
                "replaceme",
                "tbd",
                "todo",
                "unknown",
            ]
            .contains(&folded.as_str())
        {
            return Ok(token.into());
        }
    }
    Err(value_error(format!(
        "content archive {} has no searchable token of at least six characters",
        repr(label)
    )))
}

pub fn project_definition_text(purpose: &str, stack: &[String]) -> String {
    format!(
        "# Project definition\n\nPurpose: {purpose}\n\nWorking stack: {}\n",
        stack.join(", ")
    )
}

pub fn scan_content_candidates(root: &Path) -> Result<Vec<Value>, Error> {
    phase2::scan_content_candidates_typed(root).map_err(content_error)
}

fn valid_classification(value: &str) -> bool {
    let bytes = value.as_bytes();
    !bytes.is_empty()
        && bytes.len() <= 64
        && (bytes[0].is_ascii_lowercase() || bytes[0].is_ascii_digit())
        && bytes
            .iter()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'_' | b'-'))
}

pub fn parse_content_archives(root: &Path, raw_archives: &[String]) -> Result<Vec<Value>, Error> {
    let mut archives = Vec::new();
    let mut seen = BTreeSet::new();
    let mut resolved_paths: Vec<(String, PathBuf)> = Vec::new();
    for raw in raw_archives {
        let (classification, authored) = raw.split_once('=').unwrap_or((raw, ""));
        let classification = classification.trim_matches(is_python_space).to_lowercase();
        if !raw.contains('=') || !valid_classification(&classification) {
            return Err(value_error(format!(
                "invalid --archive {}; expected lowercase CLASSIFICATION=PATH",
                repr(raw)
            )));
        }
        if seen.contains(&classification) {
            return Err(value_error(format!(
                "duplicate content classification: {classification}"
            )));
        }
        let (path, relative) = project_relative(root, authored.trim_matches(is_python_space))?;
        if !path.exists() {
            return Err(value_error(format!(
                "content archive path does not exist: {relative}"
            )));
        }
        for (prior_label, prior_path) in &resolved_paths {
            if path.starts_with(prior_path) || prior_path.starts_with(&path) {
                return Err(value_error(format!(
                    "content archive paths overlap: {} and {}",
                    repr(prior_label),
                    repr(&classification)
                )));
            }
        }
        let discovered_files = discoverable_content_files(root, &path)?;
        let files: Vec<_> = discovered_files
            .iter()
            .filter(|candidate| phase2::TEXT_EXTENSIONS.contains(&extension(candidate).as_str()))
            .cloned()
            .collect();
        if discovered_files.is_empty() {
            return Err(value_error(format!(
                "content archive has no recognized record files: {relative}"
            )));
        }
        let all_formats = formats(&discovered_files);
        let Some(acceptance_path) = files.first() else {
            let rendered = all_formats
                .iter()
                .map(|s| repr(s))
                .collect::<Vec<_>>()
                .join(", ");
            return Err(value_error(format!(
                "content archive {} contains only non-indexable formats [{rendered}]; \
                 add a tracked UTF-8 text projection before bootstrap",
                repr(&relative)
            )));
        };
        let bytes = fs::read(acceptance_path)
            .map_err(|error| adopt_error(adoption::io_error(acceptance_path, error)))?;
        let body = adoption::decode(bytes).map_err(|_| {
            value_error(format!(
                "content archive file is not UTF-8: {}",
                wire(
                    acceptance_path
                        .strip_prefix(root)
                        .unwrap_or(acceptance_path)
                )
            ))
        })?;
        archives.push(json!({
            "classification": classification,
            "path": relative,
            "kind": if path.is_dir() { "directory" } else { "file" },
            "formats": all_formats,
            "indexed_formats": formats(&files),
            "document_count": discovered_files.len(),
            "indexed_document_count": files.len(),
            "acceptance": {
                "query": acceptance_query(&body, &relative)?,
                "expected_path": wire(acceptance_path.strip_prefix(root).unwrap_or(acceptance_path))
            }
        }));
        seen.insert(classification.clone());
        resolved_paths.push((classification, path));
    }
    Ok(archives)
}

pub fn build_content_onboarding(
    root: &Path,
    purpose: &str,
    stack: &[String],
    raw_archives: &[String],
) -> Result<(Value, String), Error> {
    let definition = project_definition_text(purpose, stack);
    let mut archives = vec![json!({
        "classification": "project-definition",
        "path": "docs/project-purpose.md",
        "kind": "file",
        "formats": ["md"],
        "indexed_formats": ["md"],
        "document_count": 1,
        "indexed_document_count": 1,
        "acceptance": {
            "query": acceptance_query(&definition, "project-definition")?,
            "expected_path": "docs/project-purpose.md"
        }
    })];
    archives.extend(parse_content_archives(root, raw_archives)?);
    let candidates = scan_content_candidates(root)?;
    let unclassified: Vec<_> = candidates
        .iter()
        .filter(|candidate| {
            let candidate = Path::new(candidate["path"].as_str().unwrap_or(""));
            !archives.iter().skip(1).any(|archive| {
                candidate.starts_with(Path::new(archive["path"].as_str().unwrap_or("")))
            })
        })
        .cloned()
        .collect();
    Ok((
        json!({
            "schema_version": 1,
            "profile": "content_workspace",
            "purpose": purpose,
            "technology_stack": stack,
            "archives": archives,
            "scan": { "candidates": candidates, "unclassified": unclassified }
        }),
        definition,
    ))
}

fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64() != Some(0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

pub fn load_content_onboarding(path: &Path) -> Result<Value, Error> {
    let bytes = fs::read(path).map_err(|error| {
        value_error(format!(
            "invalid config/content-onboarding.json: {}",
            adoption::io_error(path, error)
        ))
    })?;
    let text = adoption::decode(bytes).map_err(adopt_error)?;
    let raw = adoption::json_text(&text)
        .map_err(|error| value_error(format!("invalid config/content-onboarding.json: {error}")))?;
    if !raw.is_object()
        || !(raw["schema_version"].as_f64() == Some(1.0)
            || raw["schema_version"] == Value::Bool(true))
    {
        return Err(value_error(
            "config/content-onboarding.json schema_version must be 1",
        ));
    }
    if raw["profile"] != "content_workspace" {
        return Err(value_error(
            "content onboarding manifest profile must be content_workspace",
        ));
    }
    if !raw["archives"]
        .as_array()
        .is_some_and(|items| !items.is_empty())
    {
        return Err(value_error(
            "content onboarding manifest must contain classified archives",
        ));
    }
    if !raw["scan"].is_object() || truthy(&raw["scan"]["unclassified"]) {
        return Err(value_error(
            "content onboarding manifest contains unclassified archive candidates",
        ));
    }
    Ok(raw)
}

fn python_str(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| python_value_repr(value))
}

pub fn content_archive_globs(onboarding: &Value) -> Vec<String> {
    let mut globs: BTreeSet<String> = ["docs/**/*.md", "tasks/**/*.md", ".ai-harness/**/*.md"]
        .into_iter()
        .map(String::from)
        .collect();
    for item in onboarding["archives"].as_array().into_iter().flatten() {
        if !item.is_object() {
            continue;
        }
        let relative = item.get("path").map(python_str).unwrap_or_default();
        if item["kind"] == "file" {
            globs.insert(relative);
        } else {
            for suffix in phase2::TEXT_EXTENSIONS {
                globs.insert(format!("{relative}/**/*.{suffix}"));
            }
        }
    }
    globs.into_iter().collect()
}

pub fn content_archive_args(onboarding: &Value) -> Result<Vec<String>, Error> {
    let mut args = Vec::new();
    for item in onboarding["archives"].as_array().into_iter().flatten() {
        if !item.is_object() || item["classification"] == "project-definition" {
            continue;
        }
        let field = |name: &str| {
            item.get(name)
                .map(python_str)
                .ok_or_else(|| Error::new("KeyError", repr(name)))
        };
        args.push(format!("{}={}", field("classification")?, field("path")?));
    }
    Ok(args)
}
