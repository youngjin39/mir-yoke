//! Shared, bounded tomllib diagnostic compatibility.
pub(crate) fn tomllib_error(error: &toml::de::Error, text: &str) -> String {
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
