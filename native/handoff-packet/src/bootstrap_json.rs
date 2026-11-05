//! jq 1.7 sorted compact hook JSON. RawValue preserves decimal precision and
//! scale (1.0, 1E+2, large integers), which Value's f64 conversion would lose.
use serde_json::value::RawValue;
use std::collections::BTreeMap;

type Object = BTreeMap<String, Box<RawValue>>;

fn decimal(raw: &str) -> Option<String> {
    let (sign, raw) = raw.strip_prefix('-').map_or(("", raw), |s| ("-", s));
    let (coefficient, exponent) = if let Some(i) = raw.find(['e', 'E']) {
        (&raw[..i], raw[i + 1..].parse::<i64>().ok()?)
    } else {
        (raw, 0)
    };
    let scale = coefficient.split_once('.').map_or(0, |(_, f)| f.len());
    let exponent = exponent.checked_sub(i64::try_from(scale).ok()?)?;
    let digits = coefficient.replace('.', "");
    let digits = digits.trim_start_matches('0');
    let digits = if digits.is_empty() { "0" } else { digits };
    let length = i64::try_from(digits.len()).ok()?;
    let adjusted = exponent.checked_add(length)?.checked_sub(1)?;
    let number = if exponent <= 0 && adjusted >= -6 {
        let point = length.checked_add(exponent)?;
        if point <= 0 {
            format!("0.{}{}", "0".repeat(usize::try_from(-point).ok()?), digits)
        } else if point < length {
            let point = usize::try_from(point).ok()?;
            format!("{}.{}", &digits[..point], &digits[point..])
        } else {
            digits.to_string()
        }
    } else {
        let fraction = if digits.len() > 1 {
            format!(".{}", &digits[1..])
        } else {
            String::new()
        };
        format!("{}{fraction}E{adjusted:+}", &digits[..1])
    };
    Some(format!("{sign}{number}"))
}
fn canonical(value: &RawValue) -> Option<String> {
    let raw = value.get();
    match raw.as_bytes().first()? {
        b'{' => {
            let object: Object = serde_json::from_str(raw).ok()?;
            let mut fields = Vec::new();
            for (key, value) in object {
                fields.push(format!(
                    "{}:{}",
                    serde_json::to_string(&key).ok()?,
                    canonical(&value)?
                ));
            }
            Some(format!("{{{}}}", fields.join(",")))
        }
        b'[' => {
            let array: Vec<Box<RawValue>> = serde_json::from_str(raw).ok()?;
            let elements: Option<Vec<_>> = array.iter().map(|v| canonical(v)).collect();
            Some(format!("[{}]", elements?.join(",")))
        }
        b'"' => {
            let text: String = serde_json::from_str(raw).ok()?;
            serde_json::to_string(&text).ok()
        }
        b't' | b'f' | b'n' => Some(raw.into()),
        _ => decimal(raw),
    }
}
pub fn hook_hash(bytes: &[u8]) -> Option<String> {
    let settings: Object = serde_json::from_slice(bytes).ok()?;
    let hooks = settings.get("hooks")?;
    let object: Object = serde_json::from_str(hooks.get()).ok()?;
    if object.is_empty() {
        return None;
    }
    let canonical = format!("{{\"hooks\":{}}}\n", canonical(hooks)?).replace('\u{7f}', "\\u007f");
    Some(crate::digest::sha256(canonical.as_bytes()))
}
