//! Private serde storage preserves frozen instances and unvalidated model_copy.
use super::{ValidationError, validate};
use serde_json::{Value, json};
#[derive(Clone, Debug, PartialEq)]
pub struct AgentProfile(Value);
impl AgentProfile {
    const ORDER: [&'static str; 14] = [
        "name",
        "slug",
        "model",
        "description",
        "role_binding",
        "system_prompt",
        "tools",
        "forbidden_tools",
        "context_budget_tokens",
        "temperature",
        "max_output_tokens",
        "stop_sequences",
        "allowed_files",
        "provenance",
    ];
    pub fn from_dict(data: &Value) -> Result<Self, ValidationError> {
        let defaults = json!({"role_binding":"executor","tools":[],"forbidden_tools":[],"temperature":0.2,"max_output_tokens":4096,"stop_sequences":[],"allowed_files":[],"provenance":{}});
        validate(data, &defaults, &Self::ORDER).map(Self)
    }
    pub fn to_dict(&self) -> Value {
        self.0.clone()
    }
    pub fn to_json(&self) -> String {
        let fields: Vec<_> = Self::ORDER
            .iter()
            .map(|k| {
                format!(
                    "{}:{}",
                    json!(k),
                    super::super::canonical::canonical_json(&self.0[k], Some(&[]))
                )
            })
            .collect();
        format!("{{{}}}", fields.join(","))
    }
    /// Match Python model_copy(update=...): no validation; unknown keys do not dump.
    pub fn fork(&self, overrides: &Value) -> Self {
        let mut copy = self.clone();
        if let Some(fields) = overrides.as_object() {
            for (key, value) in fields {
                if Self::ORDER.contains(&key.as_str()) {
                    copy.0[key] = if key == "temperature" {
                        value
                            .as_f64()
                            .map(Value::from)
                            .unwrap_or_else(|| value.clone())
                    } else {
                        value.clone()
                    };
                }
            }
        }
        copy
    }
}
impl serde::Serialize for AgentProfile {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0.serialize(serializer)
    }
}
