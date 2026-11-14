//! Shared, bounded tomllib diagnostic compatibility.
pub(crate) fn tomllib_error(error: &toml::de::Error, text: &str) -> String {
    if error.message().contains("invalid array")
        && error.span().is_some_and(|s| s.start >= text.len())
    {
        return if !array_expects_value(text) {
            "Unclosed array (at end of document)"
        } else {
            "Invalid value (at end of document)"
        }
        .into();
    }
    if text.trim_end() == "[" {
        return "Invalid initial character for a key part (at end of document)".into();
    }
    if error.message().contains("expected `.`, `]`") {
        let offset = error.span().map_or(text.len(), |s| s.start);
        let location = if offset >= text.len() {
            "end of document".into()
        } else {
            let prefix = &text[..offset];
            let line = prefix.bytes().filter(|b| *b == b'\n').count() + 1;
            let column = prefix.rsplit('\n').next().unwrap_or("").chars().count() + 1;
            format!("line {line}, column {column}")
        };
        format!("Expected ']' at the end of a table declaration (at {location})")
    } else {
        "unmapped TOML parse error".into()
    }
}

// At EOF Python distinguishes a missing element from a missing closing bracket.
// Ignore TOML comments and whitespace, keeping quoted '#' characters as values.
fn array_expects_value(text: &str) -> bool {
    let bytes = text.as_bytes();
    let (mut i, mut last) = (0, 0);
    let mut quote: Option<(u8, bool)> = None;
    let mut comment = false;
    while i < bytes.len() {
        let b = bytes[i];
        if comment {
            comment = b != b'\n';
        } else if let Some((q, triple)) = quote {
            if q == b'"' && b == b'\\' {
                i += 1;
            } else if b == q && (!triple || bytes.get(i..i + 3) == Some(&[q, q, q])) {
                if triple {
                    i += 2;
                    // Python consumes up to two extra quotes as string content
                    // before closing, rather than opening another string.
                    for _ in 0..2 {
                        if bytes.get(i + 1) == Some(&q) {
                            i += 1;
                        } else {
                            break;
                        }
                    }
                }
                quote = None;
                last = q;
            }
        } else if b == b'#' {
            comment = true;
        } else if matches!(b, b'"' | b'\'') {
            let triple = bytes.get(i..i + 3) == Some(&[b, b, b]);
            quote = Some((b, triple));
            last = b;
            if triple {
                i += 2;
            }
        } else if !matches!(b, b' ' | b'\t' | b'\n' | b'\r') {
            last = b;
        }
        i += 1;
    }
    matches!(last, b'[' | b',')
}

#[cfg(test)]
mod tests {
    #[test]
    fn y_e5_eof_array_python_parity() {
        let records: Vec<serde_json::Value> =
            serde_json::from_str(include_str!("../../tests/fixtures/y-e5-tomllib.json")).unwrap();
        let mut matched = 0;
        let (mut closing_cases, mut closing_diagnostics) = (0, 0);
        for r in records {
            let closing_case = r.get("closing_quotes").is_some();
            closing_cases += usize::from(closing_case);
            let text = r["text"].as_str().unwrap();
            let result = toml::from_str::<toml::Value>(text);
            if let Some(value) = r.get("value") {
                assert_eq!(
                    serde_json::to_value(result.unwrap()).unwrap(),
                    *value,
                    "{text:?}"
                );
                continue;
            }
            let error = result.unwrap_err();
            if error.message().contains("invalid array")
                && error.span().is_some_and(|s| s.start >= text.len())
            {
                matched += 1;
                closing_diagnostics += usize::from(closing_case);
                assert_eq!(super::tomllib_error(&error, text), r["error"], "{text:?}");
            }
        }
        assert!(matched > 100);
        assert_eq!(closing_cases, 80);
        assert_eq!(closing_diagnostics, 24);
    }
}
