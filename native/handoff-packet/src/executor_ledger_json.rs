//! Preserve Python dictionary insertion order when rendering a ledger update.
use serde_json::Value;

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
    use serde_json::json;
    #[test]
    fn preserves_nested_order_and_appends_execution_fields() {
        let original = r#"{"z":{"verifier":"keep","status":"planned"},"a":[]}"#;
        assert_eq!(render(original, &json!({"z":{"verifier":"keep","status":"pass","notes":"ok","executed_argv":["fake"]},"a":[]})).unwrap(), "{\n  \"z\": {\n    \"verifier\": \"keep\",\n    \"status\": \"pass\",\n    \"executed_argv\": [\n      \"fake\"\n    ],\n    \"notes\": \"ok\"\n  },\n  \"a\": []\n}\n");
    }
}
