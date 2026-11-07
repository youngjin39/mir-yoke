//! Reached circuit-breaker detector from tools.autonomous_loop.loop.
use serde_json::Value;
#[derive(Debug, PartialEq, Eq)]
pub struct TriggerResult {
    pub trigger_id: &'static str,
    pub reason: &'static str,
    pub should_request_approval: bool,
}
pub fn trigger_circuit_breaker(state: &Value) -> Option<TriggerResult> {
    (state["state"] == "open").then_some(TriggerResult {
        trigger_id: "circuit_breaker",
        reason: "circuit breaker state=open",
        should_request_approval: true,
    })
}
