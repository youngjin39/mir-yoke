//! Compact CPython JSON; omission applies only to the top-level mapping.
use serde_json::Value;
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
// Shared with executor_query; preserve CPython exponent thresholds and .0.
#[derive(Debug)]
pub struct FloatError;
pub fn python_float(value: f64) -> Result<String, FloatError> {
    let encoded = serde_json::to_string(&value).map_err(|_| FloatError)?;
    let sign = if encoded.starts_with('-') { "-" } else { "" };
    let magnitude = encoded.trim_start_matches('-');
    let (mantissa, exponent) = magnitude.split_once(['e', 'E']).unwrap_or((magnitude, "0"));
    let decimal = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let all: String = mantissa.chars().filter(|c| *c != '.').collect();
    let Some(first) = all.find(|c| c != '0') else {
        return Ok(format!("{sign}0.0"));
    };
    let exponent = exponent.parse::<i32>().map_err(|_| FloatError)? + decimal - first as i32 - 1;
    let digits = all[first..].trim_end_matches('0');
    let decimal = (exponent + 1).max(0) as usize;
    let body = if !(-4..16).contains(&exponent) {
        let fraction = if digits.len() > 1 {
            format!(".{}", &digits[1..])
        } else {
            String::new()
        };
        format!("{}{fraction}e{exponent:+03}", &digits[..1])
    } else if exponent < 0 {
        format!("0.{}{}", "0".repeat((-exponent - 1) as usize), digits)
    } else if decimal >= digits.len() {
        format!("{digits}{}.0", "0".repeat(decimal - digits.len()))
    } else {
        format!("{}.{}", &digits[..decimal], &digits[decimal..])
    };
    Ok(format!("{sign}{body}"))
}
