//! Preserve permissive Python fields; unknown input keys are ignored.
use crate::executor_local::{Error, JsonSyntax};
use crate::executor_policy_query::ascii_json_text;
use serde_json::{Value, json};

#[derive(Clone, Debug, PartialEq)]
pub struct ToolContract {
    pub idempotency_key: Value,
    pub precondition: Value,
    pub dry_run: Value,
    pub side_effect_summary: Value,
    pub extra: Value,
}
impl ToolContract {
    pub fn from_dict(data: &Value) -> Result<Self, Error> {
        for key in [
            "idempotency_key",
            "precondition",
            "dry_run",
            "side_effect_summary",
        ] {
            if data.get(key).is_none() {
                return Err(Error::Invalid(format!("missing required field: {key}")));
            }
        }
        let length = match &data["side_effect_summary"] {
            Value::String(s) => s.chars().count(),
            Value::Array(a) => a.len(),
            Value::Object(o) => o.len(),
            value => {
                let kind = match value {
                    Value::Null => "NoneType",
                    Value::Bool(_) => "bool",
                    Value::Number(n) if n.is_f64() => "float",
                    _ => "int",
                };
                return Err(Error::Type(format!("object of type '{kind}' has no len()")));
            }
        };
        if length > 200 {
            return Err(Error::Invalid(format!(
                "side_effect_summary too long: {length} chars (max 200)"
            )));
        }
        Ok(Self {
            idempotency_key: data["idempotency_key"].clone(),
            precondition: data["precondition"].clone(),
            dry_run: data["dry_run"].clone(),
            side_effect_summary: data["side_effect_summary"].clone(),
            extra: data.get("extra").cloned().unwrap_or_else(|| json!({})),
        })
    }
    pub fn from_json(text: &str) -> Result<Self, Error> {
        JsonSyntax::validate(text)?;
        Self::from_dict(&serde_json::from_str(text).map_err(Error::Json)?)
    }
    pub fn to_dict(&self) -> Value {
        let mut data = json!({"idempotency_key":self.idempotency_key,"precondition":self.precondition,"dry_run":self.dry_run,"side_effect_summary":self.side_effect_summary});
        let present = match &self.extra {
            Value::Null => false,
            Value::Bool(v) => *v,
            Value::Number(v) => v.as_f64().is_some_and(|n| n != 0.0),
            Value::String(v) => !v.is_empty(),
            Value::Array(v) => !v.is_empty(),
            Value::Object(v) => !v.is_empty(),
        };
        if present {
            data["extra"] = self.extra.clone();
        }
        data
    }
    pub fn to_json(&self) -> String {
        ascii_json_text(&super::canonical::canonical_json(
            &self.to_dict(),
            Some(&[]),
        ))
    }
}
pub fn make_idempotency_key(parts: &[&str]) -> String {
    crate::digest::sha256(parts.join("|").as_bytes())[..16].to_owned()
}
