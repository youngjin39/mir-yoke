//! Replay the immutable own/template W1 envelopes through the native command.
#[path = "../src/compact_snapshot.rs"]
mod compact_snapshot;

#[cfg(unix)]
#[path = "support/replay.rs"]
mod frozen;
use std::fs;

#[cfg(unix)]
fn replay(template: bool, command: &str, count: usize) {
    let family = format!(
        "{}.claude/hooks/{command}.sh",
        if template {
            "templates/common-harness/"
        } else {
            ""
        }
    );
    frozen::replay(&family, count);
}

#[cfg(unix)]
#[test]
fn own_post_compact_replay() {
    replay(false, "post-compact", 7);
}
#[cfg(unix)]
#[test]
fn template_post_compact_replay() {
    replay(true, "post-compact", 7);
}
#[cfg(unix)]
#[test]
fn own_compact_resume_replay() {
    replay(false, "compact-resume", 9);
}
#[cfg(unix)]
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
