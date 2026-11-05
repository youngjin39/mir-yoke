//! Replay the immutable own/template W1 envelopes through the native command.
#[path = "../src/compact_snapshot.rs"]
mod compact_snapshot;

use serde_json::Value;
use std::{
    fs,
    io::Write,
    process::{Command, Stdio},
};

fn decode(value: &Value) -> Vec<u8> {
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut accumulator = 0u32;
    let mut bits = 0;
    let mut output = Vec::new();
    for byte in value.as_str().unwrap().bytes().take_while(|b| *b != b'=') {
        let digit = alphabet.iter().position(|b| *b == byte).unwrap() as u32;
        accumulator = (accumulator << 6) | digit;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            output.push((accumulator >> bits) as u8);
        }
    }
    output
}

fn replay(template: bool, command: &str, count: usize) {
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/w1/records.json")).unwrap();
    let family = format!(
        "{}.claude/hooks/{command}.sh",
        if template {
            "templates/common-harness/"
        } else {
            ""
        }
    );
    let mut seen = 0;
    for record in records.iter().filter(|r| r["family"] == family) {
        let id = record["id"].as_str().unwrap();
        let root = std::env::temp_dir().join(format!(
            "project-hooks-{}-{}-{}-{}",
            std::process::id(),
            template,
            command,
            record["case"].as_str().unwrap()
        ));
        fs::create_dir_all(root.join("tasks/handoffs")).unwrap();
        let handoff = root.join("tasks/handoffs/session-handoff-LATEST.md");
        if let Some(entry) = record["setup"].get("project/tasks/handoffs/session-handoff-LATEST.md")
        {
            fs::write(&handoff, decode(&entry["base64"])).unwrap();
        }
        let mut child = Command::new(env!("CARGO_BIN_EXE_project-hooks"))
            .arg(command)
            .env("CLAUDE_PROJECT_DIR", &root)
            .current_dir(&root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(&decode(&record["stdin"]))
            .unwrap();
        let output = child.wait_with_output().unwrap();
        assert_eq!(
            output.status.code(),
            Some(record["expected"]["exit"].as_i64().unwrap() as i32),
            "{id}"
        );
        assert_eq!(
            output.stdout,
            decode(&record["expected"]["stdout"]),
            "{id}: stdout"
        );
        assert_eq!(
            output.stderr,
            decode(&record["expected"]["stderr"]),
            "{id}: stderr"
        );
        fs::remove_dir_all(root).unwrap();
        seen += 1;
    }
    assert_eq!(seen, count);
}

#[test]
fn own_post_compact_replay() {
    replay(false, "post-compact", 7);
}
#[test]
fn template_post_compact_replay() {
    replay(true, "post-compact", 7);
}
#[test]
fn own_compact_resume_replay() {
    replay(false, "compact-resume", 9);
}
#[test]
fn template_compact_resume_replay() {
    replay(true, "compact-resume", 9);
}

#[test]
fn recovery_exact_byte_boundary_and_python_whitespace() {
    use compact_snapshot::{FOOTER, HEADER, MAX_CONTEXT_BYTES, recovery};
    let size = MAX_CONTEXT_BYTES - HEADER.len() - FOOTER.len();
    let body = "x".repeat(size);
    assert_eq!(recovery(&body).len(), MAX_CONTEXT_BYTES);
    assert!(!recovery(&body).contains("truncated"));
    assert!(recovery(&(body + "x")).contains("truncated at 8192 bytes"));
    assert_eq!(
        recovery("\u{1c}\r\n text \u{1f}"),
        format!("{HEADER}text{FOOTER}")
    );
}

#[test]
fn parse_returns_only_marked_body() {
    use compact_snapshot::{BEGIN, END, parse};
    assert_eq!(
        parse(&format!("curated\n{BEGIN}\nsnapshot\n{END}\ncurated")),
        Ok("\nsnapshot\n")
    );
}

#[test]
fn invalid_utf8_and_newline_translation() {
    use compact_snapshot::{compact_resume, post_compact, read_handoff};
    let root = std::env::temp_dir().join(format!("project-hooks-read-{}", std::process::id()));
    fs::create_dir_all(&root).unwrap();
    let path = root.join("handoff.md");
    fs::write(&path, b"a\r\nb\rc\n").unwrap();
    assert_eq!(read_handoff(&path).unwrap(), "a\nb\nc\n");
    fs::write(&path, [0xff]).unwrap();
    assert!(post_compact(&path).contains("unreadable: UnicodeDecodeError"));
    assert!(
        compact_resume(&path, br#"{"source":"compact"}"#)
            .contains("unreadable (UnicodeDecodeError)")
    );
    fs::remove_dir_all(root).unwrap();
}
