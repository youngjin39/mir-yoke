//! Private serde storage preserves frozen instances and unvalidated model_copy.
use super::{Kind as K, ValidationError, validate};
use serde_json::{Value, json};
#[derive(Clone, Debug, PartialEq)]
pub struct AgentProfile(Value);
impl AgentProfile {
    fn fields() -> Vec<super::Field> {
        super::contract!(@fields;
            ("name", K::String, None, None, None),
            ("slug", K::String, None, None, None),
            ("model", K::Literal(&["opus", "sonnet", "haiku"]), None, None, None),
            ("description", K::String, None, None, None),
            ("role_binding", K::Literal(&["conductor", "executor", "reviewer", "planner", "tester"]), Some(json!("executor")), None, None),
            ("system_prompt", K::String, None, None, None),
            ("tools", K::Tuple(&K::String), Some(json!([])), None, None),
            ("forbidden_tools", K::Tuple(&K::String), Some(json!([])), None, None),
            ("context_budget_tokens", K::Int, None, Some((1000.0, 200000.0)), None),
            ("temperature", K::Float, Some(json!(0.2)), Some((0.0, 2.0)), None),
            ("max_output_tokens", K::Int, Some(json!(4096)), Some((256.0, 16000.0)), None),
            ("stop_sequences", K::Tuple(&K::String), Some(json!([])), None, None),
            ("allowed_files", K::Tuple(&K::String), Some(json!([])), None, None),
            ("provenance", K::Dict(&K::String), Some(json!({})), None, None),
        )
    }
    pub fn from_dict(data: &Value) -> Result<Self, ValidationError> {
        validate(data, &Self::fields()).map(|value| Self(value.dump))
    }
    pub fn to_dict(&self) -> Value {
        self.0.clone()
    }
    pub fn to_json(&self) -> String {
        let fields: Vec<_> = Self::fields()
            .iter()
            .map(|(k, ..)| {
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
                if Self::fields().iter().any(|f| f.0 == key) {
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
