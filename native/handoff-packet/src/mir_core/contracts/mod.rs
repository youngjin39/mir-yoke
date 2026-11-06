//! Frozen contract validation; deliberately limited to the first model slice.
pub mod agent_profile;
pub mod conductor_mode;
use serde_json::{Value, json};
pub type ValidationError = Value;
fn validate(data: &Value, defaults: &Value, order: &[&str]) -> Result<Value, ValidationError> {
    let mut output = defaults.clone();
    let mut errors = Vec::new();
    for &field in order {
        let Some(value) = data.get(field).or_else(|| defaults.get(field)) else {
            errors.push(json!({"loc":[field],"msg":"Field required","type":"missing"}));
            continue;
        };
        let mut value = value.clone();
        let failure = match field {
            "name" | "slug" | "description" | "system_prompt" if !value.is_string() => {
                Some(("string_type", "Input should be a valid string".into()))
            }
            "model" | "role_binding" => {
                let choices: &[&str] = if field == "model" {
                    &["opus", "sonnet", "haiku"]
                } else {
                    &["conductor", "executor", "reviewer", "planner", "tester"]
                };
                if choices.iter().any(|s| value.as_str() == Some(s)) {
                    None
                } else {
                    let quoted: Vec<_> = choices.iter().map(|s| format!("'{s}'")).collect();
                    Some((
                        "literal_error",
                        format!(
                            "Input should be {} or {}",
                            quoted[..quoted.len() - 1].join(", "),
                            quoted[quoted.len() - 1]
                        ),
                    ))
                }
            }
            "context_budget_tokens" | "max_output_tokens" | "temperature" => {
                let float = field == "temperature";
                let parsed = if float {
                    value
                        .as_f64()
                        .or_else(|| value.as_str()?.parse().ok())
                        .map(Value::from)
                } else {
                    value
                        .as_i64()
                        .or_else(|| value.as_str()?.parse().ok())
                        .map(Value::from)
                };
                if let Some(number) = parsed {
                    let n = number.as_f64().unwrap_or_default();
                    value = number;
                    let (min, max) = match field {
                        "context_budget_tokens" => (1000, 200000),
                        "max_output_tokens" => (256, 16000),
                        _ => (0, 2),
                    };
                    if n < min as f64 {
                        Some((
                            "greater_than_equal",
                            format!("Input should be greater than or equal to {min}"),
                        ))
                    } else if n > max as f64 {
                        Some((
                            "less_than_equal",
                            format!("Input should be less than or equal to {max}"),
                        ))
                    } else {
                        None
                    }
                } else if float {
                    Some((
                        "float_parsing",
                        "Input should be a valid number, unable to parse string as a number".into(),
                    ))
                } else {
                    Some((
                        "int_parsing",
                        "Input should be a valid integer, unable to parse string as an integer"
                            .into(),
                    ))
                }
            }
            _ => None,
        };
        if let Some((kind, msg)) = failure {
            errors.push(json!({"loc":[field],"msg":msg,"type":kind}));
        } else {
            output[field] = value;
        }
    }
    if let Some(fields) = data.as_object() {
        for key in fields.keys().filter(|key| !order.contains(&key.as_str())) {
            errors.push(json!({"loc":[key],"msg":"Extra inputs are not permitted","type":"extra_forbidden"}));
        }
    }
    if errors.is_empty() {
        Ok(output)
    } else {
        Err(json!(["ValidationError", errors]))
    }
}
