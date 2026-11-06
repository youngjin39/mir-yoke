//! Structured errors retain Python's permissive dataclass field values.
use crate::executor_local::{Error, JsonSyntax};
use crate::executor_policy_query::ascii_json_text;
use serde_json::{Value, json};
use std::io::{self, Write};
macro_rules! error_types {
    ($($variant:ident => $name:literal),+ $(,)?) => {
        #[derive(Clone, Copy, Debug, PartialEq, Eq)]
        pub enum ErrorType { $($variant),+ }
        impl ErrorType {
            pub const ALL: [Self; 7] = [$(Self::$variant),+];
            pub fn as_str(self) -> &'static str { match self { $(Self::$variant => $name),+ } }
        }
    };
}
error_types! {
    Precondition => "precondition", Transition => "transition", Policy => "policy",
    ToolFailure => "tool_failure", Schema => "schema", Interrupt => "interrupt", Unknown => "unknown",
}
#[derive(Clone, Debug, PartialEq)]
pub struct StructuredError {
    pub error_type: ErrorType,
    fields: Value,
}
impl StructuredError {
    pub fn from_dict(data: &Value) -> Result<Self, Error> {
        for key in ["type", "recoverable", "summary"] {
            if data.get(key).is_none() {
                return Err(Error::Invalid(format!("missing required field: {key}")));
            }
        }
        let repr = crate::executor_brief_render::python_value_repr(&data["type"]);
        let error_type = ErrorType::ALL
            .into_iter()
            .find(|t| data["type"].as_str() == Some(t.as_str()))
            .ok_or_else(|| Error::Invalid(format!("{repr} is not a valid ErrorType")))?;
        let fields = json!({"recoverable":data["recoverable"], "summary":data["summary"], "details_ref":data["details_ref"], "context":data["context"]});
        Ok(Self { error_type, fields })
    }
    pub fn from_json(text: &str) -> Result<Self, Error> {
        JsonSyntax::validate(text)?;
        Self::from_dict(&serde_json::from_str(text).map_err(Error::Json)?)
    }
    pub fn to_dict(&self) -> Value {
        let mut data = self.fields.clone();
        data["type"] = self.error_type.as_str().into();
        if let Value::Object(fields) = &mut data {
            fields.retain(|_, v| !v.is_null());
        }
        data
    }
    pub fn to_json(&self) -> String {
        let text = super::canonical::canonical_json(&self.to_dict(), Some(&[]));
        ascii_json_text(&text)
    }
    pub fn write_to(&self, writer: &mut impl Write, prefix: Option<&str>) -> io::Result<()> {
        let prefix = prefix.unwrap_or("[mir ERROR]");
        writeln!(writer, "{prefix} {}", self.to_json())
    }
}
pub fn emit_error_to_stderr(error: &StructuredError, prefix: Option<&str>) -> io::Result<()> {
    error.write_to(&mut io::stderr().lock(), prefix)
}
