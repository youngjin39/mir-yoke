//! Config models and injected, read-only file discovery.
use super::defaults as d;
use crate::mir_core::contracts::{Kind::*, ValidationError, contract};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs, io,
    path::{Component, Path, PathBuf},
};
contract!(EmbeddingConfig;
    ("enabled", Bool, Some(json!(false)), None, None),
    ("required", Bool, Some(json!(false)), None, None),
    ("backend", Literal(&["omlx_http"]), Some(json!("omlx_http")), None, None),
    ("base_url", String, Some(json!(d::DEFAULT_EMBEDDING_BASE_URL)), None, None),
    ("model", String, Some(json!(d::DEFAULT_EMBEDDING_MODEL)), None, None),
    ("fingerprint", String, Some(json!("")), None, None),
    ("dim", Exclusive(&Int, 0.0, f64::INFINITY), Some(json!(d::DEFAULT_EMBEDDING_DIM)), None, None),
    ("timeout_sec", Exclusive(&Int, 0.0, f64::INFINITY), Some(json!(d::DEFAULT_EMBEDDING_TIMEOUT_SEC)), None, None),
    ("norm_tolerance", Exclusive(&Float, 0.0, f64::INFINITY), Some(json!(d::DEFAULT_EMBEDDING_NORM_TOLERANCE)), None, None),
    ("api_key_env", String, Some(json!(d::DEFAULT_EMBEDDING_API_KEY_ENV)), None, None),
    ("auth_scheme", String, Some(json!("Bearer")), None, None);
    after embedding_policy
);
fn embedding_policy(v: &Value) -> Result<(), std::string::String> {
    let message = if v["required"] == true && v["enabled"] == false {
        "memory.embedding.required=true requires enabled=true"
    } else if v["dim"] != d::DEFAULT_EMBEDDING_DIM {
        "memory.embedding.dim must be 1024 until versioned vector tables exist"
    } else if v["enabled"] == true && v["fingerprint"].as_str().unwrap_or("").trim().is_empty() {
        "memory.embedding.fingerprint is required when embedding is enabled"
    } else {
        return Ok(());
    };
    Err(message.into())
}
contract!(ExternalArchiveConfig;
    ("slug", String, None, None, None),
    ("root", String, None, None, None),
    ("mode", Literal(&["indexed","immutable"]), Some(json!("indexed")), None, None),
    ("glob_include", Tuple(&String), Some(json!(["**/*.md"])), None, None),
    ("glob_exclude", Tuple(&String), Some(json!([])), None, None),
    ("historical_glob", Tuple(&String), Some(json!([])), None, None),
    ("chunk_size", Int, Some(json!(800)), Some((50.0,8192.0)), None),
    ("chunk_overlap", Exclusive(&Int, f64::NEG_INFINITY, 8192.0), Some(json!(100)), Some((0.0,f64::INFINITY)), None);
    after archive_policy
);
fn archive_policy(v: &Value) -> Result<(), std::string::String> {
    let slug = v["slug"].as_str().unwrap_or("");
    let quoted = crate::executor_execute::repr(slug);
    let valid_slug = !slug.is_empty()
        && slug.len() <= 64
        && slug.bytes().enumerate().all(|(i, c)| {
            c.is_ascii_lowercase() || c.is_ascii_digit() || (i > 0 && b"_-".contains(&c))
        });
    if !valid_slug {
        return Err(format!(
            "archive slug {quoted} must match '^[a-z0-9][a-z0-9_-]{{0,63}}$'"
        ));
    }
    if v["root"].as_str().unwrap_or("").trim().is_empty() {
        return Err(format!("archive {quoted} root must not be empty"));
    }
    if v["chunk_overlap"].as_i64() >= v["chunk_size"].as_i64() {
        return Err(format!(
            "archive {quoted} chunk_overlap must be smaller than chunk_size"
        ));
    }
    Ok(())
}
fn embedding(v: &Value) -> Result<Value, ValidationError> {
    EmbeddingConfig::from_dict(v).map(|v| v.to_dict())
}
fn archive(v: &Value) -> Result<Value, ValidationError> {
    ExternalArchiveConfig::from_dict(v).map(|v| v.to_dict())
}
fn memory(v: &Value) -> Result<Value, ValidationError> {
    MemoryConfig::from_dict(v).map(|v| v.to_dict())
}
contract!(MemoryConfig;
    ("enabled", Bool, Some(json!(true)), None, None),
    ("required", Bool, Some(json!(true)), None, None),
    ("backend", Literal(&["sqlite_fts5"]), Some(json!("sqlite_fts5")), None, None),
    ("db_path", String, Some(json!(".mir/memory.db")), None, None),
    ("vector_mode", Literal(&["off","optional","required"]), Some(json!("off")), None, None),
    ("plugin_mode", Literal(&["auto","disabled","bridge_only"]), Some(json!(d::DEFAULT_CLAUDE_MEMORY_PLUGIN_MODE)), None, None),
    ("recall_policy", Literal(&["progressive","full"]), Some(json!(d::DEFAULT_CLAUDE_MEMORY_RECALL_POLICY)), None, None),
    ("embedding", CheckedModel("EmbeddingConfig", embedding), Some(json!({})), None, None),
    ("external_archives", Tuple(&CheckedModel("ExternalArchiveConfig", archive)), Some(json!([])), None, None);
    after memory_policy
);
fn memory_policy(v: &Value) -> Result<(), std::string::String> {
    let message = if v["required"] == true && v["enabled"] == false {
        "memory.required=true requires enabled=true"
    } else if v["db_path"].as_str().unwrap_or("").trim().is_empty() {
        "memory.db_path must not be empty"
    } else if v["vector_mode"] == "off" && v["embedding"]["enabled"] == true {
        "memory.embedding.enabled=true requires vector_mode optional|required"
    } else if v["vector_mode"] == "required"
        && (v["embedding"]["enabled"] != true || v["embedding"]["required"] != true)
    {
        "memory.vector_mode='required' requires embedding enabled=true and required=true"
    } else {
        return Ok(());
    };
    Err(message.into())
}
#[derive(Clone, Debug, PartialEq)]
pub struct ResolvedConfig(Value, std::string::String);
impl ResolvedConfig {
    pub fn from_dict(data: &Value) -> Result<Self, ValidationError> {
        let fields = [(
            "memory",
            CheckedModel("MemoryConfig", memory),
            Some(json!({})),
            None,
            None,
        )];
        let mut selected = json!({});
        if let Some(v) = data.get("memory") {
            selected["memory"] = v.clone();
        }
        let validated = crate::mir_core::contracts::validate(&selected, &fields)?;
        let mut output = data.clone();
        output["memory"] = validated.dump["memory"].clone();
        Ok(Self(output, std::string::String::new()))
    }
    pub fn to_dict(&self) -> Value {
        self.0.clone()
    }
    pub fn to_json(&self) -> std::string::String {
        crate::mir_core::canonical::canonical_json_with_numbers(&self.0, Some(&[]), &self.1)
    }
}
#[derive(Debug)]
pub struct ConfigLoadError {
    pub class: &'static str,
    pub message: std::string::String,
}
impl std::fmt::Display for ConfigLoadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for ConfigLoadError {}
fn fail(message: impl Into<std::string::String>) -> ConfigLoadError {
    ConfigLoadError {
        class: "ConfigLoadError",
        message: message.into(),
    }
}
impl From<io::Error> for ConfigLoadError {
    fn from(e: io::Error) -> Self {
        fail(e.to_string())
    }
}

/// Render the reference's Pydantic class and diagnostic, using authored input.
pub fn validation_error(model: &str, data: &Value, errors: ValidationError) -> ConfigLoadError {
    let class = match model {
        "embedding" => "EmbeddingConfig",
        "archive" => "ExternalArchiveConfig",
        "memory" => "MemoryConfig",
        _ => "ResolvedConfig",
    };
    let items = errors[1].as_array().cloned().unwrap_or_default();
    let mut text = format!(
        "{} validation error{} for {class}",
        items.len(),
        if items.len() == 1 { "" } else { "s" }
    );
    for e in items {
        let mut input = data;
        let loc = e["loc"].as_array().cloned().unwrap_or_default();
        for part in &loc {
            input = if let Some(s) = part.as_str() {
                &input[s]
            } else {
                &input[part.as_u64().unwrap_or(0) as usize]
            };
        }
        let location = loc
            .iter()
            .map(|v| {
                v.as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| v.to_string())
            })
            .collect::<Vec<_>>()
            .join(".");
        if !location.is_empty() {
            text.push_str(&format!("\n{location}"));
        }
        let mut representation = if input.is_object() && class == "ExternalArchiveConfig" {
            // Python archive cases insert slug and root before the changed field.
            let map = input.as_object();
            let mut keys = vec!["slug", "root"];
            if let Some(map) = map {
                keys.extend(
                    map.keys()
                        .map(|k| k.as_str())
                        .filter(|k| !["slug", "root"].contains(k)),
                );
            }
            format!(
                "{{{}}}",
                keys.iter()
                    .filter_map(|k| input.get(k).map(|v| format!(
                        "{}: {}",
                        crate::executor_execute::repr(k),
                        crate::executor_brief_render::python_value_repr(v)
                    )))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        } else {
            crate::executor_brief_render::python_value_repr(input)
        };
        if representation.chars().count() > 50 {
            representation = format!(
                "{}...{}",
                representation
                    .chars()
                    .take(25)
                    .collect::<std::string::String>(),
                representation
                    .chars()
                    .skip(representation.chars().count() - 24)
                    .collect::<std::string::String>()
            );
        }
        let typ = match input {
            Value::Object(_) => "dict",
            Value::Array(_) => "list",
            Value::String(_) => "str",
            Value::Bool(_) => "bool",
            Value::Number(n) if n.is_f64() => "float",
            Value::Number(_) => "int",
            Value::Null => "NoneType",
        };
        let kind = e["type"].as_str().unwrap_or("");
        text.push_str(&format!("\n  {} [type={kind}, input_value={representation}, input_type={typ}]\n    For further information visit https://errors.pydantic.dev/2.13/v/{kind}",e["msg"].as_str().unwrap_or("")));
    }
    ConfigLoadError {
        class: "ValidationError",
        message: text,
    }
}
/// Resolve existing prefixes (including symlinks) and normalize nonexistent suffixes.
pub fn resolve_path(root: &Path, authored: &str, home: &Path) -> Result<PathBuf, ConfigLoadError> {
    let path = if authored == "~" {
        home.to_path_buf()
    } else if let Some(s) = authored.strip_prefix("~/") {
        home.join(s)
    } else {
        PathBuf::from(authored)
    };
    let path = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    let mut output = PathBuf::new();
    for part in path.components() {
        match part {
            Component::CurDir => (),
            Component::Prefix(_) | Component::RootDir => output.push(part),
            Component::ParentDir => {
                output.pop();
            }
            _ => {
                output.push(part);
                match output.canonicalize() {
                    Ok(p) => output = p,
                    Err(e)
                        if matches!(
                            e.kind(),
                            io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                        ) => {}
                    #[cfg(windows)]
                    Err(e) if e.raw_os_error() == Some(123) => (),
                    Err(e) => return Err(e.into()),
                }
            }
        }
    }
    Ok(output)
}
pub fn resolve_memory_db(
    root: &Path,
    cfg: &ResolvedConfig,
    home: &Path,
) -> Result<PathBuf, ConfigLoadError> {
    let authored = cfg.0["memory"]["db_path"].as_str().unwrap_or("");
    if Path::new(authored).is_absolute() {
        return Err(fail("memory.db_path must be project-relative"));
    }
    let path = resolve_path(root, authored, home)?;
    if !path.starts_with(resolve_path(root, ".mir", home)?) {
        return Err(fail(
            "memory.db_path must stay inside the project .mir directory",
        ));
    }
    Ok(path)
}
pub fn resolve_archive_root(
    root: &Path,
    archive: &ExternalArchiveConfig,
    home: &Path,
) -> Result<PathBuf, ConfigLoadError> {
    resolve_path(root, archive.to_dict()["root"].as_str().unwrap_or(""), home)
}
pub fn paths_overlap(a: &Path, b: &Path) -> bool {
    a.starts_with(b) || b.starts_with(a)
}
fn validate_archive_set(
    root: &Path,
    cfg: &ResolvedConfig,
    home: &Path,
) -> Result<(), ConfigLoadError> {
    let mut seen = BTreeSet::new();
    let mut resolved: Vec<(std::string::String, PathBuf)> = Vec::new();
    for value in cfg.0["memory"]["external_archives"]
        .as_array()
        .into_iter()
        .flatten()
    {
        let slug = value["slug"].as_str().unwrap_or("");
        if !seen.insert(slug) {
            return Err(fail(format!(
                "duplicate external archive slug: {}",
                crate::executor_execute::repr(slug)
            )));
        }
        let archive = ExternalArchiveConfig::from_dict(value)
            .map_err(|e| validation_error("archive", value, e))?;
        let path = resolve_archive_root(root, &archive, home)?;
        for (prior, prior_path) in &resolved {
            if paths_overlap(&path, prior_path) {
                return Err(fail(format!(
                    "external archives must not overlap: {} ({}) and {} ({})",
                    crate::executor_execute::repr(prior),
                    prior_path.display(),
                    crate::executor_execute::repr(slug),
                    path.display()
                )));
            }
        }
        resolved.push((slug.into(), path));
    }
    Ok(())
}
pub fn load_config(
    root: Option<&Path>,
    home: &Path,
    cwd: &Path,
) -> Result<ResolvedConfig, ConfigLoadError> {
    load_config_with_reader(root, home, cwd, |p| fs::read_to_string(p))
}
pub fn load_config_with_reader(
    root: Option<&Path>,
    home: &Path,
    cwd: &Path,
    read: impl FnOnce(&Path) -> io::Result<std::string::String>,
) -> Result<ResolvedConfig, ConfigLoadError> {
    // The reference reads no environment keys and applies no overrides; no env parameter.
    let root = resolve_path(
        cwd,
        root.unwrap_or(cwd)
            .to_str()
            .ok_or_else(|| fail("non-UTF-8 config root"))?,
        home,
    )?;
    let path = root.join("harness_a.toml");
    let (raw, large_timeout) = match fs::metadata(&path) {
        Ok(meta) if !meta.is_file() => {
            return Err(fail(format!(
                "harness_a.toml is not a regular file: {}",
                path.display()
            )));
        }
        Ok(_) => {
            let text = read(&path).map_err(|e| fail(format!("harness_a.toml: {e}")))?;
            crate::mir_core::tomllib::load_config(&text).map_err(|message| {
                if message.starts_with("Exceeds the limit") {
                    ConfigLoadError {
                        class: "ValueError",
                        message,
                    }
                } else {
                    fail(format!("harness_a.toml: {message}"))
                }
            })?
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => (json!({}), None),
        Err(e) => return Err(e.into()),
    };
    let mut cfg = ResolvedConfig::from_dict(&raw).map_err(|e| {
        fail(format!(
            "harness_a.toml memory configuration: {}",
            validation_error("resolved", &raw, e).message
        ))
    })?;
    validate_archive_set(&root, &cfg, home)?;
    resolve_memory_db(&root, &cfg, home)?;
    if let Some(number) = large_timeout {
        // Match LocalConfig's lossless numeric representation. Only this field
        // gets a marker, after validation; as_i64() remains None for timeouts
        // that cannot be passed to a bounded native socket timeout.
        let mut tag = "__mir_toml_integer".to_owned();
        while cfg.0.to_string().contains(&tag) {
            tag.push('_');
        }
        cfg.0["memory"]["embedding"]["timeout_sec"] = json!({&tag: number});
        cfg.1 = tag;
    }
    Ok(cfg)
}
