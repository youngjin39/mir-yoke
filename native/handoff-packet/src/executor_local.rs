//! Read-only executor-local data. Validation stays lazy, as in the Python callers.
//! Unknown fields remain available to repository-owned extensions.
use serde_json::{Map, Value, json};
use std::{cmp::Ordering, fmt, fs, io, path::Path};

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Unicode(std::string::FromUtf8Error),
    Json(serde_json::Error),
    Syntax(String),
    Object,
    Invalid(String),
    Type(String),
    Overflow,
    Depth,
}
impl Error {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Io(_) => "OSError",
            Self::Unicode(_) => "UnicodeDecodeError",
            Self::Json(_) | Self::Syntax(_) => "JSONDecodeError",
            Self::Object | Self::Invalid(_) => "ValueError",
            Self::Type(_) => "TypeError",
            Self::Overflow => "OverflowError",
            Self::Depth => "RecursionError",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => error.fmt(f),
            Self::Unicode(error) => f.write_str(&python_unicode_error(error)),
            Self::Json(error) => error.fmt(f),
            Self::Object => f.write_str("<config> must contain a JSON object"),
            Self::Invalid(message) | Self::Type(message) | Self::Syntax(message) => {
                f.write_str(message)
            }
            Self::Overflow => f.write_str("int too large to convert to float"),
            Self::Depth => f.write_str("maximum supported JSON nesting depth exceeded (64)"),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Unicode(error) => Some(error),
            Self::Json(error) => Some(error),
            Self::Object
            | Self::Invalid(_)
            | Self::Type(_)
            | Self::Syntax(_)
            | Self::Overflow
            | Self::Depth => None,
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct LocalConfig {
    data: Map<String, Value>,
    numeric_tag: String,
    verifier_order: Vec<String>,
}
impl LocalConfig {
    pub fn load(repo_root: &Path) -> Result<Self, Error> {
        Self::read_path(&repo_root.join("config/mir-executor.local.json"))
    }

    pub fn read_path(path: &Path) -> Result<Self, Error> {
        // Python Path.exists treats a dangling symlink as absent. Other read errors
        // must remain errors, including directories and invalid UTF-8.
        match fs::metadata(path) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Self::default()),
            Err(error) => return Err(Error::Io(error)),
            Ok(_) => {}
        }
        let bytes = fs::read(path).map_err(Error::Io)?;
        Self::parse_bytes(bytes).map_err(|error| match error {
            Error::Object => {
                Error::Invalid(format!("{} must contain a JSON object", path.display()))
            }
            other => other,
        })
    }

    pub fn parse(text: &str) -> Result<Self, Error> {
        let verifier_order = JsonSyntax::validate(text)?;
        let mut numeric_tag = "$python_number".to_owned();
        while text.contains(&numeric_tag) {
            numeric_tag.push('_');
        }
        let normalized = python_numbers(text, &numeric_tag);
        let value: Value = serde_json::from_str(&normalized).map_err(Error::Json)?;
        match value {
            Value::Object(data) => {
                let config = Self {
                    data,
                    numeric_tag,
                    verifier_order,
                };
                config.native_policy()?;
                Ok(config)
            }
            _ => Err(Error::Object),
        }
    }

    /// Owned versioned policy is strict; existing extension keys stay lazy.
    pub fn native_policy(
        &self,
    ) -> Result<Option<crate::executor_target_policy::NativePolicy>, Error> {
        self.data
            .get("native_policy")
            .map(crate::executor_target_policy::NativePolicy::parse)
            .transpose()
    }

    pub(crate) fn verifier_order(&self) -> &[String] {
        &self.verifier_order
    }

    pub fn parse_bytes(bytes: Vec<u8>) -> Result<Self, Error> {
        let text = String::from_utf8(bytes).map_err(Error::Unicode)?;
        Self::parse(&text)
    }

    /// Extended Python JSON scalars use `{numeric_tag: original_lexeme}` because
    /// serde_json cannot represent nonfinite floats or arbitrary precision ints.
    pub fn numeric_tag(&self) -> &str {
        &self.numeric_tag
    }

    /// Parse a validator argument with the same extended-number representation.
    pub fn parse_argument(&self, text: &str) -> Result<Value, Error> {
        JsonSyntax::validate(text)?;
        serde_json::from_str(&python_numbers(text, &self.numeric_tag)).map_err(Error::Json)
    }

    pub fn raw(&self) -> &Map<String, Value> {
        &self.data
    }

    /// Effective data defaults only; this does not validate unused policy fields.
    pub fn defaults(&self) -> Map<String, Value> {
        let mut data = Map::from_iter([
            ("timeout_seconds_range".into(), Value::Null),
            ("max_codex_attempts_cap".into(), Value::Null),
            ("input_limit_bytes".into(), Value::Null),
            ("codex_sandbox_default".into(), json!("workspace-write")),
            ("child_env_filter".into(), json!(false)),
            ("child_env_extra_keys".into(), json!([])),
            ("require_review".into(), json!(false)),
            ("verifiers".into(), json!({})),
            ("verifier_env".into(), json!("inherit")),
            ("artifact_retention_days".into(), json!(30)),
        ]);
        data.extend(self.data.clone());
        data
    }

    pub fn validate_timeout(&self, value: Option<&Value>) -> Result<(), Error> {
        let bounds = self
            .data
            .get("timeout_seconds_range")
            .filter(|v| !v.is_null());
        if let Some(bounds) = bounds {
            let valid = if let Some(values) = bounds.as_array().filter(|v| v.len() == 2) {
                self.positive(&values[0])?
                    && self.positive(&values[1])?
                    && self.compare(&values[0], &values[1])? != Some(Ordering::Greater)
            } else {
                false
            };
            if !valid {
                return Err(Error::Invalid(
                    "timeout_seconds_range must be [min, max], finite and positive".into(),
                ));
            }
        }
        let Some(value) = value.filter(|v| !v.is_null()) else {
            return Ok(());
        };
        if !self.positive(value)? {
            return Err(Error::Invalid("timeout must be finite and positive".into()));
        }
        if let Some(bounds) = bounds {
            let values = bounds.as_array().ok_or(Error::Object)?;
            if self.compare(value, &values[0])? == Some(Ordering::Less)
                || self.compare(value, &values[1])? == Some(Ordering::Greater)
            {
                return Err(Error::Invalid(format!(
                    "timeout must be within timeout_seconds_range [{}, {}]",
                    self.numeric_repr(&values[0]),
                    self.numeric_repr(&values[1])
                )));
            }
        }
        Ok(())
    }

    pub fn sandbox(&self) -> Result<&str, Error> {
        match self.data.get("codex_sandbox_default") {
            None => Ok("workspace-write"),
            Some(Value::String(value))
                if ["workspace-write", "read-only", "danger-full-access"]
                    .contains(&value.as_str()) =>
            {
                Ok(value)
            }
            Some(Value::Array(_)) => Err(Error::Type("unhashable type: 'list'".into())),
            Some(value) if value.get(&self.numeric_tag).is_some() => {
                Err(Error::Invalid("invalid codex_sandbox_default".into()))
            }
            Some(Value::Object(_)) => Err(Error::Type("unhashable type: 'dict'".into())),
            Some(_) => Err(Error::Invalid("invalid codex_sandbox_default".into())),
        }
    }

    pub fn verifier_env(&self) -> Result<&str, Error> {
        match self.data.get("verifier_env") {
            None => Ok("inherit"),
            Some(Value::String(value)) if ["inherit", "isolated"].contains(&value.as_str()) => {
                Ok(value)
            }
            Some(_) => Err(Error::Invalid(
                "verifier_env must be \"inherit\" or \"isolated\"".into(),
            )),
        }
    }

    pub fn retention_days(&self, explicit: Option<&Value>) -> Result<Value, Error> {
        // None is Python's request to consult local configuration.
        let value = explicit
            .filter(|v| !v.is_null())
            .or_else(|| self.data.get("artifact_retention_days"));
        match value {
            None => Ok(json!(30)),
            Some(Value::Number(number)) if number.as_u64().is_some() => {
                Ok(Value::Number(number.clone()))
            }
            Some(value) if self.integer(value).is_some_and(|n| !n.starts_with('-')) => {
                Ok(value.clone())
            }
            Some(_) => Err(Error::Invalid(
                "artifact_retention_days must be a non-negative integer".into(),
            )),
        }
    }

    pub fn verifier_commands(&self, requested: &[&str]) -> Result<Vec<Vec<String>>, Error> {
        let empty = json!({});
        let verifiers = match self.data.get("verifiers") {
            None => &empty,
            Some(value) => value,
        };
        let keys: Vec<String> = match verifiers {
            Value::Object(values) if verifiers.get(&self.numeric_tag).is_none() => {
                values.keys().cloned().collect()
            }
            Value::Array(values) => {
                for value in values {
                    match value {
                        Value::Array(_) => {
                            return Err(Error::Type("unhashable type: 'list'".into()));
                        }
                        Value::Object(_) if value.get(&self.numeric_tag).is_none() => {
                            return Err(Error::Type("unhashable type: 'dict'".into()));
                        }
                        _ => {}
                    }
                }
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_owned)
                    .collect()
            }
            Value::String(value) => value.chars().map(|c| c.to_string()).collect(),
            other => {
                let name = match other {
                    Value::Null => "NoneType",
                    Value::Bool(_) => "bool",
                    _ if self.integer(other).is_some() => "int",
                    _ => "float",
                };
                return Err(Error::Type(format!("'{name}' object is not iterable")));
            }
        };
        let mut unknown: Vec<_> = requested
            .iter()
            .filter(|id| !keys.iter().any(|key| key == **id))
            .copied()
            .collect();
        unknown.sort_unstable();
        unknown.dedup();
        if !unknown.is_empty() {
            return Err(Error::Invalid(format!(
                "unknown-verifier:{}",
                unknown.join(",")
            )));
        }
        requested
            .iter()
            .map(|id| {
                match verifiers {
                    Value::Array(_) => {
                        return Err(Error::Type(
                            "list indices must be integers or slices, not str".into(),
                        ));
                    }
                    Value::String(_) => {
                        return Err(Error::Type(
                            "string indices must be integers, not 'str'".into(),
                        ));
                    }
                    _ => {}
                }
                let argv = verifiers.get(*id).and_then(Value::as_array);
                if let Some(argv) = argv.filter(|argv| {
                    !argv.is_empty()
                        && argv
                            .iter()
                            .all(|v| v.as_str().is_some_and(|s| !s.is_empty()))
                }) {
                    Ok(argv
                        .iter()
                        .filter_map(|v| v.as_str().map(str::to_owned))
                        .collect())
                } else {
                    Err(Error::Invalid(format!("invalid-verifier:{id}")))
                }
            })
            .collect()
    }

    /// Python accepts bool as an int here and ignores non-positive/non-int caps.
    pub fn validate_input_size(&self, bytes: u64) -> Result<(), Error> {
        let limit = match self.data.get("input_limit_bytes") {
            Some(Value::Bool(true)) => Some(1),
            Some(Value::Number(number)) => number.as_u64().filter(|n| *n > 0),
            _ => None,
        };
        if limit.is_some_and(|limit| bytes > limit) {
            return Err(Error::Invalid(
                "Codex input exceeds configured input_limit_bytes".into(),
            ));
        }
        Ok(())
    }

    pub fn require_review(&self) -> bool {
        self.data.get("require_review").is_some_and(truthy)
    }

    pub fn child_env_filter(&self) -> bool {
        self.data.get("child_env_filter").is_some_and(truthy)
    }

    pub fn validate_attempts(&self, attempts: u64) -> Result<(), Error> {
        if let Some(cap) = self
            .data
            .get("max_codex_attempts_cap")
            .filter(|v| !v.is_null())
        {
            let exceeded = match cap {
                Value::Bool(value) => attempts > u64::from(*value),
                Value::Number(_) => self.compare(&json!(attempts), cap)? == Some(Ordering::Greater),
                Value::Object(_) if cap.get(&self.numeric_tag).is_some() => {
                    self.compare(&json!(attempts), cap)? == Some(Ordering::Greater)
                }
                other => {
                    let name = match other {
                        Value::String(_) => "str",
                        Value::Array(_) => "list",
                        _ => "dict",
                    };
                    return Err(Error::Type(format!(
                        "'>' not supported between instances of 'int' and '{name}'"
                    )));
                }
            };
            if exceeded {
                return Err(Error::Invalid(
                    "max_codex_attempts exceeds local cap".into(),
                ));
            }
        }
        if attempts < 1 {
            return Err(Error::Invalid("max_codex_attempts must be positive".into()));
        }
        Ok(())
    }

    fn number(&self, value: &Value) -> Result<Option<f64>, Error> {
        if let Some(number) = value.as_f64() {
            return Ok(Some(number));
        }
        let Some(token) = value.get(&self.numeric_tag).and_then(Value::as_str) else {
            return Ok(None);
        };
        match token {
            "NaN" => Ok(Some(f64::NAN)),
            "Infinity" => Ok(Some(f64::INFINITY)),
            "-Infinity" => Ok(Some(f64::NEG_INFINITY)),
            _ => {
                let number = token.parse::<f64>().map_err(|_| Error::Overflow)?;
                if !token.contains(['.', 'e', 'E']) && !number.is_finite() {
                    return Err(Error::Overflow);
                }
                Ok(Some(number))
            }
        }
    }
    fn integer(&self, value: &Value) -> Option<String> {
        if let Value::Number(number) = value
            && (number.is_i64() || number.is_u64())
        {
            return Some(number.to_string());
        }
        value
            .get(&self.numeric_tag)
            .and_then(Value::as_str)
            .filter(|token| {
                !token.contains(['.', 'e', 'E'])
                    && token
                        .trim_start_matches('-')
                        .bytes()
                        .all(|b| b.is_ascii_digit())
            })
            .map(str::to_owned)
    }
    fn compare(&self, left: &Value, right: &Value) -> Result<Option<Ordering>, Error> {
        match (self.integer(left), self.integer(right)) {
            (Some(left), Some(right)) => Ok(Some(compare_integers(&left, &right))),
            (Some(integer), None) => Ok(self
                .number(right)?
                .and_then(|number| compare_integer_float(&integer, number))),
            (None, Some(integer)) => Ok(self
                .number(left)?
                .and_then(|number| compare_integer_float(&integer, number).map(Ordering::reverse))),
            (None, None) => {
                let (left, right) = (self.number(left)?, self.number(right)?);
                Ok(left
                    .zip(right)
                    .and_then(|(left, right)| left.partial_cmp(&right)))
            }
        }
    }
    fn positive(&self, value: &Value) -> Result<bool, Error> {
        Ok(self
            .number(value)?
            .is_some_and(|number| number.is_finite() && number > 0.0))
    }
    fn numeric_repr(&self, value: &Value) -> String {
        if let Value::Number(number) = value
            && number.is_f64()
            && let Some(number) = number.as_f64()
        {
            let absolute = number.abs();
            if absolute != 0.0 && !(1e-4..1e16).contains(&absolute) {
                let scientific = format!("{number:e}");
                if let Some((mantissa, exponent)) = scientific.split_once('e')
                    && let Ok(exponent) = exponent.parse::<i32>()
                {
                    return format!("{mantissa}e{exponent:+03}");
                }
            }
        }
        value
            .get(&self.numeric_tag)
            .and_then(Value::as_str)
            .map_or_else(|| value.to_string(), str::to_owned)
    }
}

/// Replace number tokens only, never contents of JSON strings.
fn python_numbers(text: &str, tag: &str) -> String {
    let bytes = text.as_bytes();
    let mut output = String::new();
    let mut start = 0;
    let mut index = 0;
    let number_pattern =
        regex::Regex::new(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$");
    while index < bytes.len() {
        if bytes[index] == b'"' {
            index += 1;
            while index < bytes.len() {
                match bytes[index] {
                    b'\\' => index = (index + 2).min(bytes.len()),
                    b'"' => {
                        index += 1;
                        break;
                    }
                    _ => index += 1,
                }
            }
            continue;
        }
        if bytes[index].is_ascii_digit() || matches!(bytes[index], b'-' | b'N' | b'I') {
            let begin = index;
            while index < bytes.len()
                && !matches!(
                    bytes[index],
                    b',' | b']' | b'}' | b':' | b' ' | b'\n' | b'\r' | b'\t'
                )
            {
                index += 1;
            }
            let token = &text[begin..index];
            if token == "-0" {
                output.push_str(&text[start..begin]);
                output.push('0');
                start = index;
                continue;
            }
            let special = matches!(token, "NaN" | "Infinity" | "-Infinity");
            let numeric = number_pattern
                .as_ref()
                .is_ok_and(|pattern| pattern.is_match(token));
            let big = numeric
                && !token.contains(['.', 'e', 'E'])
                && token.parse::<i64>().is_err()
                && token.parse::<u64>().is_err();
            let overflow_float = numeric
                && token.contains(['.', 'e', 'E'])
                && token.parse::<f64>().is_ok_and(|n| !n.is_finite());
            if special || big || overflow_float {
                output.push_str(&text[start..begin]);
                output.push_str(&json!({tag: token}).to_string());
                start = index;
            }
        } else {
            index += 1;
        }
    }
    output.push_str(&text[start..]);
    output
}

fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().is_some_and(|v| v != 0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

fn compare_integers(left: &str, right: &str) -> Ordering {
    let negative_left = left.starts_with('-');
    let negative_right = right.starts_with('-');
    if negative_left != negative_right {
        return if negative_left {
            Ordering::Less
        } else {
            Ordering::Greater
        };
    }
    let (left, right) = (left.trim_start_matches('-'), right.trim_start_matches('-'));
    let order = left.len().cmp(&right.len()).then_with(|| left.cmp(right));
    if negative_left {
        order.reverse()
    } else {
        order
    }
}

fn compare_integer_float(integer: &str, number: f64) -> Option<Ordering> {
    if number.is_nan() {
        return None;
    }
    if number == f64::INFINITY {
        return Some(Ordering::Less);
    }
    if number == f64::NEG_INFINITY {
        return Some(Ordering::Greater);
    }
    let truncated = number.trunc();
    let token = if truncated == 0.0 {
        "0".to_owned()
    } else {
        format!("{truncated:.0}")
    };
    let order = compare_integers(integer, &token);
    Some(if order == Ordering::Equal {
        if number.fract() > 0.0 {
            Ordering::Less
        } else if number.fract() < 0.0 {
            Ordering::Greater
        } else {
            Ordering::Equal
        }
    } else {
        order
    })
}
/// Syntax-only scan supplies CPython JSON diagnostics before serde builds values.
struct JsonSyntax {
    chars: Vec<char>,
    index: usize,
    depth: usize,
    in_verifiers: bool,
    verifier_order: Vec<String>,
}
impl JsonSyntax {
    fn validate(text: &str) -> Result<Vec<String>, Error> {
        let mut parser = Self {
            chars: text.chars().collect(),
            index: 0,
            depth: 0,
            in_verifiers: false,
            verifier_order: Vec::new(),
        };
        if parser.chars.first() == Some(&'\u{feff}') {
            return Err(parser.error("Unexpected UTF-8 BOM (decode using utf-8-sig)", 0));
        }
        parser.space();
        parser.value()?;
        parser.space();
        if parser.index != parser.chars.len() {
            return Err(parser.error("Extra data", parser.index));
        }
        Ok(parser.verifier_order)
    }
    fn error(&self, message: &str, index: usize) -> Error {
        let prefix = &self.chars[..index.min(self.chars.len())];
        let line = 1 + prefix.iter().filter(|c| **c == '\n').count();
        let column = prefix
            .iter()
            .rposition(|c| *c == '\n')
            .map_or(index + 1, |last| index - last);
        Error::Syntax(format!(
            "{message}: line {line} column {column} (char {index})"
        ))
    }
    fn peek(&self) -> Option<char> {
        self.chars.get(self.index).copied()
    }
    fn space(&mut self) {
        while self
            .peek()
            .is_some_and(|c| matches!(c, ' ' | '\n' | '\r' | '\t'))
        {
            self.index += 1;
        }
    }
    fn take(&mut self, literal: &str) -> bool {
        let literal: Vec<char> = literal.chars().collect();
        if self.chars[self.index..].starts_with(&literal) {
            self.index += literal.len();
            true
        } else {
            false
        }
    }
    fn value(&mut self) -> Result<(), Error> {
        match self.peek() {
            Some('"') => self.string(),
            Some('{') => self.container(true),
            Some('[') => self.container(false),
            _ => {
                if self.take("null")
                    || self.take("true")
                    || self.take("false")
                    || self.take("NaN")
                    || self.take("Infinity")
                    || self.take("-Infinity")
                {
                    return Ok(());
                }
                let start = self.index;
                if self.peek() == Some('-') {
                    self.index += 1;
                }
                match self.peek() {
                    Some('0') => self.index += 1,
                    Some('1'..='9') => {
                        self.index += 1;
                        while self.peek().is_some_and(|c| c.is_ascii_digit()) {
                            self.index += 1;
                        }
                    }
                    _ => {
                        self.index = start;
                        return Err(self.error("Expecting value", start));
                    }
                }
                if self.peek() == Some('.')
                    && self
                        .chars
                        .get(self.index + 1)
                        .is_some_and(|c| c.is_ascii_digit())
                {
                    self.index += 2;
                    while self.peek().is_some_and(|c| c.is_ascii_digit()) {
                        self.index += 1;
                    }
                }
                if self.peek().is_some_and(|c| c == 'e' || c == 'E') {
                    let exponent = self.index;
                    self.index += 1;
                    if self.peek().is_some_and(|c| c == '+' || c == '-') {
                        self.index += 1;
                    }
                    let digits = self.index;
                    while self.peek().is_some_and(|c| c.is_ascii_digit()) {
                        self.index += 1;
                    }
                    if self.index == digits {
                        self.index = exponent;
                    }
                }
                Ok(())
            }
        }
    }
    fn string(&mut self) -> Result<(), Error> {
        let start = self.index;
        self.index += 1;
        while let Some(c) = self.peek() {
            match c {
                '"' => {
                    self.index += 1;
                    return Ok(());
                }
                '\\' => {
                    let slash = self.index;
                    self.index += 1;
                    match self.peek() {
                        Some('"' | '\\' | '/' | 'b' | 'f' | 'n' | 'r' | 't') => self.index += 1,
                        Some('u') => {
                            let escape = self.index;
                            if self
                                .chars
                                .get(escape + 1..escape + 5)
                                .is_none_or(|digits| !digits.iter().all(char::is_ascii_hexdigit))
                            {
                                return Err(self.error("Invalid \\uXXXX escape", escape));
                            }
                            self.index += 5;
                        }
                        Some(_) => return Err(self.error("Invalid \\escape", slash)),
                        None => return Err(self.error("Unterminated string starting at", start)),
                    }
                }
                c if c < '\u{20}' => {
                    return Err(self.error("Invalid control character at", self.index));
                }
                _ => self.index += 1,
            }
        }
        Err(self.error("Unterminated string starting at", start))
    }
    fn container(&mut self, object: bool) -> Result<(), Error> {
        if self.depth >= 64 {
            return Err(Error::Depth);
        }
        self.depth += 1;
        let result = if object { self.object() } else { self.array() };
        self.depth -= 1;
        result
    }
    fn object(&mut self) -> Result<(), Error> {
        self.index += 1;
        self.space();
        if self.peek() == Some('}') {
            self.index += 1;
            return Ok(());
        }
        loop {
            if self.peek() != Some('"') {
                return Err(self.error(
                    "Expecting property name enclosed in double quotes",
                    self.index,
                ));
            }
            let start = self.index;
            self.string()?;
            let key: String =
                serde_json::from_str(&self.chars[start..self.index].iter().collect::<String>())
                    .map_err(Error::Json)?;
            if self.depth == 2 && self.in_verifiers && !self.verifier_order.contains(&key) {
                self.verifier_order.push(key.clone());
            }
            self.space();
            if self.peek() != Some(':') {
                return Err(self.error("Expecting ':' delimiter", self.index));
            }
            self.index += 1;
            self.space();
            if self.depth == 1 && key == "verifiers" {
                self.verifier_order.clear();
                self.in_verifiers = true;
            }
            self.value()?;
            if self.depth == 1 {
                self.in_verifiers = false;
            }
            self.space();
            match self.peek() {
                Some('}') => {
                    self.index += 1;
                    return Ok(());
                }
                Some(',') => {
                    self.index += 1;
                    self.space();
                }
                _ => return Err(self.error("Expecting ',' delimiter", self.index)),
            }
        }
    }
    fn array(&mut self) -> Result<(), Error> {
        self.index += 1;
        self.space();
        if self.peek() == Some(']') {
            self.index += 1;
            return Ok(());
        }
        loop {
            self.value()?;
            self.space();
            match self.peek() {
                Some(']') => {
                    self.index += 1;
                    return Ok(());
                }
                Some(',') => {
                    self.index += 1;
                    self.space();
                }
                _ => return Err(self.error("Expecting ',' delimiter", self.index)),
            }
        }
    }
}

fn python_unicode_error(error: &std::string::FromUtf8Error) -> String {
    let utf8 = error.utf8_error();
    let start = utf8.valid_up_to();
    let length = utf8.error_len().unwrap_or(error.as_bytes().len() - start);
    let reason = match utf8.error_len() {
        None => "unexpected end of data",
        Some(_) if matches!(error.as_bytes()[start], 0xc2..=0xf4) => "invalid continuation byte",
        Some(_) => "invalid start byte",
    };
    if length == 1 {
        format!(
            "'utf-8' codec can't decode byte 0x{:02x} in position {start}: {reason}",
            error.as_bytes()[start]
        )
    } else {
        format!(
            "'utf-8' codec can't decode bytes in position {start}-{}: {reason}",
            start + length - 1
        )
    }
}
