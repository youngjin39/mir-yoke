//! Frozen contract validation; deliberately limited to the five-model slice.
pub mod agent_profile;
pub mod conductor_mode;
pub mod discord_event;
pub mod provider_result;
pub mod route_decision;
use serde_json::{Value, json};
pub type ValidationError = Value;
#[derive(Clone, Copy)]
enum Kind {
    String,
    Int,
    Float,
    Bool,
    Literal(&'static [&'static str]),
    Nullable(&'static Kind),
    Tuple(&'static Kind),
    Dict(&'static Kind),
    AnyDict,
}
// Name, kind, default, numeric bounds, maximum string length (in class order).
type Bounds = Option<(f64, f64)>;
type Field = (&'static str, Kind, Option<Value>, Bounds, Option<usize>);
#[derive(Clone, Debug, PartialEq)]
struct Validated {
    dump: Value,
    floats: std::collections::BTreeMap<String, f64>,
}
fn coerce(value: &mut Value, kind: Kind, loc: Vec<Value>, errors: &mut Vec<Value>) -> Option<f64> {
    let mut parsed = None;
    let failure = match kind {
        Kind::String if !value.is_string() => {
            Some(("string_type", "Input should be a valid string"))
        }
        Kind::AnyDict | Kind::Dict(_) if !value.is_object() => {
            Some(("dict_type", "Input should be a valid dictionary"))
        }
        Kind::Int | Kind::Float => match number(value, matches!(kind, Kind::Float)) {
            Ok(n) => {
                parsed = Some(n);
                *value = if matches!(kind, Kind::Float) {
                    Value::from(n)
                } else {
                    json!(n as i64)
                };
                None
            }
            Err(e) => Some(e),
        },
        Kind::Bool => {
            let parsed = value.as_bool().or_else(|| {
                match value.as_str().map(str::to_ascii_lowercase).as_deref() {
                    Some("true" | "1" | "yes" | "on" | "t" | "y") => Some(true),
                    Some("false" | "0" | "no" | "off" | "f" | "n") => Some(false),
                    _ => match value.as_f64() {
                        Some(0.0) => Some(false),
                        Some(1.0) => Some(true),
                        _ => None,
                    },
                }
            });
            if let Some(v) = parsed {
                *value = json!(v);
                None
            } else if value.is_string() || value.is_number() {
                Some((
                    "bool_parsing",
                    "Input should be a valid boolean, unable to interpret input",
                ))
            } else {
                Some(("bool_type", "Input should be a valid boolean"))
            }
        }
        Kind::Literal(choices) if !choices.iter().any(|s| value.as_str() == Some(s)) => {
            let quoted: Vec<_> = choices.iter().map(|s| format!("'{s}'")).collect();
            errors.push(json!({"loc":loc,"msg":format!("Input should be {} or {}", quoted[..quoted.len()-1].join(", "), quoted[quoted.len()-1]),"type":"literal_error"}));
            None
        }
        Kind::Nullable(inner) if !value.is_null() => return coerce(value, *inner, loc, errors),
        Kind::Tuple(element) => {
            if let Some(values) = value.as_array_mut() {
                for (i, v) in values.iter_mut().enumerate() {
                    let mut path = loc.clone();
                    path.push(json!(i));
                    coerce(v, *element, path, errors);
                }
            } else {
                errors.push(
                    json!({"loc":loc,"msg":"Input should be a valid tuple","type":"tuple_type"}),
                );
            }
            None
        }
        Kind::Dict(element) => {
            if let Some(values) = value.as_object_mut() {
                for (k, v) in values {
                    let mut path = loc.clone();
                    path.push(json!(k));
                    coerce(v, *element, path, errors);
                }
            }
            None
        }
        _ => None,
    };
    if let Some((kind, msg)) = failure {
        errors.push(json!({"loc":loc,"msg":msg,"type":kind}));
    }
    parsed
}

type Failure = (&'static str, &'static str);
fn number(value: &Value, float: bool) -> Result<f64, Failure> {
    let parsed = value
        .as_f64()
        .or_else(|| value.as_bool().map(|v| u8::from(v) as f64))
        .or_else(|| {
            let text = value.as_str()?.trim();
            if text.as_bytes().windows(2).any(|p| {
                (p[0] == b'_' && !p[1].is_ascii_digit()) || (p[1] == b'_' && !p[0].is_ascii_digit())
            }) || text.starts_with('_')
                || text.ends_with('_')
            {
                return None;
            }
            if !float && text.contains(['e', 'E']) {
                return None;
            }
            text.replace('_', "").parse().ok()
        });
    let Some(n) = parsed else {
        return Err(match (float, value.is_string()) {
            (true, true) => (
                "float_parsing",
                "Input should be a valid number, unable to parse string as a number",
            ),
            (true, false) => ("float_type", "Input should be a valid number"),
            (false, true) => (
                "int_parsing",
                "Input should be a valid integer, unable to parse string as an integer",
            ),
            (false, false) => ("int_type", "Input should be a valid integer"),
        });
    };
    if !float && (!n.is_finite() || n.fract() != 0.0) {
        return Err((
            "int_from_float",
            "Input should be a valid integer, got a number with a fractional part",
        ));
    }
    Ok(n)
}
fn validate(data: &Value, fields: &[Field]) -> Result<Validated, ValidationError> {
    let mut output = Validated {
        dump: json!({}),
        floats: Default::default(),
    };
    let mut errors = Vec::new();
    for (field, kind, default, bounds, max_length) in fields {
        let Some(value) = data.get(field).or(default.as_ref()) else {
            errors.push(json!({"loc":[field],"msg":"Field required","type":"missing"}));
            continue;
        };
        let mut value = value.clone();
        let parsed = coerce(&mut value, *kind, vec![json!(field)], &mut errors);
        if let (Some(n), Some((min, max))) = (parsed, bounds) {
            for (failed, direction, bound) in [(n < *min, "greater", min), (n > *max, "less", max)]
            {
                if failed {
                    errors.push(json!({"loc":[field],"msg":format!("Input should be {direction} than or equal to {bound}"),"type":format!("{direction}_than_equal")}));
                }
            }
        }
        if let Some(max) = max_length
            && value.as_str().is_some_and(|s| s.chars().count() > *max)
        {
            errors.push(json!({"loc":[field],"msg":format!("String should have at most {max} characters"),"type":"string_too_long"}));
        }
        if matches!(kind, Kind::Float)
            && let Some(n) = parsed
        {
            output.floats.insert((*field).into(), n);
        }
        output.dump[field] = value;
    }
    if let Some(input) = data.as_object() {
        for key in input
            .keys()
            .filter(|key| !fields.iter().any(|f| f.0 == key.as_str()))
        {
            errors.push(json!({"loc":[key],"msg":"Extra inputs are not permitted","type":"extra_forbidden"}));
        }
    }
    if errors.is_empty() {
        Ok(output)
    } else {
        Err(json!(["ValidationError", errors]))
    }
}
macro_rules! contract {
    (@fields; $($spec:expr),* $(,)?) => { vec![$($spec),*] };
    ($name:ident; $($spec:expr),+ $(,)?) => {
        #[derive(Clone, Debug, PartialEq)]
        pub struct $name(super::Validated);
        impl $name {
            fn fields() -> Vec<super::Field> { vec![$($spec),+] }
            pub fn from_dict(data: &serde_json::Value) -> Result<Self, super::ValidationError> {
                super::validate(data, &Self::fields()).map(Self)
            }
            pub fn to_dict(&self) -> serde_json::Value {
                self.0.dump.clone()
            }
            pub fn to_json(&self) -> std::string::String {
                let fields: Vec<_> = Self::fields().iter().map(|f| format!("{}:{}", serde_json::json!(f.0), crate::mir_core::canonical::canonical_json(&self.0.dump[f.0], Some(&[])))).collect();
                format!("{{{}}}", fields.join(","))
            }
        }
        impl serde::Serialize for $name {
            fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> { self.to_dict().serialize(serializer) }
        }
    };
}
pub(crate) use contract;
