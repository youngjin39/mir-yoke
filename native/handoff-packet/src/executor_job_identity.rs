//! Finite identity evidence with explicit owner-supplied package provenance.
use crate::executor_local::Error;
use serde_json::{Value, json};

#[derive(Clone, Debug)]
pub struct JobIdentity {
    package: String,
    version: Option<String>,
}
impl JobIdentity {
    pub fn parse(value: &Value) -> Result<Self, Error> {
        let invalid = || {
            Error::Invalid("native_policy: job_identity requires codex_mcp_v1, package and optional string package_version".into())
        };
        let data = value.as_object().ok_or_else(invalid)?;
        if data
            .keys()
            .any(|key| !["name", "package", "package_version"].contains(&key.as_str()))
            || data.get("name").and_then(Value::as_str) != Some("codex_mcp_v1")
        {
            return Err(invalid());
        }
        let package = data
            .get("package")
            .and_then(Value::as_str)
            .filter(|name| !name.is_empty())
            .ok_or_else(invalid)?
            .to_owned();
        let version = data
            .get("package_version")
            .map(|value| value.as_str().map(str::to_owned).ok_or_else(invalid))
            .transpose()?;
        Ok(Self { package, version })
    }
    pub fn enabled(&self) -> bool {
        self.version.is_some()
    }
    pub fn render(&self, dispatch: bool, prompt: &str, model: Option<&str>) -> String {
        let model = model.unwrap_or(if dispatch {
            "codex-config-default"
        } else {
            "policy-or-config-default"
        });
        let fields = [
            ("ceiling", "none-v1-usage-alerting-only".to_owned()),
            (
                "instruction_sha256",
                crate::digest::sha256(prompt.as_bytes()),
            ),
            ("model_alias", model.to_owned()),
            (
                "package",
                format!(
                    "{} {}",
                    self.package,
                    self.version.as_deref().unwrap_or_default()
                ),
            ),
            ("tool_schema", "codex-mcp:tools/codex".to_owned()),
        ];
        format!(
            "{{{}}}",
            fields
                .iter()
                .map(|(key, value)| format!("{}: {}", ascii_string(key), ascii_string(value)))
                .collect::<Vec<_>>()
                .join(", ")
        )
    }
}
fn ascii_string(text: &str) -> String {
    let mut output = String::new();
    for character in json!(text).to_string().chars() {
        if character < '\u{7f}' {
            output.push(character);
        } else {
            for unit in character.encode_utf16(&mut [0; 2]) {
                output.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    output
}
