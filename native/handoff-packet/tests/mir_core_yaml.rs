//! Frozen compose observations and marked diagnostics for bootstrap's YAML loads.
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::mir_core::yaml::{Input, Kind, Node, compose};
use serde_json::{Value, json};
use std::collections::BTreeMap;

fn base64(text: &str) -> Vec<u8> {
    let mut bits = 0u32;
    let mut count = 0;
    let mut out = Vec::new();
    for c in text.bytes().filter(|&c| c != b'=') {
        let n = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
            .iter()
            .position(|&x| x == c)
            .unwrap() as u32;
        bits = (bits << 6) | n;
        count += 6;
        if count >= 8 {
            count -= 8;
            out.push((bits >> count) as u8);
        }
    }
    out
}
fn tree(node: &Node, id: usize, seen: &mut BTreeMap<usize, usize>) -> Value {
    if let Some(index) = seen.get(&id) {
        return json!({"ref": index});
    }
    seen.insert(id, seen.len());
    let n = &node.arena[id];
    let mut v = json!({"tag": n.tag, "line": n.line, "column": n.column});
    match &n.kind {
        Kind::Scalar(text) => {
            v["kind"] = json!("scalar");
            v["style"] = json!(n.style.map(|c| c.to_string()));
            v["value"] = if text.chars().count() > 512 {
                json!({"len": text.chars().count(), "sha256": digest::sha256(text.as_bytes())})
            } else {
                json!(text)
            };
        }
        Kind::Sequence(items) => {
            v["kind"] = json!("sequence");
            v["items"] = items.iter().map(|&i| tree(node, i, seen)).collect();
        }
        Kind::Mapping(pairs) => {
            v["kind"] = json!("mapping");
            v["pairs"] = pairs
                .iter()
                .map(|&(k, v)| json!([tree(node, k, seen), tree(node, v, seen)]))
                .collect();
        }
    }
    v
}
fn ascii_json(value: &Value) -> String {
    let mut out = String::new();
    for c in serde_json::to_string(value).unwrap().chars() {
        if c.is_ascii() {
            out.push(c);
        } else {
            let mut buf = [0; 2];
            for u in c.encode_utf16(&mut buf) {
                out.push_str(&format!("\\u{u:04x}"));
            }
        }
    }
    out
}
fn json_depth(value: &Value) -> usize {
    let (mut deepest, mut stack) = (0, vec![(value, 1)]);
    while let Some((item, depth)) = stack.pop() {
        match item {
            Value::Array(items) => stack.extend(items.iter().map(|child| (child, depth + 1))),
            Value::Object(map) => stack.extend(map.values().map(|child| (child, depth + 1))),
            _ => continue,
        }
        deepest = deepest.max(depth);
    }
    deepest
}
#[test]
fn frozen_compose_records() {
    // Rows: [kind, earlier case name, prefix byte count, [[base64 suffix, repeat], ...]].
    let inputs: Value = serde_json::from_str(include_str!("yaml-inputs.json")).unwrap();
    let oracle: Value =
        serde_json::from_str(include_str!("fixtures/w2/yaml-compose.json")).unwrap();
    let mut decoded: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    let mut counts = [0; 2];
    let mut failures = Vec::new();
    for (name, row) in inputs.as_object().unwrap() {
        let parent = row[1].as_str().unwrap();
        let mut bytes = if parent.is_empty() {
            vec![]
        } else {
            decoded[parent][..row[2].as_u64().unwrap() as usize].to_vec()
        };
        for span in row[3].as_array().unwrap() {
            bytes.extend(
                base64(span[0].as_str().unwrap()).repeat(span[1].as_u64().unwrap() as usize),
            );
        }
        decoded.insert(name.clone(), bytes.clone());
        let input = if row[0] == "bytes" {
            Input::Bytes(&bytes)
        } else {
            Input::Text(std::str::from_utf8(&bytes).unwrap())
        };
        let observed = match compose(input) {
            Err(error) => {
                counts[1] += 1;
                json!({"error": [error.class]})
            }
            Ok(node) => {
                counts[0] += 1;
                let mut v = node.map_or(Value::Null, |n| tree(&n, n.root, &mut BTreeMap::new()));
                let compact = ascii_json(&v);
                if compact.len() > 65536 || json_depth(&v) > 100 {
                    v = json!({"compact_tree": {
                        "len": compact.len(), "sha256": digest::sha256(compact.as_bytes())}});
                }
                json!({"value": v})
            }
        };
        let expected = if oracle[name].get("error").is_some() {
            json!({"error": [oracle[name]["error"][0]]})
        } else {
            oracle[name].clone()
        };
        if observed != expected {
            failures.push(format!("{name}: got {observed}, expected {expected}"));
        }
    }
    eprintln!("success/error = {counts:?}; 257 records, no exemptions");
    assert_eq!(counts, [236, 21]);
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

#[test]
fn frozen_marked_diagnostics() {
    let records: Value = serde_json::from_str(include_str!("fixtures/y_e18_p3b.json")).unwrap();
    let mut failures = Vec::new();
    let mut count = 0;
    for row in records
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["implemented"] == true)
    {
        count += 1;
        let err = compose(Input::Text(row["text"].as_str().unwrap())).unwrap_err();
        if err.class != row["error"] || err.message != row["message"] {
            failures.push(format!("{}: {:?} != {}", row["case"], err, row["message"]));
        }
    }
    assert_eq!(count, 24);
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
