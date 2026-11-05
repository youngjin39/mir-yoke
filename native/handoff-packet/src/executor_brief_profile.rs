//! Finite repository-selected DispatchBrief contracts; no consumer imports.
use crate::{
    executor_brief_render::{ValidationIssue, python_value_repr, render_errors},
    executor_local::{Error, LocalConfig},
    executor_target_policy::PolicyFailure,
};
use serde_json::{Map, Value, json};
use std::{collections::BTreeMap, fs, io::Read, path::Path};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Contract {
    BaseV1,
    ClosedVerifierV2,
}
#[derive(Clone, Debug)]
pub struct BriefProfile {
    contract: Contract,
    input_limit_bytes: Option<u64>,
    goal_bound: bool,
}
impl BriefProfile {
    pub fn parse(value: &Value) -> Result<Self, Error> {
        let data = value
            .as_object()
            .ok_or_else(|| invalid("brief_profile must be an object"))?;
        for key in data.keys() {
            if !["name", "input_limit_bytes", "input_bound"].contains(&key.as_str()) {
                return Err(invalid(format!("unknown brief_profile field: {key}")));
            }
        }
        let contract = match data.get("name").and_then(Value::as_str) {
            Some("base_v1") => Contract::BaseV1,
            Some("closed_verifier_v2") => Contract::ClosedVerifierV2,
            _ => {
                return Err(invalid(
                    "brief_profile.name must be base_v1 or closed_verifier_v2",
                ));
            }
        };
        let input_limit_bytes = data
            .get("input_limit_bytes")
            .map(|value| {
                value.as_u64().filter(|value| *value > 0).ok_or_else(|| {
                    invalid("brief_profile.input_limit_bytes must be a positive integer")
                })
            })
            .transpose()?;
        let goal_bound = match data.get("input_bound") {
            None => false,
            Some(Value::String(name))
                if name == "expanded_goal" && contract == Contract::BaseV1 =>
            {
                true
            }
            _ => {
                return Err(invalid(
                    "brief_profile.input_bound requires base_v1 and expanded_goal",
                ));
            }
        };
        Ok(Self {
            contract,
            input_limit_bytes,
            goal_bound,
        })
    }
    /// Bound the validated goal (or plain text), independently of raw file size.
    pub fn bound_text(&self, text: &str, root: &Path) -> Result<(), PolicyFailure> {
        if !self.goal_bound {
            return Ok(());
        }
        let config = LocalConfig::load(root).map_err(local_failure)?;
        let limit = config
            .raw()
            .get("input_limit_bytes")
            .ok_or_else(|| failure("KeyError", "'input_limit_bytes'"))?;
        let comparison_limit = match limit {
            Value::Bool(value) => json!(u8::from(*value)),
            _ => limit.clone(),
        };
        if !matches!(comparison_limit, Value::Number(_))
            && comparison_limit.get(config.numeric_tag()).is_none()
        {
            return Err(failure(
                "TypeError",
                format!(
                    "'>' not supported between instances of 'int' and '{}'",
                    crate::executor_brief_render::python_type(limit)
                ),
            ));
        }
        let size = text.len() as u64;
        if config
            .compare(&json!(size), &comparison_limit)
            .map_err(local_failure)?
            == Some(std::cmp::Ordering::Greater)
        {
            let limit = match limit {
                Value::Bool(true) => "True".to_owned(),
                Value::Bool(false) => "False".to_owned(),
                _ => match config.numeric_repr(limit).as_str() {
                    "Infinity" => "inf".into(),
                    "-Infinity" => "-inf".into(),
                    "NaN" => "nan".into(),
                    value => value.to_owned(),
                },
            };
            return Err(failure(
                "ValueError",
                format!(
                    "delegated input exceeds {limit} bytes ({size}); refusing rather than truncating"
                ),
            ));
        }
        Ok(())
    }
    pub fn load(&self, path: &Path) -> Result<Value, PolicyFailure> {
        self.load_cached(path).map(|(value, _)| value)
    }
    pub fn load_cached(&self, path: &Path) -> Result<(Value, String), PolicyFailure> {
        let file = fs::File::open(path).map_err(|error| io_failure(error, path))?;
        let mut bytes = Vec::new();
        match self.input_limit_bytes {
            Some(limit) => {
                file.take(limit.saturating_add(1))
                    .read_to_end(&mut bytes)
                    .map_err(|error| io_failure(error, path))?;
            }
            None => {
                let mut file = file;
                file.read_to_end(&mut bytes)
                    .map_err(|error| io_failure(error, path))?;
            }
        }
        let value = self.validate_bytes(&bytes)?;
        Ok((value, crate::digest::sha256(&bytes)))
    }
    pub fn validate_bytes(&self, bytes: &[u8]) -> Result<Value, PolicyFailure> {
        if self
            .input_limit_bytes
            .is_some_and(|limit| bytes.len() as u64 > limit)
        {
            return Err(failure(
                "ValueError",
                "DispatchBrief input exceeds configured input_limit_bytes",
            ));
        }
        let text = String::from_utf8(bytes.to_vec())
            .map_err(|error| local_failure(Error::Unicode(error)))?;
        let payload = LocalConfig::default()
            .parse_argument(&text)
            .map_err(local_failure)?;
        let mut reprs = BTreeMap::new();
        ReprCursor {
            text: &text,
            offset: 0,
            reprs: &mut reprs,
        }
        .value(&[]);
        self.validate(&payload, &reprs)
    }
    fn validate(
        &self,
        payload: &Value,
        reprs: &BTreeMap<Vec<String>, String>,
    ) -> Result<Value, PolicyFailure> {
        let root_type = issue(Vec::new(), "", "", payload, reprs).input_type;
        let Some(data) = payload.as_object().filter(|_| root_type.is_none()) else {
            return Err(failure(
                "TypeError",
                format!(
                    "mir.core.contracts.dispatch_brief.DispatchBrief() argument after ** must be a mapping, not {}",
                    root_type
                        .as_deref()
                        .unwrap_or_else(|| crate::executor_brief_render::python_type(payload))
                ),
            ));
        };
        let mut output = Map::new();
        let mut issues = Vec::new();
        let typed = self.contract == Contract::ClosedVerifierV2;
        let mut fields = vec![
            "version",
            "task_id",
            "phase_id",
            "slice_id",
            "target_agent",
            "user_intent",
            "expanded_goal",
            "owned_scope",
            "out_of_scope",
        ];
        if typed {
            fields.push("verification_ids");
        }
        fields.extend([
            "verification_commands",
            "stop_conditions",
            "handoff_refs",
            "tdd_change_refs",
            "resume_state_ref",
            "source_refs",
        ]);
        for key in &fields {
            let location = vec![(*key).into()];
            let value = data.get(*key);
            match *key {
                "version" => match value {
                    None => {
                        output.insert((*key).into(), json!(if typed { 2 } else { 1 }));
                    }
                    Some(value) => match integer(value, reprs.get(&location).map(String::as_str)) {
                        Ok(parsed) => {
                            output.insert((*key).into(), parsed);
                        }
                        Err((message, code)) => {
                            issues.push(issue(location, message, code, value, reprs))
                        }
                    },
                },
                "phase_id" => {
                    if value.is_none_or(Value::is_null) {
                        output.insert((*key).into(), Value::Null);
                    } else if let Some(value) = value {
                        string_field(value, location, false, &mut output, key, &mut issues, reprs);
                    }
                }
                "source_refs" => {
                    if let Some(value) = value {
                        if let Some(source) = value.as_object().filter(|_| {
                            reprs
                                .get(&location)
                                .is_none_or(|repr| repr.starts_with('{'))
                        }) {
                            let mut parsed = Map::new();
                            for source_key in ["task_spec", "plan", "phase"] {
                                let loc = vec![(*key).into(), source_key.into()];
                                match source.get(source_key) {
                                    Some(value) => string_field(
                                        value,
                                        loc,
                                        source_key != "plan",
                                        &mut parsed,
                                        source_key,
                                        &mut issues,
                                        reprs,
                                    ),
                                    None if source_key == "plan" => {
                                        parsed.insert(source_key.into(), json!("tasks/plan.md"));
                                    }
                                    None => issues.push(issue(
                                        loc,
                                        "Field required",
                                        "missing",
                                        value,
                                        reprs,
                                    )),
                                }
                            }
                            for extra in ordered_keys(source, reprs.get(&location)) {
                                if !["task_spec", "plan", "phase"].contains(&extra.as_str()) {
                                    issues.push(issue(
                                        vec![(*key).into(), extra.clone()],
                                        "Extra inputs are not permitted",
                                        "extra_forbidden",
                                        &source[&extra],
                                        reprs,
                                    ));
                                }
                            }
                            output.insert((*key).into(), Value::Object(parsed));
                        } else {
                            issues.push(issue(location, "Input should be a valid dictionary or instance of DispatchBriefSourceRefs", "model_type", value, reprs));
                        }
                    } else {
                        issues.push(issue(location, "Field required", "missing", payload, reprs));
                    }
                }
                "owned_scope"
                | "out_of_scope"
                | "verification_ids"
                | "verification_commands"
                | "stop_conditions"
                | "handoff_refs"
                | "tdd_change_refs" => {
                    let required = ["owned_scope", "stop_conditions"].contains(key)
                        || (*key == "verification_commands" && !typed);
                    match value {
                        None if required => issues.push(issue(
                            location,
                            "Field required",
                            "missing",
                            payload,
                            reprs,
                        )),
                        None => {
                            output.insert((*key).into(), json!([]));
                        }
                        Some(value) => {
                            if let Some(array) = value.as_array() {
                                let mut parsed = Vec::new();
                                for (index, item) in array.iter().enumerate() {
                                    if item.is_string() {
                                        parsed.push(item.clone());
                                    } else {
                                        issues.push(issue(
                                            vec![(*key).into(), index.to_string()],
                                            "Input should be a valid string",
                                            "string_type",
                                            item,
                                            reprs,
                                        ));
                                    }
                                }
                                if required && parsed.is_empty() {
                                    issues.push(issue(
                                        location,
                                        "Tuple should have at least 1 item after validation, not 0",
                                        "too_short",
                                        value,
                                        reprs,
                                    ));
                                }
                                output.insert((*key).into(), Value::Array(parsed));
                            } else {
                                issues.push(issue(
                                    location,
                                    "Input should be a valid tuple",
                                    "tuple_type",
                                    value,
                                    reprs,
                                ));
                            }
                        }
                    }
                }
                _ => match value {
                    Some(value) => {
                        string_field(value, location, true, &mut output, key, &mut issues, reprs)
                    }
                    None => {
                        issues.push(issue(location, "Field required", "missing", payload, reprs))
                    }
                },
            }
        }
        for key in ordered_keys(data, reprs.get(&Vec::new())) {
            if !fields.contains(&key.as_str()) {
                issues.push(issue(
                    vec![key.clone()],
                    "Extra inputs are not permitted",
                    "extra_forbidden",
                    &data[&key],
                    reprs,
                ));
            }
        }
        if issues.is_empty()
            && let Some(message) = contract_error(&output, typed)
        {
            issues.push(issue(
                Vec::new(),
                &format!("Value error, {message}"),
                "value_error",
                payload,
                reprs,
            ));
        }
        if issues.is_empty() {
            Ok(Value::Object(output))
        } else {
            Err(failure("ValidationError", render_errors(&issues)))
        }
    }
}
fn invalid(message: impl Into<String>) -> Error {
    Error::Invalid(message.into())
}
fn failure(kind: &str, message: impl Into<String>) -> PolicyFailure {
    PolicyFailure {
        kind: kind.into(),
        message: message.into(),
        stderr: None,
    }
}
fn local_failure(error: Error) -> PolicyFailure {
    failure(error.kind(), error.to_string())
}
fn io_failure(error: std::io::Error, path: &Path) -> PolicyFailure {
    let kind = match error.kind() {
        std::io::ErrorKind::NotFound => "FileNotFoundError",
        std::io::ErrorKind::PermissionDenied => "PermissionError",
        std::io::ErrorKind::IsADirectory => "IsADirectoryError",
        std::io::ErrorKind::NotADirectory => "NotADirectoryError",
        _ => "OSError",
    };
    let message = error.to_string();
    // Python reports C runtime errno text; on Windows Rust carries the Win32 code and text instead.
    let errno = match (cfg!(windows), error.kind()) {
        (true, std::io::ErrorKind::NotFound) => Some((2, "No such file or directory")),
        (true, std::io::ErrorKind::PermissionDenied) => Some((13, "Permission denied")),
        _ => error.raw_os_error().map(|number| {
            (
                number,
                message
                    .rsplit_once(" (os error ")
                    .map_or(message.as_str(), |(message, _)| message),
            )
        }),
    };
    let message = match errno {
        Some((number, text)) => format!(
            "[Errno {number}] {text}: {}",
            crate::executor_execute::repr(&path.display().to_string())
        ),
        None => message.clone(),
    };
    failure(kind, message)
}
fn issue(
    location: Vec<String>,
    message: &str,
    code: &str,
    input: &Value,
    reprs: &BTreeMap<Vec<String>, String>,
) -> ValidationIssue {
    let repr_location = if code == "missing" {
        &location[..location.len().saturating_sub(1)]
    } else {
        &location
    };
    let input_repr = reprs.get(repr_location).cloned();
    let input_type = input_repr
        .as_deref()
        .filter(|repr| input.is_object() && !repr.starts_with('{'))
        .map(|repr| {
            if repr.contains(['.', 'e', 'E']) || ["nan", "inf", "-inf"].contains(&repr) {
                "float"
            } else {
                "int"
            }
            .to_owned()
        });
    ValidationIssue {
        location: location.clone(),
        message: message.into(),
        code: code.into(),
        input: input.clone(),
        input_repr,
        input_type,
    }
}
fn string_field(
    value: &Value,
    location: Vec<String>,
    nonempty: bool,
    output: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ValidationIssue>,
    reprs: &BTreeMap<Vec<String>, String>,
) {
    if let Some(text) = value.as_str() {
        if nonempty && text.is_empty() {
            issues.push(issue(
                location,
                "String should have at least 1 character",
                "string_too_short",
                value,
                reprs,
            ));
        } else {
            output.insert(key.into(), value.clone());
        }
    } else {
        issues.push(issue(
            location,
            "Input should be a valid string",
            "string_type",
            value,
            reprs,
        ));
    }
}
fn integer(value: &Value, raw: Option<&str>) -> Result<Value, (&'static str, &'static str)> {
    let bad = ("Input should be a valid integer", "int_type");
    match value {
        Value::Bool(value) => Ok(json!(u8::from(*value))),
        Value::Number(number) if number.is_i64() || number.is_u64() => Ok(value.clone()),
        Value::Number(number) => {
            let Some(number) = number.as_f64() else {
                return Err(bad);
            };
            if number.fract() != 0.0 {
                return Err((
                    "Input should be a valid integer, got a number with a fractional part",
                    "int_from_float",
                ));
            }
            if number >= i64::MIN as f64 && number < i64::MAX as f64 {
                Ok(json!(number as i64))
            } else {
                Err((
                    "Unable to parse input string as an integer, exceeded maximum size",
                    "int_parsing_size",
                ))
            }
        }
        Value::String(text) => {
            let text = text.trim();
            if text
                .strip_prefix(['+', '-'])
                .unwrap_or(text)
                .trim_start_matches('0')
                .bytes()
                .filter(u8::is_ascii_digit)
                .count()
                > 4300
            {
                return Err((
                    "Unable to parse input string as an integer, exceeded maximum size",
                    "int_parsing_size",
                ));
            }
            let digits = text.strip_prefix(['+', '-']).unwrap_or(text);
            let head_valid = |head: &str| {
                !head.is_empty()
                    && head.split('_').all(|part| {
                        !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit())
                    })
            };
            let valid = if let Some((head, tail)) = digits.split_once('.') {
                head_valid(head) && !tail.is_empty() && tail.bytes().all(|byte| byte == b'0')
            } else {
                head_valid(digits)
            };
            if !valid {
                return Err((
                    "Input should be a valid integer, unable to parse string as an integer",
                    "int_parsing",
                ));
            }
            let normalized = text.replace('_', "");
            let integral =
                normalized
                    .split_once('.')
                    .map_or(normalized.as_str(), |(head, tail)| {
                        if !tail.is_empty() && tail.chars().all(|ch| ch == '0') {
                            head
                        } else {
                            ""
                        }
                    });
            Ok(integral
                .parse::<i64>()
                .map(|value| json!(value))
                .unwrap_or_else(|_| value.clone()))
        }
        Value::Object(_) if raw.is_some_and(|raw| !raw.starts_with('{')) => {
            if raw.is_some_and(|raw| ["nan", "inf", "-inf"].contains(&raw)) {
                Err(("Input should be a finite number", "finite_number"))
            } else {
                Ok(value.clone())
            }
        }
        _ => Err(bad),
    }
}
fn contract_error(output: &Map<String, Value>, typed: bool) -> Option<String> {
    let version = output["version"].as_i64();
    if typed {
        let ids = output["verification_ids"].as_array()?;
        let commands = output["verification_commands"].as_array()?;
        match version {
            Some(2) => {
                if ids.is_empty() {
                    return Some("DispatchBrief v2 requires verification_ids".into());
                }
                let mut unknown = ids
                    .iter()
                    .filter_map(Value::as_str)
                    .filter(|id| {
                        ![
                            "python-tests",
                            "project-verification",
                            "ruff",
                            "mypy",
                            "spec-projections",
                            "git-diff-check",
                        ]
                        .contains(id)
                    })
                    .collect::<Vec<_>>();
                unknown.sort();
                unknown.dedup();
                if !unknown.is_empty() {
                    return Some(format!(
                        "DispatchBrief contains unknown verification_ids: [{}]",
                        unknown
                            .iter()
                            .map(|id| crate::executor_execute::repr(id))
                            .collect::<Vec<_>>()
                            .join(", ")
                    ));
                }
                if !commands.is_empty() {
                    return Some("DispatchBrief v2 forbids verification_commands".into());
                }
            }
            Some(1) => {
                if commands.is_empty() {
                    return Some("DispatchBrief v1 requires verification_commands".into());
                }
                if !ids.is_empty() {
                    return Some("DispatchBrief v1 forbids verification_ids".into());
                }
            }
            _ => return Some("DispatchBrief.version must be 1 or 2".into()),
        }
    } else if version != Some(1) {
        return Some("DispatchBrief.version must be 1".into());
    }
    let expected = format!(
        "tasks/dispatch/{}/{}.json",
        output["task_id"].as_str()?,
        output["slice_id"].as_str()?
    );
    if output["resume_state_ref"].as_str() != Some(&expected) {
        return Some(format!(
            "DispatchBrief.resume_state_ref must match {}",
            crate::executor_execute::repr(&expected)
        ));
    }
    if output["source_refs"]["plan"].as_str() != Some("tasks/plan.md") {
        return Some("DispatchBrief.source_refs.plan must be 'tasks/plan.md'".into());
    }
    None
}

// Admission uses the existing parser. This second pass only preserves object
// insertion order in Python diagnostic representations.
struct ReprCursor<'a, 'b> {
    text: &'a str,
    offset: usize,
    reprs: &'b mut BTreeMap<Vec<String>, String>,
}
impl ReprCursor<'_, '_> {
    fn whitespace(&mut self) {
        while self
            .text
            .as_bytes()
            .get(self.offset)
            .is_some_and(u8::is_ascii_whitespace)
        {
            self.offset += 1;
        }
    }
    fn string(&mut self) -> String {
        let start = self.offset;
        self.offset += 1;
        while let Some(byte) = self.text.as_bytes().get(self.offset) {
            self.offset += 1;
            if *byte == b'\\' {
                self.offset += 1;
            } else if *byte == b'"' {
                break;
            }
        }
        serde_json::from_str(&self.text[start..self.offset]).unwrap_or_default()
    }
    fn value(&mut self, path: &[String]) -> String {
        self.whitespace();
        let result = match self.text.as_bytes().get(self.offset) {
            Some(b'{') => {
                self.offset += 1;
                let mut entries = Vec::<(String, String)>::new();
                loop {
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b'}') {
                        self.offset += 1;
                        break;
                    }
                    let key = self.string();
                    self.whitespace();
                    self.offset += 1;
                    let mut child = path.to_vec();
                    child.push(key.clone());
                    let value = self.value(&child);
                    if let Some(existing) = entries.iter_mut().find(|(name, _)| name == &key) {
                        existing.1 = value;
                    } else {
                        entries.push((key, value));
                    }
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b',') {
                        self.offset += 1;
                    }
                }
                format!(
                    "{{{}}}",
                    entries
                        .iter()
                        .map(|(key, value)| format!(
                            "{}: {value}",
                            crate::executor_execute::repr(key)
                        ))
                        .collect::<Vec<_>>()
                        .join(", ")
                )
            }
            Some(b'[') => {
                self.offset += 1;
                let mut values = Vec::new();
                loop {
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b']') {
                        self.offset += 1;
                        break;
                    }
                    let mut child = path.to_vec();
                    child.push(values.len().to_string());
                    values.push(self.value(&child));
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b',') {
                        self.offset += 1;
                    }
                }
                format!("[{}]", values.join(", "))
            }
            Some(b'"') => crate::executor_execute::repr(&self.string()),
            _ => {
                let start = self.offset;
                while self
                    .text
                    .as_bytes()
                    .get(self.offset)
                    .is_some_and(|byte| !b",}] \n\r\t".contains(byte))
                {
                    self.offset += 1;
                }
                let token = &self.text[start..self.offset];
                match token {
                    "NaN" => "nan".into(),
                    "Infinity" => "inf".into(),
                    "-Infinity" => "-inf".into(),
                    _ if token
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || byte == b'-') =>
                    {
                        token.into()
                    }
                    _ => serde_json::from_str::<Value>(token)
                        .map(|value| python_value_repr(&value))
                        .unwrap_or_else(|_| token.into()),
                }
            }
        };
        self.reprs.insert(path.to_vec(), result.clone());
        result
    }
}
fn ordered_keys(data: &Map<String, Value>, repr: Option<&String>) -> Vec<String> {
    let mut keys = data.keys().cloned().collect::<Vec<_>>();
    if let Some(repr) = repr {
        keys.sort_by_key(|key| {
            repr.find(&format!("{}: ", crate::executor_execute::repr(key)))
                .unwrap_or(usize::MAX)
        });
    }
    keys
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn python_profile_fixtures() {
        let fixtures: Value = serde_json::from_str(include_str!(
            "../tests/fixtures/executor_brief_profile.json"
        ))
        .unwrap();
        for name in ["base_v1", "closed_verifier_v2"] {
            let profile = BriefProfile::parse(&json!({"name":name})).unwrap();
            for case in fixtures[name].as_array().unwrap() {
                let result = profile.validate_bytes(case["text"].as_str().unwrap().as_bytes());
                if let Some(expected) = case.get("value") {
                    assert_eq!(result.unwrap(), *expected, "{name}/{}", case["name"]);
                } else {
                    let error = result.unwrap_err();
                    assert_eq!(error.kind, case["kind"], "{name}/{}", case["name"]);
                    assert_eq!(error.message, case["message"], "{name}/{}", case["name"]);
                }
            }
        }
    }
    #[test]
    fn extended_numeric_roots_are_not_mapping_inputs() {
        let profile = BriefProfile::parse(&json!({"name":"base_v1"})).unwrap();
        for (input, kind) in [
            ("NaN", "float"),
            ("10000000000000000000000000000000000000000", "int"),
        ] {
            let error = profile.validate_bytes(input.as_bytes()).unwrap_err();
            assert_eq!(error.kind, "TypeError");
            assert!(error.message.ends_with(&format!("mapping, not {kind}")));
        }
    }
    #[test]
    fn finite_configuration_and_input_bound() {
        for value in [
            json!({}),
            json!({"name":"unknown"}),
            json!({"name":"base_v1","extra":true}),
            json!({"name":"base_v1","input_limit_bytes":true}),
            json!({"name":"base_v1","input_limit_bytes":0}),
        ] {
            assert!(BriefProfile::parse(&value).is_err());
        }
        let profile =
            BriefProfile::parse(&json!({"name":"base_v1","input_limit_bytes":2})).unwrap();
        assert_eq!(
            profile.validate_bytes(b"{} ").unwrap_err().kind,
            "ValueError"
        );
        assert_eq!(
            profile.validate_bytes(b"{}").unwrap_err().kind,
            "ValidationError"
        );
        assert_eq!(
            profile.validate_bytes(&[0xff]).unwrap_err().kind,
            "UnicodeDecodeError"
        );
    }
    #[test]
    fn filesystem_errors_preserve_python_errno_and_filename() {
        let error = io_failure(
            std::io::Error::from_raw_os_error(2),
            Path::new("missing brief.json"),
        );
        assert_eq!(error.kind, "FileNotFoundError");
        assert_eq!(
            error.message,
            "[Errno 2] No such file or directory: 'missing brief.json'"
        );
    }
}
