//! Task-blind repository identity and the existing intent-conflict advisory.

use serde::{
    Deserialize, Deserializer,
    de::{MapAccess, SeqAccess, Visitor},
};
use std::{fmt, path::Path, sync::OnceLock};

// A vector retains source map order, including gates and Python container repr.
#[derive(Debug)]
enum Value {
    Null,
    Bool(bool),
    Int(String),
    Float(f64),
    String(String),
    List(Vec<Value>),
    Map(Vec<(String, Value)>),
    Date(toml::value::Datetime),
}

impl<'de> Deserialize<'de> for Value {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Value;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("a TOML or JSON value")
            }
            fn visit_unit<E>(self) -> Result<Value, E> {
                Ok(Value::Null)
            }
            fn visit_none<E>(self) -> Result<Value, E> {
                Ok(Value::Null)
            }
            fn visit_bool<E>(self, v: bool) -> Result<Value, E> {
                Ok(Value::Bool(v))
            }
            fn visit_i64<E>(self, v: i64) -> Result<Value, E> {
                Ok(Value::Int(v.to_string()))
            }
            fn visit_u64<E>(self, v: u64) -> Result<Value, E> {
                Ok(Value::Int(v.to_string()))
            }
            fn visit_f64<E>(self, v: f64) -> Result<Value, E> {
                Ok(Value::Float(v))
            }
            fn visit_str<E>(self, v: &str) -> Result<Value, E> {
                Ok(Value::String(v.into()))
            }
            fn visit_string<E>(self, v: String) -> Result<Value, E> {
                Ok(Value::String(v))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> Result<Value, A::Error> {
                let mut values = Vec::new();
                while let Some(v) = a.next_element()? {
                    values.push(v);
                }
                Ok(Value::List(values))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> Result<Value, A::Error> {
                let mut fields = Vec::new();
                while let Some((k, v)) = a.next_entry::<String, Value>()? {
                    // Python JSON keeps a duplicate key's original insertion slot.
                    if let Some((_, old)) = fields.iter_mut().find(|(key, _)| key == &k) {
                        *old = v;
                    } else {
                        fields.push((k, v));
                    }
                }
                Ok(Value::Map(fields))
            }
        }
        d.deserialize_any(V)
    }
}

fn parse_toml(text: &str) -> Option<Value> {
    let mut value = Value::deserialize(toml::Deserializer::new(text)).ok()?;
    fn dates(v: &mut Value) {
        match v {
            Value::Map(fields)
                if fields.len() == 1 && fields[0].0 == "$__toml_private_datetime" =>
            {
                if let Value::String(s) = &fields[0].1
                    && let Ok(date) = s.parse()
                {
                    *v = Value::Date(date);
                }
            }
            Value::Map(fields) => fields.iter_mut().for_each(|(_, v)| dates(v)),
            Value::List(values) => values.iter_mut().for_each(dates),
            _ => (),
        }
    }
    dates(&mut value);
    Some(value)
}

fn parse_json(text: &str) -> Option<Value> {
    // Python accepts these three nonstandard numeric literals. Use an otherwise
    // absent numeric spelling for NaN, so quoted or escaped strings never collide.
    let mut nan = "1e999999".to_string();
    while text.contains(&nan) {
        nan.push('9');
    }
    let mut normalized = String::with_capacity(text.len());
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let start = i;
        if bytes[i] == b'"' {
            i += 1;
            while i < bytes.len() {
                match bytes[i] {
                    b'\\' => i = (i + 2).min(bytes.len()),
                    b'"' => {
                        i += 1;
                        break;
                    }
                    _ => i += 1,
                }
            }
            normalized.push_str(&text[start..i]);
        } else if b"[]{}:, \t\r\n".contains(&bytes[i]) {
            normalized.push(char::from(bytes[i]));
            i += 1;
        } else {
            while i < bytes.len() && !b"[]{}:, \t\r\n\"".contains(&bytes[i]) {
                i += 1;
            }
            normalized.push_str(match &text[start..i] {
                "NaN" => &nan,
                "Infinity" => "1e9999",
                "-Infinity" => "-1e9999",
                token => token,
            });
        }
    }
    parse_json_strict(&normalized, &nan)
}

fn parse_json_strict(text: &str, nan: &str) -> Option<Value> {
    // Raw elements preserve Python's arbitrary precision integer semantics.
    struct Json<'a> {
        nan: &'a str,
    }
    impl<'de> serde::de::DeserializeSeed<'de> for Json<'_> {
        type Value = Value;
        fn deserialize<D: Deserializer<'de>>(self, d: D) -> Result<Value, D::Error> {
            struct J<'a> {
                nan: &'a str,
            }
            impl<'de> Visitor<'de> for J<'_> {
                type Value = Value;
                fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                    f.write_str("a JSON container")
                }
                fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> Result<Value, A::Error> {
                    let mut values = Vec::new();
                    while let Some(raw) = a.next_element::<Box<serde_json::value::RawValue>>()? {
                        values.push(
                            parse_json_strict(raw.get(), self.nan)
                                .ok_or_else(|| serde::de::Error::custom("invalid JSON element"))?,
                        );
                    }
                    Ok(Value::List(values))
                }
                fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> Result<Value, A::Error> {
                    let mut fields: Vec<(String, Value)> = Vec::new();
                    while let Some((key, raw)) =
                        a.next_entry::<String, Box<serde_json::value::RawValue>>()?
                    {
                        let value = parse_json_strict(raw.get(), self.nan)
                            .ok_or_else(|| serde::de::Error::custom("invalid JSON field"))?;
                        if let Some((_, old)) = fields.iter_mut().find(|(k, _)| k == &key) {
                            *old = value;
                        } else {
                            fields.push((key, value));
                        }
                    }
                    Ok(Value::Map(fields))
                }
            }
            d.deserialize_any(J { nan: self.nan })
        }
    }
    let raw: Box<serde_json::value::RawValue> = serde_json::from_str(text).ok()?;
    let text = raw.get();
    if text.starts_with(['{', '[']) {
        return serde::de::DeserializeSeed::deserialize(
            Json { nan },
            &mut serde_json::Deserializer::from_str(text),
        )
        .ok();
    }
    if text.starts_with(|c: char| c == '-' || c.is_ascii_digit()) {
        if text == nan {
            return Some(Value::Float(f64::NAN));
        }
        if text.contains(['.', 'e', 'E']) {
            return text.parse().ok().map(Value::Float);
        }
        return Some(Value::Int(if text == "-0" { "0" } else { text }.into()));
    }
    serde_json::from_str(text).ok()
}
fn get<'a>(value: &'a Value, key: &str) -> Option<&'a Value> {
    match value {
        Value::Map(fields) => fields.iter().find(|(k, _)| k == key).map(|(_, v)| v),
        _ => None,
    }
}
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(v) => *v,
        Value::Int(v) => v != "0",
        Value::Float(v) => *v != 0.0,
        Value::String(v) => !v.is_empty(),
        Value::List(v) => !v.is_empty(),
        Value::Map(v) => !v.is_empty(),
        Value::Date(_) => true,
    }
}
fn whitespace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}
fn strip(s: &str) -> &str {
    s.trim_matches(whitespace)
}
fn repr(s: &str) -> String {
    static NONPRINTABLE: OnceLock<Result<regex::Regex, regex::Error>> = OnceLock::new();
    let nonprintable = NONPRINTABLE
        .get_or_init(|| regex::Regex::new(r"[\p{C}\p{Z}]"))
        .as_ref();
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = quote.to_string();
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if c != ' '
                && nonprintable.is_ok_and(|re| re.is_match(c.encode_utf8(&mut [0; 4]))) =>
            {
                let n = c as u32;
                out.push_str(&if n <= 255 {
                    format!("\\x{n:02x}")
                } else if n <= 65535 {
                    format!("\\u{n:04x}")
                } else {
                    format!("\\U{n:08x}")
                });
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}
fn float(v: f64) -> String {
    if v.is_nan() {
        return "nan".into();
    }
    if v.is_infinite() {
        return if v.is_sign_negative() { "-inf" } else { "inf" }.into();
    }
    let s = format!("{v:?}");
    if let Some((m, e)) = s.split_once('e') {
        let Ok(e) = e.parse::<i32>() else {
            return s;
        };
        format!("{m}e{}{e:02}", if e < 0 { "-" } else { "+" }, e = e.abs())
    } else {
        s
    }
}
fn date_string(d: &toml::value::Datetime, nested: bool) -> String {
    if !nested {
        let mut out = d
            .date
            .map(|v| format!("{:04}-{:02}-{:02}", v.year, v.month, v.day))
            .unwrap_or_default();
        if let Some(t) = d.time {
            if d.date.is_some() {
                out.push(' ');
            }
            out.push_str(&format!("{:02}:{:02}:{:02}", t.hour, t.minute, t.second));
            if t.nanosecond / 1000 != 0 {
                out.push_str(&format!(".{:06}", t.nanosecond / 1000));
            }
        }
        if let Some(o) = d.offset {
            let m = match o {
                toml::value::Offset::Z => 0,
                toml::value::Offset::Custom { minutes } => minutes,
            };
            out.push_str(&format!(
                "{}{:02}:{:02}",
                if m < 0 { '-' } else { '+' },
                m.abs() / 60,
                m.abs() % 60
            ));
        }
        return out;
    }
    let mut fields = Vec::new();
    if let Some(d) = d.date {
        fields.extend([d.year.to_string(), d.month.to_string(), d.day.to_string()]);
    }
    if let Some(t) = d.time {
        fields.extend([t.hour.to_string(), t.minute.to_string()]);
        if d.date.is_some() || t.second != 0 || t.nanosecond / 1000 != 0 {
            fields.push(t.second.to_string());
        }
        if t.nanosecond / 1000 != 0 {
            fields.push((t.nanosecond / 1000).to_string());
        }
    }
    if let Some(o) = d.offset {
        let m = match o {
            toml::value::Offset::Z => 0,
            toml::value::Offset::Custom { minutes } => minutes,
        };
        let tz = if m == 0 {
            "datetime.timezone.utc".into()
        } else {
            let seconds = i32::from(m) * 60;
            if seconds < 0 {
                format!(
                    "datetime.timezone(datetime.timedelta(days=-1, seconds={}))",
                    86400 + seconds
                )
            } else {
                format!("datetime.timezone(datetime.timedelta(seconds={seconds}))")
            }
        };
        fields.push(format!("tzinfo={tz}"));
    }
    let kind = match (d.date.is_some(), d.time.is_some()) {
        (true, true) => "datetime",
        (true, false) => "date",
        _ => "time",
    };
    format!("datetime.{kind}({})", fields.join(", "))
}
fn pystr(v: &Value, nested: bool) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(v) => if *v { "True" } else { "False" }.into(),
        Value::Int(v) => v.clone(),
        Value::Float(v) => float(*v),
        Value::String(v) => {
            if nested {
                repr(v)
            } else {
                v.clone()
            }
        }
        Value::Date(v) => date_string(v, nested),
        Value::List(v) => format!(
            "[{}]",
            v.iter()
                .map(|v| pystr(v, true))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Map(v) => format!(
            "{{{}}}",
            v.iter()
                .map(|(k, v)| format!("{}: {}", repr(k), pystr(v, true)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}
fn strings(v: Option<&Value>, key: &str) -> Vec<String> {
    match v.and_then(|v| get(v, key)) {
        Some(Value::List(items)) => items
            .iter()
            .map(|v| strip(&pystr(v, false)).to_string())
            .filter(|s| !s.is_empty())
            .collect(),
        _ => Vec::new(),
    }
}
fn values(v: Vec<String>) -> String {
    if v.is_empty() {
        "none".into()
    } else {
        v.join(", ")
    }
}
fn scalar(v: Option<&Value>, key: &str) -> String {
    match v.and_then(|v| get(v, key)) {
        None | Some(Value::Null | Value::List(_) | Value::Map(_)) => "unspecified".into(),
        Some(v) => {
            let s = pystr(v, false);
            if strip(&s).is_empty() {
                "unspecified".into()
            } else {
                strip(&s).into()
            }
        }
    }
}
fn or_string(v: Option<&Value>, default: &str) -> String {
    v.filter(|v| truthy(v))
        .map(|v| pystr(v, false))
        .unwrap_or_else(|| default.into())
}
fn advisory(intent: &Value) -> Option<String> {
    let normalize = |v| {
        or_string(v, "")
            .split(whitespace)
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" ")
    };
    let current = normalize(get(intent, "goal"));
    if current.is_empty() {
        return None;
    }
    let Value::List(history) = get(intent, "history")? else {
        return None;
    };
    let prior = history.iter().rev().find(|v| matches!(v, Value::Map(_)))?;
    if matches!(get(prior, "completed"), Some(Value::Bool(true))) {
        return None;
    }
    if ["complete", "completed", "done", "closed"].contains(
        &strip(&or_string(get(prior, "status"), ""))
            .to_lowercase()
            .as_str(),
    ) {
        return None;
    }
    let old = normalize(get(prior, "goal"));
    if old.is_empty() || old == current {
        return None;
    }
    let compact = |s: String| {
        if s.chars().count() <= 160 {
            s
        } else {
            format!("{}…", s.chars().take(159).collect::<String>())
        }
    };
    Some(format!(
        "intent_conflict_advisory: prior={}; current={}; confirm supersede or merge",
        compact(old),
        compact(current)
    ))
}
fn render(profile: Option<&Value>, intent: Option<&Value>) -> String {
    let mut lines = vec!["=== REPOSITORY CONTEXT ===".to_string()];
    if let Some(profile) = profile {
        let repo = get(profile, "repo");
        let paths = get(profile, "paths");
        let boundaries = get(profile, "boundaries");
        let slug = or_string(repo.and_then(|r| get(r, "slug")), "unknown");
        let name = or_string(repo.and_then(|r| get(r, "display_name")), &slug);
        let kind = or_string(repo.and_then(|r| get(r, "repository_type")), "unknown");
        lines.push(format!("repository: {name} ({slug}, {kind})"));
        for key in ["protected_paths", "generated_paths"] {
            lines.push(format!("{key}: {}", values(strings(paths, key))));
        }
        let preserve = [
            "skills",
            "claude_sections",
            "agent_memory_paths",
            "commands",
            "extra_docs",
        ]
        .iter()
        .filter_map(|key| {
            let v = strings(get(profile, "preserve"), key);
            if v.is_empty() {
                None
            } else {
                Some(format!("{key}={}", values(v)))
            }
        })
        .collect::<Vec<_>>();
        lines.push(format!(
            "preserve: {}",
            if preserve.is_empty() {
                "none".into()
            } else {
                preserve.join("; ")
            }
        ));
        for (label, key) in [
            ("secret_paths", "secrets"),
            ("live_runtime_boundaries", "live_runtime"),
            ("external_services", "external_services"),
        ] {
            lines.push(format!("{label}: {}", values(strings(boundaries, key))));
        }
        for key in ["data_sensitivity", "release_window"] {
            lines.push(format!("{key}: {}", scalar(boundaries, key)));
        }
        let gates = match get(profile, "gates") {
            Some(Value::Map(v)) => v
                .iter()
                .filter(|(_, v)| matches!(v, Value::Bool(true)))
                .map(|(k, _)| k.clone())
                .collect(),
            _ => Vec::new(),
        };
        lines.push(format!("required_gates: {}", values(gates)));
        lines.push("source: .mir/repo-profile.toml".into());
    } else {
        lines.extend([
            "repository_profile: unavailable".into(),
            "mandatory_safety: inspect repository-local instructions before mutation".into(),
        ]);
    }
    if let Some(a) = intent.and_then(advisory) {
        lines.push(a);
    }
    lines.push("=== END REPOSITORY CONTEXT ===".into());
    lines.join("\n")
}

pub fn build(project: &Path) -> String {
    let profile = std::fs::read_to_string(project.join(".mir/repo-profile.toml"))
        .ok()
        .and_then(|s| parse_toml(&s));
    let intent = std::fs::read_to_string(project.join("tasks/intent.json"))
        .ok()
        .and_then(|s| parse_json(&s));
    render(profile.as_ref(), intent.as_ref())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_profile() {
        let project = tempfile::tempdir().unwrap();
        assert_eq!(
            build(project.path()),
            "=== REPOSITORY CONTEXT ===\nrepository_profile: unavailable\nmandatory_safety: inspect repository-local instructions before mutation\n=== END REPOSITORY CONTEXT ==="
        );
    }

    #[test]
    fn python_values_and_order() {
        let profile = parse_toml("[repo]\nslug = false\ndisplay_name = [true, { z = 2, a = 'x' }]\nrepository_type = 42\n[paths]\nprotected_paths = [false, 0, '', '  ', ['x'], 1e-7, 1979-05-27]\n[boundaries]\ndata_sensitivity = false\nrelease_window = 1979-05-27T07:32:00.123456789Z\n[gates]\nz = true\nignored = 1\na = true\n").unwrap();
        let text = render(Some(&profile), None);
        assert!(text.contains("repository: [True, {'z': 2, 'a': 'x'}] (unknown, 42)"));
        assert!(text.contains("protected_paths: False, 0, ['x'], 1e-07, 1979-05-27"));
        assert!(text.contains("data_sensitivity: False"));
        assert!(text.contains("release_window: 1979-05-27 07:32:00.123456+00:00"));
        assert!(text.contains("required_gates: z, a"));
    }

    #[test]
    fn unicode_advisory_and_python_truthiness() {
        let value = parse_json(
            r#"{"goal":{"z":true,"a":null},"history":[{"goal":" old\u001cgoal ","completed":1}]}"#,
        )
        .unwrap();
        assert_eq!(
            advisory(&value).unwrap(),
            "intent_conflict_advisory: prior=old goal; current={'z': True, 'a': None}; confirm supersede or merge"
        );
        let value = parse_json(&format!(
            r#"{{"goal":"{}","history":[{{"goal":"old"}}]}}"#,
            "\u{d55c}".repeat(161)
        ))
        .unwrap();
        assert!(
            advisory(&value)
                .unwrap()
                .contains(&format!("current={}…;", "\u{d55c}".repeat(159)))
        );
        let value = parse_json(
            r#"{"goal":99999999999999999999999999999999999,"history":[{"goal":"old"}]}"#,
        )
        .unwrap();
        assert!(
            advisory(&value)
                .unwrap()
                .contains("current=99999999999999999999999999999999999;")
        );
    }

    #[test]
    fn json_nonfinite_literals_preserve_quoted_strings() {
        let value = parse_json(r#"{"goal":[NaN,Infinity,-Infinity,"NaN","Infinity","-Infinity","1e999999","\u0031e9999999"],"history":[{"goal":"old"}]}"#).unwrap();
        assert_eq!(
            advisory(&value).unwrap(),
            "intent_conflict_advisory: prior=old; current=[nan, inf, -inf, 'NaN', 'Infinity', '-Infinity', '1e999999', '1e9999999']; confirm supersede or merge"
        );
        assert!(parse_json("[NaNgarbage]").is_none());
        assert!(parse_json("[+Infinity]").is_none());
        assert_eq!(pystr(&parse_json("NaN").unwrap(), false), "nan");
    }
}
