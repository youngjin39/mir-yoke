//! Frozen released-Python decisions, including malformed payload degradation.
use std::io::Write;
use std::process::{Command, Stdio};

fn decode(text: &str) -> Vec<u8> {
    const DIGITS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::new();
    let (mut bits, mut count) = (0u32, 0);
    for byte in text.bytes().filter(|b| *b != b'=') {
        let value = DIGITS.iter().position(|b| *b == byte).unwrap() as u32;
        bits = (bits << 6) | value;
        count += 6;
        if count >= 8 {
            count -= 8;
            out.push((bits >> count) as u8);
        }
    }
    out
}

#[test]
fn handoff_python_json_admission() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/handoff-json.json")).unwrap();
    for record in fixture["records"].as_array().unwrap() {
        let home = tempfile::tempdir().unwrap();
        let mut child = Command::new(env!("CARGO_BIN_EXE_handoff-packet"))
            .env("HOME", home.path())
            .env("PATH", "")
            .current_dir(home.path())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut input = vec![b' '; record["input_prefix_spaces"].as_u64().unwrap() as usize];
        input.extend(decode(record["input"].as_str().unwrap()));
        child.stdin.take().unwrap().write_all(&input).unwrap();
        let result = child.wait_with_output().unwrap();
        let capture: serde_json::Value =
            serde_json::from_str(include_str!("fixtures/windows-deep.json")).unwrap();
        if cfg!(windows)
            && record["name"]
                .as_str()
                .and_then(|s| s.strip_prefix("depth-"))
                .and_then(|s| s.parse::<usize>().ok())
                .is_some_and(|depth| depth >= 2997)
        {
            let expected = &capture["boundaries"][0]["first_changed"]["reference"];
            assert_eq!(
                (result.status.code(), result.stdout, result.stderr),
                (
                    Some(expected["code"].as_i64().unwrap() as i32),
                    expected["stdout"].as_str().unwrap().as_bytes().to_vec(),
                    expected["stderr"].as_str().unwrap().as_bytes().to_vec()
                ),
                "{}",
                record["name"]
            );
            continue;
        }
        let native_eol = |bytes: Vec<u8>| {
            if cfg!(windows) {
                bytes
                    .split(|b| *b == b'\n')
                    .collect::<Vec<_>>()
                    .join(&b"\r\n"[..])
            } else {
                bytes
            }
        };
        assert_eq!(
            (result.status.code(), result.stdout, result.stderr),
            (
                record["code"].as_i64().map(|n| n as i32),
                native_eol(decode(record["stdout"].as_str().unwrap())),
                native_eol(decode(record["stderr"].as_str().unwrap()))
            ),
            "{}",
            record["name"]
        );
    }
}
