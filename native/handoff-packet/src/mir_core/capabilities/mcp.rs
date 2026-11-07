//! Closed operator-observed JSON evidence used by the capability CLI.
#![forbid(unsafe_code)]
use serde_json::Value;
use std::{collections::BTreeSet, fs, path::Path};

/// Read a JSON object, rejecting duplicate keys recursively.
/// The CLI translates both I/O and decoding failures into its evidence error.
pub fn closed_json(path: &Path) -> Option<Value> {
    closed_json_bytes(&fs::read(path).ok()?)
}

fn closed_json_bytes(bytes: &[u8]) -> Option<Value> {
    let value: Value = serde_json::from_slice(bytes).ok()?;
    if !value.is_object() {
        return None;
    }
    let mut objects = Vec::<BTreeSet<String>>::new();
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'{' => objects.push(Default::default()),
            b'}' => {
                objects.pop()?;
            }
            b'"' => {
                let start = i;
                i += 1;
                while i < bytes.len() && bytes[i] != b'"' {
                    if bytes[i] == b'\\' {
                        i += 1;
                    }
                    i += 1;
                }
                let end = i + 1;
                let mut next = end;
                while bytes.get(next).is_some_and(u8::is_ascii_whitespace) {
                    next += 1;
                }
                if bytes.get(next) == Some(&b':') {
                    let key = serde_json::from_slice(bytes.get(start..end)?).ok()?;
                    if !objects.last_mut()?.insert(key) {
                        return None;
                    }
                }
            }
            _ => {}
        }
        i += 1;
    }
    Some(value)
}
