//! Test-only slots: machine-derived Win32 text and synthetic root spellings.
#![allow(dead_code)]

pub fn root(text: &str, root: &str, token: &str) -> String {
    let plain = root.strip_prefix(r"\\?\").unwrap_or(root);
    let mut spellings = vec![root.to_owned(), plain.to_owned(), plain.replace('\\', "/")];
    spellings.extend([root.replace('\\', r"\\"), plain.replace('\\', r"\\")]);
    spellings.sort_by_key(|s| std::cmp::Reverse(s.len()));
    spellings.dedup();
    let mut result = text.to_owned();
    for spelling in spellings {
        result = result.replace(&spelling, token);
    }
    // Change separators only in the substituted path slot; preserve later text.
    let mut offset = 0;
    while let Some(start) = result[offset..].find(token) {
        let start = offset + start + token.len();
        let end = result[start..]
            .find(['\'', '"', '\r', '\n'])
            .map_or(result.len(), |i| start + i);
        let suffix = result[start..end].replace(r"\\", "/").replace('\\', "/");
        result.replace_range(start..end, &suffix);
        offset = start + suffix.len();
    }
    result
}

// Independent OS source, never the production formatter. Keep the code pinned.
pub fn localize(text: &str) -> String {
    let mut result = text.to_owned();
    let mut offset = 0;
    while let Some(start) = result[offset..].find("[WinError ") {
        let code_start = offset + start + "[WinError ".len();
        let code_end = code_start + result[code_start..].find(']').unwrap();
        let code: i32 = result[code_start..code_end].parse().unwrap();
        let message_start = code_end + 2;
        let tail = &result[message_start..];
        let end = [
            tail.find(": '"),
            tail.find('"'),
            tail.find('\r'),
            tail.find('\n'),
        ]
        .into_iter()
        .flatten()
        .min()
        .unwrap_or(tail.len());
        let pinned = &tail[..end];
        let raw = std::io::Error::from_raw_os_error(code).to_string();
        let suffix = format!(" (os error {code})");
        let message = raw
            .strip_suffix(&suffix)
            .expect("Rust OS error suffix")
            .trim_end();
        let message = if pinned.ends_with('.') {
            message
        } else {
            message.trim_end_matches('.')
        };
        // Python JSON captures use ensure_ascii=True. Keep their encoding exact.
        let message = if pinned.contains(r"\u") {
            message
                .chars()
                .map(|c| {
                    if c.is_ascii() {
                        c.to_string()
                    } else {
                        c.encode_utf16(&mut [0; 2])
                            .iter()
                            .map(|u| format!("\\u{u:04x}"))
                            .collect::<String>()
                    }
                })
                .collect::<String>()
        } else {
            message.to_owned()
        };
        result.replace_range(message_start..message_start + end, &message);
        offset = message_start + message.len();
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn locale_slot_preserves_code_class_paths_and_crlf() {
        let captured = "PermissionError: [WinError 5] \u{c561}\u{c138}\u{c2a4}\u{ac00} \u{ac70}\u{bd80}\u{b418}\u{c5c8}\u{c2b5}\u{b2c8}\u{b2e4}: 'source' -> 'destination'\r\n";
        let raw = std::io::Error::from_raw_os_error(5).to_string();
        let message = raw
            .strip_suffix(" (os error 5)")
            .unwrap()
            .trim_end_matches([' ', '\r', '\n', '.']);
        let expected =
            format!("PermissionError: [WinError 5] {message}: 'source' -> 'destination'\r\n");
        assert_eq!(localize(captured), expected);
        assert_ne!(
            localize(&captured.replace("WinError 5", "WinError 6")),
            expected
        );
        assert_ne!(localize(&captured.replace("'source'", "'wrong'")), expected);
        assert_ne!(
            localize(&captured.replace("PermissionError", "OSError")),
            expected
        );
        assert_eq!(
            localize("[Errno 2] pinned: 'source'"),
            "[Errno 2] pinned: 'source'"
        );
        let json = r#"{"errors":["[WinError 5] \uc561\uc138\uc2a4"]}"#;
        let ascii_message: String = message
            .encode_utf16()
            .map(|u| {
                if u < 128 {
                    char::from_u32(u32::from(u)).unwrap().to_string()
                } else {
                    format!("\\u{u:04x}")
                }
            })
            .collect();
        assert_eq!(
            localize(json),
            format!(r#"{{"errors":["[WinError 5] {ascii_message}"]}}"#)
        );
    }
    #[test]
    fn repr_root_keeps_error_and_relative_filename_exact() {
        let base = r"\\?\C:\scratch\case";
        let text =
            r"[Errno 2] No such file or directory: '\\\\?\\C:\\scratch\\case\\config\\file.json'";
        let expected = "[Errno 2] No such file or directory: '<tmp>/config/file.json'";
        assert_eq!(root(text, base, "<tmp>"), expected);
        assert_ne!(
            root(&text.replace("Errno 2", "Errno 3"), base, "<tmp>"),
            expected
        );
        assert_ne!(
            root(&text.replace("file.json", "wrong.json"), base, "<tmp>"),
            expected
        );
    }
    #[test]
    fn plain_and_raw_paths_keep_other_text_exact() {
        assert_eq!(
            root(
                r"C:\scratch\case\brief.json",
                r"\\?\C:\scratch\case",
                "<root>"
            ),
            "<root>/brief.json"
        );
        assert_eq!(
            root("outside \\ unchanged", r"C:\scratch\case", "<tmp>"),
            "outside \\ unchanged"
        );
        assert_eq!(
            root("/tmp/case/config/file", "/tmp/case", "<tmp>"),
            "<tmp>/config/file"
        );
    }
}
