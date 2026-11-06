//! Ordered field specs mirror the Python reference class.
use super::Kind::*;
use serde_json::json;
super::contract!(TaskSpec;
    ("intent", Min(&String, 1), None, None, Some(8000)),
    ("scope", Min(&Tuple(&String), 1), None, None, None),
    ("success_criteria", Min(&Tuple(&String), 1), None, None, None),
    ("role_binding", Pattern("^(executor|reviewer|planner|tester)$"), None, None, None),
    ("budget", Dict(&Int), None, None, None),
    ("target_files", Tuple(&AnyDict), Some(json!([])), None, None),
    ("expected_symbols", Tuple(&String), Some(json!([])), None, None),
    ("required_tools", Tuple(&String), Some(json!([])), None, None),
    ("stack", Nullable(&String), Some(json!(null)), None, None),
    ("parent_task_id", Nullable(&Int), Some(json!(null)), None, None),
    ("fingerprint", Nullable(&String), Some(json!(null)), None, None),
    ("phase_tag", Nullable(&String), Some(json!(null)), None, None),
    ("extensions", AnyDict, Some(json!({})), None, None),
);
