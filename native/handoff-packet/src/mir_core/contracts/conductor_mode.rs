//! Declaration order matches the Python StrEnum iteration contract.
use serde_json::{Value, json};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConductorMode {
    Normal,
    MetaRequested,
    MetaApproved,
    MetaApplying,
}
impl ConductorMode {
    pub const ALL: [Self; 4] = [
        Self::Normal,
        Self::MetaRequested,
        Self::MetaApproved,
        Self::MetaApplying,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Normal => "normal",
            Self::MetaRequested => "meta_requested",
            Self::MetaApproved => "meta_approved",
            Self::MetaApplying => "meta_applying",
        }
    }
    pub fn parse(value: &str) -> Result<Self, Value> {
        Self::ALL
            .into_iter()
            .find(|v| v.as_str() == value)
            .ok_or_else(|| {
                let repr = crate::executor_brief_render::python_value_repr(&json!(value));
                json!(["ValueError", format!("{repr} is not a valid ConductorMode")])
            })
    }
}
impl serde::Serialize for ConductorMode {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(self.as_str())
    }
}
