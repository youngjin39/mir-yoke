//! Shared, bounded tomllib diagnostic compatibility.
/// Preserve oversized integer timeouts without coercing other TOML numbers.
pub(crate) fn load_config(text: &str) -> Result<(serde_json::Value, Option<String>), String> {
    let error = match toml::from_str::<toml::Value>(text) {
        Ok(value) => {
            return serde_json::to_value(value)
                .map(|v| (v, None))
                .map_err(|e| e.to_string());
        }
        Err(error) => error,
    };
    let fallback = || tomllib_error(&error, text);
    if error.message() != "number too large to fit in target type" {
        return Err(fallback());
    }
    let span = error.span().ok_or_else(fallback)?;
    let start = span.start;
    let end = text[start..]
        .find(|c: char| c.is_whitespace() || ",]}#".contains(c))
        .map_or(text.len(), |n| start + n);
    let token = &text[start..end];
    let valid = regex::Regex::new(r"^(?:\+?[1-9](?:_?[0-9])*|0x[0-9a-fA-F](?:_?[0-9a-fA-F])*|0o[0-7](?:_?[0-7])*|0b[01](?:_?[01])*)$").map_err(|e| e.to_string())?;
    if !valid.is_match(token) {
        return Err(fallback());
    }
    // Prove the overflowing token's destination, including quoted/dotted keys,
    // without matching source lines, comments or string contents.
    let mut result = None;
    for replacement in [0, 1] {
        let mut probe = text.to_owned();
        probe.replace_range(start..end, &replacement.to_string());
        let parsed: toml::Value = toml::from_str(&probe).map_err(|_| fallback())?;
        let value = serde_json::to_value(parsed).map_err(|e| e.to_string())?;
        if value.pointer("/memory/embedding/timeout_sec") != Some(&serde_json::json!(replacement)) {
            return Err(fallback());
        }
        result = Some(value);
    }
    let clean = token.replace('_', "");
    let unsigned = clean.trim_start_matches('+');
    let (base, digits) = match unsigned.get(..2) {
        Some("0x") => (16, &unsigned[2..]),
        Some("0o") => (8, &unsigned[2..]),
        Some("0b") => (2, &unsigned[2..]),
        _ => (10, unsigned),
    };
    if base == 10 && digits.len() > 4300 {
        return Err(format!(
            "Exceeds the limit (4300 digits) for integer string conversion: value has {} digits; use sys.set_int_max_str_digits() to increase the limit",
            digits.len()
        ));
    }
    // Convert power-of-two TOML bases without a machine integer bound.
    let mut decimal = vec![0u32];
    for digit in digits.chars() {
        let mut carry = digit.to_digit(base).ok_or_else(fallback)?;
        for place in &mut decimal {
            carry += *place * base;
            *place = carry % 10;
            carry /= 10;
        }
        while carry > 0 {
            decimal.push(carry % 10);
            carry /= 10;
        }
    }
    let number: String = decimal
        .iter()
        .rev()
        .filter_map(|d| char::from_digit(*d, 10))
        .collect();
    let mut result = result.ok_or_else(fallback)?;
    result["memory"]["embedding"]["timeout_sec"] = serde_json::json!(i64::MAX);
    Ok((result, Some(number)))
}

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
    fn yfix9_timeout_scope() {
        for text in [
            "[memory.embedding]\ntimeout_sec=18446744073709551616\n",
            "memory.embedding.timeout_sec=18446744073709551616\n",
            "[\"memory\".'embedding']\n\"timeout_sec\"=18446744073709551616 # comment\n",
        ] {
            let (_, number) = super::load_config(text).unwrap();
            assert_eq!(number.as_deref(), Some("18446744073709551616"));
        }
        for text in [
            "other=18446744073709551616\n[memory.embedding]\ntimeout_sec=0\n",
            "other=18446744073709551616\n[memory.embedding]\ntimeout_sec=1\n",
            "[memory.embedding]\ndim=18446744073709551616\n",
            "[memory.embedding]\ntimeout_sec=18446744073709551616z\n",
            "[memory.embedding]\ntimeout_sec=018446744073709551616\n",
        ] {
            assert!(super::load_config(text).is_err(), "{text}");
        }
    }
    #[test]
    fn yfix9_integer_validation_and_limit() {
        for token in ["18446744073709551615", "123456789012345678901234567890"] {
            let (_, number) =
                super::load_config(&format!("[memory.embedding]\ntimeout_sec={token}")).unwrap();
            assert_eq!(number.as_deref(), Some(token));
        }
        let text = format!("[memory.embedding]\ntimeout_sec={}", "1".repeat(4301));
        assert!(
            super::load_config(&text)
                .unwrap_err()
                .contains("value has 4301 digits")
        );
        assert!(super::load_config("[memory.embedding]\ntimeout_sec=30\na=[").is_err());
    }
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
