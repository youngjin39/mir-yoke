//! Ordered field specs mirror the Python reference class.
use super::Kind::*;
use serde_json::json;
super::contract!(ProviderResult;
    ("status", Literal(&["success", "failed", "timeout", "cancelled"]), None, None, None),
    ("exit_code", Int, None, None, None),
    ("stdout_tail", String, None, None, Some(16384)),
    ("stderr_tail", String, None, None, Some(16384)),
    ("artifacts", Tuple(&AnyDict), Some(json!([])), None, None),
    ("tokens_used", Dict(&Int), Some(json!({})), None, None),
    ("wall_seconds", Float, None, Some((0.0, f64::INFINITY)), None),
    ("session_uuid", String, None, None, None),
    ("provider", String, None, None, None),
    ("argv_snapshot", Tuple(&String), Some(json!([])), None, None),
);
impl ProviderResult {
    /// Parsed duration, including the reference's positive infinity.
    pub fn wall_seconds(&self) -> f64 {
        self.0.floats["wall_seconds"]
    }
}
