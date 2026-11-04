use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value, json};
// Reject duplicate keys at every level, without derive/proc macros.
struct Closed(Value);
impl<'de> Deserialize<'de> for Closed {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Closed;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("JSON")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Closed, E> {
                Ok(Closed(json!(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Closed, E> {
                Ok(Closed(json!(v)))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Closed, E> {
                Ok(Closed(json!(v)))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Closed, E> {
                Ok(Closed(json!(v)))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Closed, E> {
                Ok(Closed(json!(v)))
            }
            fn visit_string<E: de::Error>(self, v: String) -> Result<Closed, E> {
                Ok(Closed(json!(v)))
            }
            fn visit_unit<E: de::Error>(self) -> Result<Closed, E> {
                Ok(Closed(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> Result<Closed, A::Error> {
                let mut values = Vec::new();
                while let Some(Closed(v)) = a.next_element()? {
                    values.push(v);
                }
                Ok(Closed(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> Result<Closed, A::Error> {
                let mut values = Map::new();
                while let Some((k, Closed(v))) = a.next_entry::<String, Closed>()? {
                    if values.contains_key(&k) {
                        return Err(de::Error::custom("duplicate key"));
                    }
                    values.insert(k, v);
                }
                Ok(Closed(Value::Object(values)))
            }
        }
        d.deserialize_any(V)
    }
}
fn bounded(v: &Value, depth: usize) -> bool {
    depth <= 32
        && match v {
            Value::String(s) => s.len() <= 4096,
            Value::Array(a) => a.iter().all(|v| bounded(v, depth + 1)),
            Value::Object(o) => o
                .iter()
                .all(|(k, v)| k.len() <= 4096 && depth < 32 && bounded(v, depth + 1)),
            _ => true,
        }
}
pub fn parse(raw: &[u8]) -> Result<Value, &'static str> {
    let raw = raw.strip_prefix(b"\xef\xbb\xbf").unwrap_or(raw);
    let s = std::str::from_utf8(raw).map_err(|_| "E_FORMAT")?;
    let (mut level, mut quoted, mut escaped) = (0_i32, false, false);
    for c in s.chars() {
        if quoted {
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                quoted = false;
            }
        } else if c == '"' {
            quoted = true;
        } else if c == '[' || c == '{' {
            level += 1;
            if level > 32 {
                return Err("E_LIMIT");
            }
        } else if c == ']' || c == '}' {
            level -= 1;
        }
    }
    let normalized = numbers(raw)?;
    let mut d = serde_json::Deserializer::from_slice(&normalized);
    let Closed(v) = Closed::deserialize(&mut d).map_err(|_| "E_FORMAT")?;
    d.end().map_err(|_| "E_FORMAT")?;
    if !bounded(&v, 0) {
        return Err("E_LIMIT");
    }
    Ok(v)
}

// Only integer IDs are serialized by the core. Tool arguments and child replies
// retain their original bytes. Represent other numbers by type for validation:
// Python admits arbitrary integers and overflowing float literals; serde's normal
// f64 decoder does not. Validate their grammar with arbitrary_precision first.
fn numbers(raw: &[u8]) -> Result<Vec<u8>, &'static str> {
    let mut out = Vec::new();
    let (mut i, mut quoted, mut escaped) = (0, false, false);
    while i < raw.len() {
        let c = raw[i];
        if quoted {
            out.push(c);
            if escaped {
                escaped = false;
            } else if c == b'\\' {
                escaped = true;
            } else if c == b'"' {
                quoted = false;
            }
            i += 1;
        } else if c == b'"' {
            quoted = true;
            out.push(c);
            i += 1;
        } else if c == b'-' || c.is_ascii_digit() {
            let start = i;
            i += 1;
            while i < raw.len() && matches!(raw[i], b'0'..=b'9' | b'.' | b'e' | b'E' | b'+' | b'-')
            {
                i += 1;
            }
            let token = std::str::from_utf8(&raw[start..i]).map_err(|_| "E_FORMAT")?;
            let _: serde_json::Number = serde_json::from_str(token).map_err(|_| "E_FORMAT")?;
            if token.contains(['.', 'e', 'E']) {
                out.extend_from_slice(b"0.0");
            } else if let Ok(n) = token.parse::<i64>() {
                out.extend_from_slice(n.to_string().as_bytes());
            } else {
                out.extend_from_slice(b"9007199254740992");
            }
        } else {
            out.push(c);
            i += 1;
        }
    }
    Ok(out)
}
