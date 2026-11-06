#![cfg(unix)]
use handoff_packet::mir_front::{SUBCOMMANDS, root};
use serde_json::Value;
use std::{ffi::OsString, os::unix::ffi::OsStringExt};

fn decode(value: &Value) -> Vec<u8> {
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut bits = 0u32;
    let mut count = 0;
    let mut out = Vec::new();
    for byte in value.as_str().unwrap().bytes().take_while(|b| *b != b'=') {
        bits = (bits << 6) | alphabet.iter().position(|b| *b == byte).unwrap() as u32;
        count += 6;
        if count >= 8 {
            count -= 8;
            out.push((bits >> count) as u8);
        }
    }
    out
}

#[test]
fn frozen_root_records() {
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/w2/cli-root.json")).unwrap();
    let mut counts = [0; 3];
    for record in records {
        let id = record["id"].as_str().unwrap();
        if id == "import_laziness" {
            counts[2] += 1;
            continue; // Python import mechanics have no native library counterpart.
        }
        assert!(id.starts_with("module:") || id.starts_with("console:"));
        counts[usize::from(id.starts_with("console:"))] += 1;
        let argv: Vec<_> = record["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|arg| OsString::from_vec(decode(arg)))
            .collect();
        let expected = (
            record["exit"].as_i64().unwrap() as i32,
            decode(&record["stdout"]),
            decode(&record["stderr"]),
        );
        assert_eq!(root(&argv), Some(expected), "{id}");
    }
    assert_eq!(counts, [14, 14, 1]);
}

#[test]
fn known_commands_defer_dispatch() {
    assert_eq!(SUBCOMMANDS.len(), 13);
    for name in SUBCOMMANDS {
        assert_eq!(root(&[name.into(), "--help".into()]), None, "{name}");
    }
}
