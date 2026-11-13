//! Preserve Python dictionary insertion order when rendering a ledger update.
use serde_json::Value;

/// json.dumps(indent=2, ensure_ascii=False), followed by a strict UTF-8 file write.
/// Keep Python-only scalars until rendering, rather than coercing through serde.
pub(crate) fn render_python(value: &crate::python_json::Value) -> Result<String, String> {
    use crate::python_json::Value as Python;
    enum Work<'a> {
        Value(&'a Python, usize),
        Text(String),
        String(&'a [u32]),
    }
    let mut work = vec![Work::Text("\n".into()), Work::Value(value, 0)];
    let mut points = Vec::new();
    while let Some(item) = work.pop() {
        // The pinned console CLI's indent=2 generator accepts 991 nested
        // arrays in a root field and raises on the 992nd. This is distinct
        // from json.loads' much larger C decoder nesting allowance.
        if matches!(&item, Work::Value(crate::python_json::Value::Object(_) | crate::python_json::Value::Array(_), level) if *level >= 992)
        {
            return Err("RecursionError: maximum recursion depth exceeded".into());
        }
        match item {
            Work::Text(text) => points.extend(text.chars().map(u32::from)),
            Work::String(text) => {
                points.extend(crate::executor_text::json_quote_points(text));
            }
            Work::Value(Python::Object(object), level) if !object.is_empty() => {
                points.extend("{\n".chars().map(u32::from));
                work.push(Work::Text(format!("\n{}}}", "  ".repeat(level))));
                let entries = object.iter().collect::<Vec<_>>();
                for (index, (key, value)) in entries.iter().enumerate().rev() {
                    if index + 1 < entries.len() {
                        work.push(Work::Text(",\n".into()));
                    }
                    work.push(Work::Value(value, level + 1));
                    work.push(Work::Text(": ".into()));
                    work.push(Work::String(&key.codepoints));
                    work.push(Work::Text("  ".repeat(level + 1)));
                }
            }
            Work::Value(Python::Array(array), level) if !array.is_empty() => {
                points.extend("[\n".chars().map(u32::from));
                work.push(Work::Text(format!("\n{}]", "  ".repeat(level))));
                for (index, value) in array.iter().enumerate().rev() {
                    if index + 1 < array.len() {
                        work.push(Work::Text(",\n".into()));
                    }
                    work.push(Work::Value(value, level + 1));
                    work.push(Work::Text("  ".repeat(level + 1)));
                }
            }
            Work::Value(Python::String(text), _) => work.push(Work::String(&text.codepoints)),
            Work::Value(value, _) => {
                let text = match value {
                    Python::Null => "null".into(),
                    Python::Bool(value) => value.to_string(),
                    Python::Array(_) => "[]".into(),
                    Python::Object(_) => "{}".into(),
                    Python::Number(number) => match number.py_str().as_str() {
                        "nan" => "NaN".into(),
                        "inf" => "Infinity".into(),
                        "-inf" => "-Infinity".into(),
                        other => other.to_owned(),
                    },
                    Python::String(_) => unreachable!(),
                };
                points.extend(text.chars().map(u32::from));
            }
        }
    }
    if let Some(start) = points
        .iter()
        .position(|point| (0xd800..=0xdfff).contains(point))
    {
        let end = start
            + points[start..]
                .iter()
                .take_while(|point| (0xd800..=0xdfff).contains(*point))
                .count();
        return Err(crate::executor_text::encode_error(
            "utf-8",
            &points,
            start,
            end,
            "surrogates not allowed",
        ));
    }
    Ok(points.into_iter().filter_map(char::from_u32).collect())
}

enum Layout {
    Object(Vec<(String, Layout)>),
    Array(Vec<Layout>),
    Scalar,
}
struct Reader<'a> {
    text: &'a str,
    offset: usize,
}
impl Reader<'_> {
    fn whitespace(&mut self) {
        while self
            .text
            .as_bytes()
            .get(self.offset)
            .is_some_and(u8::is_ascii_whitespace)
        {
            self.offset += 1;
        }
    }
    fn string(&mut self) -> Result<String, String> {
        let start = self.offset;
        self.offset += 1;
        while let Some(byte) = self.text.as_bytes().get(self.offset) {
            self.offset += 1;
            match byte {
                b'\\' => self.offset += 1,
                b'"' => {
                    return serde_json::from_str(&self.text[start..self.offset])
                        .map_err(|e| e.to_string());
                }
                _ => (),
            }
        }
        Err("unterminated ledger string".into())
    }
    fn node(&mut self) -> Result<Layout, String> {
        self.whitespace();
        match self.text.as_bytes().get(self.offset) {
            Some(b'{') => {
                self.offset += 1;
                let mut entries = Vec::new();
                loop {
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b'}') {
                        self.offset += 1;
                        return Ok(Layout::Object(entries));
                    }
                    let key = self.string()?;
                    self.whitespace();
                    self.offset += 1; // Validated source contains a colon.
                    let node = self.node()?;
                    if let Some((_, previous)) = entries.iter_mut().find(|(name, _)| name == &key) {
                        *previous = node;
                    } else {
                        entries.push((key, node));
                    }
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b',') {
                        self.offset += 1;
                    }
                }
            }
            Some(b'[') => {
                self.offset += 1;
                let mut items = Vec::new();
                loop {
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b']') {
                        self.offset += 1;
                        return Ok(Layout::Array(items));
                    }
                    items.push(self.node()?);
                    self.whitespace();
                    if self.text.as_bytes().get(self.offset) == Some(&b',') {
                        self.offset += 1;
                    }
                }
            }
            Some(b'"') => {
                self.string()?;
                Ok(Layout::Scalar)
            }
            Some(_) => {
                while self
                    .text
                    .as_bytes()
                    .get(self.offset)
                    .is_some_and(|b| !b",]} \t\r\n".contains(b))
                {
                    self.offset += 1;
                }
                Ok(Layout::Scalar)
            }
            None => Err("incomplete ledger".into()),
        }
    }
}
fn encode(value: &Value, layout: Option<&Layout>, level: usize) -> Result<String, String> {
    let indent = "  ".repeat(level);
    let child_indent = "  ".repeat(level + 1);
    match value {
        Value::Object(entries) if !entries.is_empty() => {
            let original = match layout {
                Some(Layout::Object(keys)) => keys.as_slice(),
                _ => &[],
            };
            let mut keys: Vec<&str> = original
                .iter()
                .map(|(key, _)| key.as_str())
                .filter(|key| entries.contains_key(*key))
                .collect();
            for key in ["status", "executed_argv", "notes"] {
                if entries.contains_key(key) && !keys.contains(&key) {
                    keys.push(key);
                }
            }
            for key in entries.keys() {
                if !keys.contains(&key.as_str()) {
                    keys.push(key);
                }
            }
            let mut rows = Vec::new();
            for key in keys {
                let shape = original
                    .iter()
                    .find(|(name, _)| name == key)
                    .map(|(_, shape)| shape);
                let item = entries.get(key).ok_or("missing ledger key")?;
                rows.push(format!(
                    "{child_indent}{}: {}",
                    serde_json::to_string(key).map_err(|e| e.to_string())?,
                    encode(item, shape, level + 1)?
                ));
            }
            Ok(format!("{{\n{}\n{indent}}}", rows.join(",\n")))
        }
        Value::Array(items) if !items.is_empty() => {
            let original = match layout {
                Some(Layout::Array(items)) => items.as_slice(),
                _ => &[],
            };
            let rows = items
                .iter()
                .enumerate()
                .map(|(index, item)| {
                    Ok(format!(
                        "{child_indent}{}",
                        encode(item, original.get(index), level + 1)?
                    ))
                })
                .collect::<Result<Vec<_>, String>>()?;
            Ok(format!("[\n{}\n{indent}]", rows.join(",\n")))
        }
        Value::Number(number) if number.is_f64() => {
            crate::executor_registry::python_float(number.as_f64().ok_or("invalid float")?)
                .map_err(|e| format!("{e:?}"))
        }
        _ => serde_json::to_string(value).map_err(|e| e.to_string()),
    }
}
pub(crate) fn render(original: &str, updated: &Value) -> Result<String, String> {
    // Validate before the small layout reader indexes delimiters.
    let _: Value = serde_json::from_str(original).map_err(|e| e.to_string())?;
    let layout = Reader {
        text: original,
        offset: 0,
    }
    .node()?;
    Ok(format!("{}\n", encode(updated, Some(&layout), 0)?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preserves_nested_order_and_python_scalars() {
        let original = r#"{"z":{"verifier":"keep","status":"pass","executed_argv":["fake"],"notes":"ok"},"a":[],"n":NaN,"f":1e400,"big":123456789012345678901234567890}"#;
        let parsed = crate::python_json::parse(original).unwrap();
        let rendered = render_python(&parsed).unwrap();
        assert!(
            rendered.starts_with(
                "{\n  \"z\": {\n    \"verifier\": \"keep\",\n    \"status\": \"pass\","
            )
        );
        assert!(rendered.ends_with(
            "  \"n\": NaN,\n  \"f\": Infinity,\n  \"big\": 123456789012345678901234567890\n}\n"
        ));
    }

    #[test]
    fn direct_ledger_dump_matches_pinned_console_recursion_boundary() {
        for (depth, fails) in [(991, false), (992, true)] {
            let source = format!("{{\"extra\": {}0{}}}", "[".repeat(depth), "]".repeat(depth));
            let parsed = crate::python_json::parse(&source).unwrap();
            let result = render_python(&parsed);
            assert_eq!(result.is_err(), fails, "depth={depth}");
            if fails {
                assert_eq!(
                    result.unwrap_err(),
                    "RecursionError: maximum recursion depth exceeded"
                );
            }
        }
    }
}
