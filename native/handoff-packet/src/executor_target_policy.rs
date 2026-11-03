//! Versioned finite target admission policy; no consumer package imports.
//! Unknown fields are rejected inside this owned schema. Other local config keys
//! remain governed by `executor_local`'s existing lazy validation contract.
use crate::executor_local::Error;
use serde_json::{Map, Value, json};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs, io,
    path::{Path, PathBuf},
    process::Command,
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PolicyFailure {
    pub kind: String,
    pub message: String,
    /// Exact diagnostic emitted before the exception; includes its own newline.
    pub stderr: Option<String>,
}
impl std::fmt::Display for PolicyFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for PolicyFailure {}
#[derive(Clone, Debug)]
struct FailureTemplate {
    kind: String,
    message: String,
    stderr: Option<String>,
}
#[derive(Clone, Debug)]
enum FamilyPolicy {
    Reject(FailureTemplate),
    Resolve {
        current: bool,
        aliases: BTreeMap<String, PathBuf>,
        normalization: Normalization,
        unknown: FailureTemplate,
        unknown_key_error: Option<String>,
        unavailable: Option<FailureTemplate>,
        root_conflict: Option<FailureTemplate>,
    },
}
#[derive(Clone, Copy, Debug)]
enum Normalization {
    Exact,
    LowerUnderscores,
    StripLower,
}
#[derive(Clone, Debug)]
pub struct NativePolicy {
    family: Option<FamilyPolicy>,
    repository_local: Option<FailureTemplate>,
    authorize_target: bool,
}
const VARIABLES: &[&str] = &[
    "family",
    "family_repr",
    "normalized_repr",
    "known",
    "key_error",
    "family_root",
    "requested_root",
    "config_root",
    "cwd",
];
fn invalid(message: impl Into<String>) -> Error {
    Error::Invalid(format!("native_policy: {}", message.into()))
}
fn object<'a>(
    value: &'a Value,
    fields: &[&str],
    location: &str,
) -> Result<&'a Map<String, Value>, Error> {
    let data = value
        .as_object()
        .ok_or_else(|| invalid(format!("{location} must be an object")))?;
    if let Some(key) = data.keys().find(|key| !fields.contains(&key.as_str())) {
        return Err(invalid(format!("unknown field {location}.{key}")));
    }
    Ok(data)
}
fn string<'a>(data: &'a Map<String, Value>, key: &str) -> Result<&'a str, Error> {
    data.get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| invalid(format!("{key} must be a string")))
}
fn template(value: &str) -> Result<String, Error> {
    let mut tail = value;
    while let Some(start) = tail.find(['{', '}']) {
        if tail.as_bytes()[start] == b'}' {
            return Err(invalid("unmatched template brace"));
        }
        tail = &tail[start + 1..];
        let end = tail
            .find('}')
            .ok_or_else(|| invalid("unmatched template brace"))?;
        if !VARIABLES.contains(&&tail[..end]) {
            return Err(invalid(format!(
                "unknown template variable {{{}}}",
                &tail[..end]
            )));
        }
        tail = &tail[end + 1..];
    }
    Ok(value.to_owned())
}
impl FailureTemplate {
    fn parse(value: &Value) -> Result<Self, Error> {
        let data = object(value, &["kind", "message", "stderr"], "failure")?;
        let kind = string(data, "kind")?;
        if ![
            "ValueError",
            "SystemExit",
            "ImportError",
            "ModuleNotFoundError",
        ]
        .contains(&kind)
        {
            return Err(invalid("unsupported failure kind"));
        }
        let message = template(string(data, "message")?)?;
        let stderr = data
            .get("stderr")
            .map(|_| string(data, "stderr").and_then(template))
            .transpose()?;
        if kind == "SystemExit" && message != "1" {
            return Err(invalid("SystemExit message must be 1"));
        }
        if kind != "SystemExit" && stderr.is_some() {
            return Err(invalid("stderr is only supported for SystemExit"));
        }
        Ok(Self {
            kind: kind.to_owned(),
            message,
            stderr,
        })
    }
    fn render(&self, vars: &BTreeMap<&str, String>) -> PolicyFailure {
        PolicyFailure {
            kind: self.kind.clone(),
            message: render(&self.message, vars),
            stderr: self.stderr.as_ref().map(|s| render(s, vars)),
        }
    }
}
fn render(text: &str, vars: &BTreeMap<&str, String>) -> String {
    let mut output = String::new();
    let mut tail = text;
    while let Some(start) = tail.find('{') {
        output.push_str(&tail[..start]);
        tail = &tail[start + 1..];
        let Some(end) = tail.find('}') else {
            break;
        };
        if let Some(value) = vars.get(&tail[..end]) {
            output.push_str(value);
        }
        tail = &tail[end + 1..];
    }
    output.push_str(tail);
    output
}
impl NativePolicy {
    pub fn parse(value: &Value) -> Result<Self, Error> {
        let data = object(value, &["version", "target_admission"], "native_policy")?;
        if data.get("version").and_then(Value::as_u64) != Some(1) {
            return Err(invalid("version must be integer 1"));
        }
        let admission = object(
            data.get("target_admission")
                .ok_or_else(|| invalid("target_admission is required"))?,
            &["family", "repository_local", "authorize_target"],
            "target_admission",
        )?;
        let family = admission
            .get("family")
            .map(|value| {
                let data = object(
                    value,
                    &[
                        "mode",
                        "failure",
                        "aliases",
                        "normalization",
                        "unknown",
                        "unknown_key_error",
                        "unavailable",
                        "root_conflict",
                    ],
                    "family",
                )?;
                let mode = string(data, "mode")?;
                if mode == "reject" {
                    if data
                        .keys()
                        .any(|k| !["mode", "failure"].contains(&k.as_str()))
                    {
                        return Err(invalid("reject family accepts only mode and failure"));
                    }
                    return Ok(FamilyPolicy::Reject(FailureTemplate::parse(
                        data.get("failure")
                            .ok_or_else(|| invalid("reject family requires failure"))?,
                    )?));
                }
                if mode != "alias_map" && mode != "require_current" {
                    return Err(invalid("invalid family mode"));
                }
                if data.contains_key("failure") {
                    return Err(invalid("failure is only supported for reject"));
                }
                let normalization = match data
                    .get("normalization")
                    .and_then(Value::as_str)
                    .unwrap_or("exact")
                {
                    "exact" => Normalization::Exact,
                    "lower_underscores" => Normalization::LowerUnderscores,
                    "strip_lower" => Normalization::StripLower,
                    _ => return Err(invalid("invalid family normalization")),
                };
                if data.contains_key("normalization") && !data["normalization"].is_string() {
                    return Err(invalid("normalization must be a string"));
                }
                let values = data
                    .get("aliases")
                    .and_then(Value::as_object)
                    .ok_or_else(|| invalid("aliases must be an object"))?;
                let mut aliases = BTreeMap::new();
                for (key, value) in values {
                    let path = value
                        .as_str()
                        .filter(|s| !s.is_empty() && !s.contains('\0'))
                        .ok_or_else(|| {
                            invalid("alias path must be a nonempty string without NUL")
                        })?;
                    aliases.insert(key.clone(), PathBuf::from(path));
                }
                let unknown = FailureTemplate::parse(
                    data.get("unknown")
                        .ok_or_else(|| invalid("family requires unknown failure"))?,
                )?;
                let unknown_key_error = data
                    .get("unknown_key_error")
                    .map(|_| string(data, "unknown_key_error").and_then(template))
                    .transpose()?;
                if unknown_key_error
                    .as_ref()
                    .is_some_and(|s| s.contains("{key_error}"))
                {
                    return Err(invalid("unknown_key_error cannot reference key_error"));
                }
                let unavailable = data
                    .get("unavailable")
                    .map(FailureTemplate::parse)
                    .transpose()?;
                if unavailable.is_some() && !aliases.is_empty() {
                    return Err(invalid("unavailable resolver cannot have aliases"));
                }
                let root_conflict = data
                    .get("root_conflict")
                    .map(FailureTemplate::parse)
                    .transpose()?;
                if mode == "require_current" && root_conflict.is_none() {
                    return Err(invalid("require_current requires root_conflict"));
                }
                Ok(FamilyPolicy::Resolve {
                    current: mode == "require_current",
                    aliases,
                    normalization,
                    unknown,
                    unknown_key_error,
                    unavailable,
                    root_conflict,
                })
            })
            .transpose()?;
        let repository_local = admission
            .get("repository_local")
            .map(FailureTemplate::parse)
            .transpose()?;
        let authorize_target = match admission.get("authorize_target") {
            None => false,
            Some(Value::Bool(value)) => *value,
            Some(_) => return Err(invalid("authorize_target must be boolean")),
        };
        if authorize_target
            && repository_local.is_none()
            && matches!(&family, Some(FamilyPolicy::Resolve { .. }))
        {
            return Err(invalid(
                "authorize_target requires reject family or repository_local checks",
            ));
        }
        if authorize_target && family.is_none() && repository_local.is_none() {
            return Err(invalid("authorize_target requires admission checks"));
        }
        Ok(Self {
            family,
            repository_local,
            authorize_target,
        })
    }
    pub fn has_authorize_target(&self) -> bool {
        self.authorize_target
    }
    pub fn covered_hooks(&self) -> Vec<&'static str> {
        let mut hooks = vec!["pre_execute"];
        if self.authorize_target {
            hooks.push("authorize_target");
        }
        hooks
    }
    /// Resolve successful redirects before locking. Refusals remain at the late
    /// pre_execute boundary. The caller must retain the initial requested root
    /// for pre_execute's conflict check.
    pub fn resolve_alias(
        &self,
        config_root: &Path,
        cwd: &Path,
        root: &Path,
        args: &mut Value,
    ) -> Result<PathBuf, PolicyFailure> {
        match self.family_target(config_root, cwd, root, args) {
            Ok(Some(target)) => {
                set_root(args, &target)?;
                Ok(target)
            }
            Ok(None) | Err(_) => Ok(root.to_owned()),
        }
    }
    pub fn pre_execute(
        &self,
        config_root: &Path,
        cwd: &Path,
        root: &Path,
        args: &mut Value,
        environment: &BTreeMap<OsString, OsString>,
    ) -> Result<(), PolicyFailure> {
        let target = self
            .family_target(config_root, cwd, root, args)?
            .unwrap_or_else(|| root.to_owned());
        self.check_repository(cwd, &target, args, environment)?;
        if target != root {
            set_root(args, &target)?;
        }
        Ok(())
    }
    pub fn authorize(
        &self,
        cwd: &Path,
        root: &Path,
        args: &Value,
        environment: &BTreeMap<OsString, OsString>,
    ) -> Result<(), PolicyFailure> {
        if !self.authorize_target {
            return Ok(());
        }
        // Authorization never redirects. Resolver policies belong to late
        // pre_execute; their authorization requires repository_local above.
        if let Some(FamilyPolicy::Reject(failure)) = &self.family
            && family(args).is_some()
        {
            return Err(failure.render(&variables(root, cwd, root, args)?));
        }
        self.check_repository(cwd, root, args, environment)
    }
    fn family_target(
        &self,
        config_root: &Path,
        cwd: &Path,
        root: &Path,
        args: &Value,
    ) -> Result<Option<PathBuf>, PolicyFailure> {
        let Some(family) = family(args) else {
            return Ok(None);
        };
        let Some(policy) = &self.family else {
            return Ok(None);
        };
        let mut vars = variables(config_root, cwd, root, args)?;
        match policy {
            FamilyPolicy::Reject(failure) => Err(failure.render(&vars)),
            FamilyPolicy::Resolve {
                current,
                aliases,
                normalization,
                unknown,
                unknown_key_error,
                unavailable,
                root_conflict,
            } => {
                let normalized = match normalization {
                    Normalization::Exact => family.to_owned(),
                    Normalization::LowerUnderscores => family.to_lowercase().replace('_', "-"),
                    Normalization::StripLower => family
                        .trim_matches(|c: char| {
                            c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
                        })
                        .to_lowercase(),
                };
                vars.insert("normalized_repr", python_repr(&normalized));
                vars.insert(
                    "known",
                    if aliases.is_empty() {
                        "(none registered)".into()
                    } else {
                        aliases.keys().cloned().collect::<Vec<_>>().join(", ")
                    },
                );
                if let Some(failure) = unavailable {
                    return Err(failure.render(&vars));
                }
                vars.insert(
                    "key_error",
                    python_repr(
                        &unknown_key_error
                            .as_ref()
                            .map(|s| render(s, &vars))
                            .unwrap_or_else(|| family.to_owned()),
                    ),
                );
                let Some(path) = aliases.get(&normalized) else {
                    return Err(unknown.render(&vars));
                };
                let target = resolve(path, config_root).map_err(io_failure)?;
                vars.insert("family_root", path_text(&target)?);
                let requested = resolve(root, cwd).map_err(io_failure)?;
                let current_root = resolve(config_root, cwd).map_err(io_failure)?;
                let cwd_root = resolve(cwd, cwd).map_err(io_failure)?;
                if let Some(failure) = root_conflict {
                    let conflict = if *current {
                        target != current_root
                    } else {
                        requested != target && requested != cwd_root
                    };
                    if conflict {
                        return Err(failure.render(&vars));
                    }
                }
                Ok(if *current { None } else { Some(target) })
            }
        }
    }
    fn check_repository(
        &self,
        cwd: &Path,
        root: &Path,
        args: &Value,
        environment: &BTreeMap<OsString, OsString>,
    ) -> Result<(), PolicyFailure> {
        let Some(failure) = &self.repository_local else {
            return Ok(());
        };
        let requested = resolve(root, cwd).map_err(io_failure)?;
        let Some(target_root) = git_root(&requested, cwd, environment)? else {
            return Ok(());
        };
        let current_root = git_root(cwd, cwd, environment)?;
        if current_root.as_ref() != Some(&target_root) || requested != target_root {
            return Err(failure.render(&variables(root, cwd, root, args)?));
        }
        Ok(())
    }
}
fn family(args: &Value) -> Option<&str> {
    args.get("family").and_then(Value::as_str)
}
fn variables(
    config_root: &Path,
    cwd: &Path,
    root: &Path,
    args: &Value,
) -> Result<BTreeMap<&'static str, String>, PolicyFailure> {
    let family = family(args).unwrap_or("");
    Ok(BTreeMap::from([
        ("family", family.to_owned()),
        ("family_repr", python_repr(family)),
        ("normalized_repr", python_repr(family)),
        ("known", String::new()),
        ("key_error", python_repr(family)),
        ("family_root", String::new()),
        (
            "requested_root",
            path_text(&resolve(root, cwd).map_err(io_failure)?)?,
        ),
        (
            "config_root",
            path_text(&resolve(config_root, cwd).map_err(io_failure)?)?,
        ),
        ("cwd", path_text(&resolve(cwd, cwd).map_err(io_failure)?)?),
    ]))
}
fn path_text(path: &Path) -> Result<String, PolicyFailure> {
    path.to_str()
        .map(str::to_owned)
        .ok_or_else(|| PolicyFailure {
            kind: "UnicodeError".into(),
            message: "native target policy requires UTF-8 paths".into(),
            stderr: None,
        })
}
fn io_failure(error: io::Error) -> PolicyFailure {
    PolicyFailure {
        kind: "OSError".into(),
        message: error.to_string(),
        stderr: None,
    }
}
fn set_root(args: &mut Value, path: &Path) -> Result<(), PolicyFailure> {
    args["repo_root"] = json!({"$type":"path","value":path_text(path)?});
    Ok(())
}
fn resolve(path: &Path, cwd: &Path) -> io::Result<PathBuf> {
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        cwd.join(path)
    };
    match fs::canonicalize(&path) {
        Ok(path) => Ok(crate::supply::plain(path)),
        Err(e) if e.kind() == io::ErrorKind::NotFound => {
            let Some(parent) = path.parent() else {
                return Err(e);
            };
            let Some(name) = path.file_name() else {
                return Err(e);
            };
            Ok(resolve(parent, cwd)?.join(name))
        }
        Err(e) => Err(e),
    }
}
fn git_root(
    path: &Path,
    cwd: &Path,
    environment: &BTreeMap<OsString, OsString>,
) -> Result<Option<PathBuf>, PolicyFailure> {
    let output = Command::new("git")
        .arg("-C")
        .arg(path)
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(cwd)
        .env_clear()
        .envs(environment)
        .output()
        .map_err(io_failure)?;
    if !output.status.success() {
        return Ok(None);
    }
    let text = String::from_utf8(output.stdout).map_err(|e| PolicyFailure {
        kind: "UnicodeDecodeError".into(),
        message: e.to_string(),
        stderr: None,
    })?;
    Ok(Some(
        resolve(Path::new(text.trim()), cwd).map_err(io_failure)?,
    ))
}
fn python_repr(text: &str) -> String {
    crate::executor_execute::repr(text)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn closed_versioned_schema() {
        for value in [
            json!({"version":2,"target_admission":{}}),
            json!({"version":true,"target_admission":{}}),
            json!({"version":1,"target_admission":{},"unknown":true}),
            json!({"version":1,"target_admission":{"authorize_target":"yes"}}),
            json!({"version":1,"target_admission":{"family":{"mode":"reject","failure":{"kind":"Oops","message":"x"}}}}),
        ] {
            assert!(NativePolicy::parse(&value).is_err(), "{value}");
        }
        assert!(NativePolicy::parse(&json!({"version":1,"target_admission":{}})).is_ok());
    }

    #[test]
    fn absent_policy_remains_optional_but_invalid_policy_fails_load() {
        use crate::executor_local::LocalConfig;
        assert!(
            LocalConfig::parse("{}")
                .unwrap()
                .native_policy()
                .unwrap()
                .is_none()
        );
        assert!(LocalConfig::parse(r#"{"native_policy":{"version":2}}"#).is_err());
    }

    #[test]
    fn python_repr_quotes_and_control_characters() {
        assert_eq!(python_repr("a'b"), "\"a'b\"");
        assert_eq!(python_repr("a\nb"), "'a\\nb'");
        assert_eq!(python_repr("\u{d55c}\u{ae00}"), "'\u{d55c}\u{ae00}'");
        assert_eq!(python_repr("\u{a0}\u{200b}"), "'\\xa0\\u200b'");
    }

    #[test]
    fn malformed_modes_templates_and_failure_categories_are_closed() {
        let failure = json!({"kind":"ValueError","message":"unknown {family_repr}"});
        let base = json!({"version":1,"target_admission":{"family":{
            "mode":"alias_map","aliases":{},"unknown":failure
        }}});
        for (field, field_value) in [
            ("mode", json!("arbitrary")),
            ("normalization", json!(false)),
            ("normalization", json!("arbitrary")),
            ("aliases", json!([])),
            ("aliases", json!({"x":null})),
            ("unknown", json!({"kind":"ValueError","message":"{exec}"})),
            (
                "unknown",
                json!({"kind":"ValueError","message":"unclosed {"}),
            ),
            (
                "unknown",
                json!({"kind":"ValueError","message":"x","extra":true}),
            ),
            (
                "unknown",
                json!({"kind":"ValueError","message":"x","stderr":"x"}),
            ),
            ("unknown", json!({"kind":"SystemExit","message":"2"})),
            ("unknown_key_error", json!("recursive {key_error}")),
        ] {
            let mut value = base.clone();
            value["target_admission"]["family"][field] = field_value;
            assert!(NativePolicy::parse(&value).is_err(), "{value}");
        }
        let mut value = base;
        value["target_admission"]["authorize_target"] = json!(true);
        assert!(NativePolicy::parse(&value).is_err());
        value["target_admission"]["repository_local"] =
            json!({"kind":"ValueError","message":"repository local"});
        assert!(NativePolicy::parse(&value).is_ok());
    }
}
