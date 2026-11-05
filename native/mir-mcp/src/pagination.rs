//! Stateless Python-compatible cursor encoding and bounded page selection.
use crate::{digest::sha256, wire};
use serde_json::{Value, json};
pub fn compact(v: &Value) -> Result<Vec<u8>, &'static str> {
    serde_json::to_vec(v).map_err(|_| "E_FORMAT")
}
const ALPHABET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
fn encode(raw: &[u8]) -> String {
    let mut out = String::new();
    for c in raw.chunks(3) {
        let a = c[0] as usize;
        let b = c.get(1).copied().unwrap_or(0) as usize;
        let d = c.get(2).copied().unwrap_or(0) as usize;
        out.push(ALPHABET[a >> 2] as char);
        out.push(ALPHABET[((a & 3) << 4) | (b >> 4)] as char);
        out.push(if c.len() > 1 {
            ALPHABET[((b & 15) << 2) | (d >> 6)] as char
        } else {
            '='
        });
        out.push(if c.len() > 2 {
            ALPHABET[d & 63] as char
        } else {
            '='
        });
    }
    out
}
fn decode(s: &str) -> Result<Vec<u8>, &'static str> {
    // Python b64decode(validate=True) also admits the standard alphabet.
    let mut out = Vec::new();
    let mut bits = 0u32;
    let mut n = 0;
    let mut padding = false;
    let mut pads = 0;
    for b in s.bytes() {
        if b == b'=' {
            padding = true;
            pads += 1;
            continue;
        }
        if padding {
            return Err("E_CURSOR");
        }
        let b = match b {
            b'+' => b'-',
            b'/' => b'_',
            _ => b,
        };
        let value = ALPHABET.iter().position(|&x| x == b).ok_or("E_CURSOR")? as u32;
        bits = (bits << 6) | value;
        n += 6;
        if n >= 8 {
            n -= 8;
            out.push((bits >> n) as u8);
        }
    }
    if n == 6 || (n > 0 && (!s.len().is_multiple_of(4) || pads != if n == 4 { 2 } else { 1 })) {
        return Err("E_CURSOR");
    }
    Ok(out)
}
pub fn binding(
    tool: &str,
    root: &str,
    args: &Value,
    sources: &Value,
    digests: &Value,
    contract: &[u8],
) -> Result<String, &'static str> {
    Ok(sha256(&compact(
        &json!({"tool":tool,"root":root,"args":args,"sources":sources,"source_digests":digests,"contract":sha256(contract)}),
    )?))
}
pub fn page(
    data: Value,
    args: &Value,
    binding: &str,
    git_error: Option<&str>,
    profile: &str,
) -> Result<Value, &'static str> {
    page_tool(data, args, binding, git_error, profile, &["sources"], true)
}
pub fn page_tool(
    mut data: Value,
    args: &Value,
    binding: &str,
    git_error: Option<&str>,
    profile: &str,
    keys: &[&str],
    handoff: bool,
) -> Result<Value, &'static str> {
    let offset = if let Some(cursor) = args.get("cursor") {
        let decoded =
            wire::parse(&decode(cursor.as_str().ok_or("E_CURSOR")?)?).map_err(|_| "E_CURSOR")?;
        if decoded
            .as_object()
            .is_none_or(|o| o.len() != 2 || !o.contains_key("h") || !o.contains_key("o"))
            || decoded["h"] != binding
        {
            return Err("E_CURSOR");
        }
        let n = decoded["o"].as_u64().filter(|&n| n > 0).ok_or("E_CURSOR")?;
        usize::try_from(n).map_err(|_| "E_CURSOR")?
    } else {
        0
    };
    let lists: Vec<Vec<Value>> = keys
        .iter()
        .map(|key| data[*key].as_array().cloned().ok_or("E_FORMAT"))
        .collect::<Result<_, _>>()?;
    let count = lists.iter().map(Vec::len).max().unwrap_or(0);
    if offset > 0 && offset >= count {
        return Err("E_CURSOR");
    }
    let mut end = (offset + args["page_size"].as_u64().unwrap_or(16) as usize).min(count);
    loop {
        for (key, list) in keys.iter().zip(&lists) {
            data[*key] = json!(&list[offset.min(list.len())..end.min(list.len())]);
        }
        // Keep original full-result unknowns; finalization adds page-local inventory.
        let mut page = data.clone();
        if handoff {
            let paths = args["paths"].as_array().ok_or("E_SCHEMA")?;
            crate::handoff::finalize(&mut page, &paths[offset..end]);
        }
        let cursor = if end < count {
            json!(encode(&compact(&json!({"h":binding,"o":end}))?))
        } else {
            Value::Null
        };
        let result = json!({"ok":git_error.is_none(),"data":page,"error":git_error.map(|code|json!({"code":code})),"next_cursor":cursor,"profile_protections":profile});
        if compact(&result)?.len() <= 15360 {
            return Ok(result);
        }
        if end - offset <= 1 {
            return Err("E_LIMIT");
        }
        end -= 1;
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn base64_vectors() {
        for (raw, expected) in [
            ("", ""),
            ("f", "Zg=="),
            ("fo", "Zm8="),
            ("foo", "Zm9v"),
            ("foobar", "Zm9vYmFy"),
        ] {
            assert_eq!(encode(raw.as_bytes()), expected);
            assert_eq!(decode(expected), Ok(raw.as_bytes().to_vec()));
        }
        for bad in ["a", "Zg", "Zg=", "Zg===", "Zm=v", " Zg=="] {
            assert!(decode(bad).is_err(), "{bad}");
        }
    }
    #[test]
    fn pages_shrink_and_indivisible_items_refuse() {
        let paths: Vec<Value> = (0..8).map(|i| json!(format!("file{i}"))).collect();
        let sources: Vec<Value> = paths.iter().map(|path|json!({"path":path,"sha256":"a".repeat(64),"revision":null,"payload":"x".repeat(3000)})).collect();
        let data = json!({"sources":sources,"unknowns":[]});
        let args = json!({"paths":paths,"page_size":8});
        let result = page(data, &args, "hash", None, "available");
        assert!(result.is_ok());
        if let Ok(result) = result {
            let len = result["data"]["sources"].as_array().map_or(0, Vec::len);
            assert!(len > 0 && len < 8);
            assert!(compact(&result).is_ok_and(|raw| raw.len() <= 15360));
            assert!(result["next_cursor"].is_string());
        }
        assert_eq!(
            page(
                json!({"sources":[{"payload":"x".repeat(20000)}],"unknowns":[]}),
                &json!({"paths":["file"]}),
                "hash",
                None,
                "available"
            ),
            Err("E_LIMIT")
        );
    }
}
