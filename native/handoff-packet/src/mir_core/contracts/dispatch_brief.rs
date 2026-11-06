//! Ordered field specs and after-validator mirror the Python reference class.
use super::Kind::*;
use serde_json::{Value, json};
super::contract!(DispatchBriefSourceRefs;
    ("task_spec", Min(&String, 1), None, None, None),
    ("plan", String, Some(json!("tasks/plan.md")), None, None),
    ("phase", Min(&String, 1), None, None, None),
);
super::contract!(DispatchBrief;
    ("version", Int, Some(json!(1)), None, None),
    ("task_id", Min(&String, 1), None, None, None),
    ("phase_id", Nullable(&String), Some(json!(null)), None, None),
    ("slice_id", Min(&String, 1), None, None, None),
    ("target_agent", Min(&String, 1), None, None, None),
    ("user_intent", Min(&String, 1), None, None, None),
    ("expanded_goal", Min(&String, 1), None, None, None),
    ("owned_scope", Min(&Tuple(&String), 1), None, None, None),
    ("out_of_scope", Tuple(&String), Some(json!([])), None, None),
    ("verification_commands", Min(&Tuple(&String), 1), None, None, None),
    ("stop_conditions", Min(&Tuple(&String), 1), None, None, None),
    ("handoff_refs", Tuple(&String), Some(json!([])), None, None),
    ("tdd_change_refs", Tuple(&String), Some(json!([])), None, None),
    ("resume_state_ref", Min(&String, 1), None, None, None),
    ("source_refs", Model("DispatchBriefSourceRefs", DispatchBriefSourceRefs::fields), None, None, None)
    ; after validate_contract
);
fn validate_contract(data: &Value) -> Result<(), std::string::String> {
    let expected = format!(
        "tasks/dispatch/{}/{}.json",
        data["task_id"].as_str().unwrap_or_default(),
        data["slice_id"].as_str().unwrap_or_default()
    );
    let error = if data["version"] != 1 {
        Some("DispatchBrief.version must be 1".into())
    } else if data["resume_state_ref"] != expected {
        let expected = crate::executor_brief_render::python_value_repr(&json!(expected));
        Some(format!(
            "DispatchBrief.resume_state_ref must match {expected}"
        ))
    } else if data["source_refs"]["plan"] != "tasks/plan.md" {
        Some("DispatchBrief.source_refs.plan must be 'tasks/plan.md'".into())
    } else {
        None
    };
    error.map_or(Ok(()), Err)
}
