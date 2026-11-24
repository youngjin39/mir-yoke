//! Compact CPython JSON; omission applies only to the top-level mapping.
use serde_json::Value;

#[path = "../python_float.rs"]
mod float;
pub use float::{FloatError, python_float};

pub fn canonical_json(value: &Value, omit: Option<&[&str]>) -> String {
    canonical_json_with_numbers(value, omit, "")
}
/// Extended numbers use LocalConfig's collision-free numeric tag and original lexemes.
pub fn canonical_json_with_numbers(value: &Value, omit: Option<&[&str]>, tag: &str) -> String {
    let mut value = value.clone();
    if let Value::Object(fields) = &mut value {
        for key in omit.unwrap_or(&["signature"]) {
            fields.remove(*key);
        }
    }
    render(&value, tag)
}
fn render(value: &Value, tag: &str) -> String {
    match value {
        Value::Object(fields)
            if !tag.is_empty()
                && fields.len() == 1
                && fields.get(tag).is_some_and(Value::is_string) =>
        {
            value[tag].as_str().unwrap_or_default().to_owned()
        }
        Value::Object(fields) => {
            let items = fields
                .iter()
                .map(|(k, v)| format!("{}:{}", Value::String(k.clone()), render(v, tag)));
            format!("{{{}}}", join(items))
        }
        Value::Array(values) => format!("[{}]", join(values.iter().map(|v| render(v, tag)))),
        Value::Number(n) if n.is_f64() => n
            .as_f64()
            .and_then(|n| python_float(n).ok())
            .unwrap_or_else(|| n.to_string()),
        _ => value.to_string(),
    }
}
fn join(items: impl Iterator<Item = String>) -> String {
    items.collect::<Vec<_>>().join(",")
}
