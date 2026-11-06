use handoff_packet::mir_core::contracts::{
    compiled_job::CompiledJob,
    dispatch_brief::{DispatchBrief, DispatchBriefSourceRefs},
    gate::{GateBlocked, PathFingerprint, STANDARD_CODES, ValidationResult},
    task_spec::TaskSpec,
};
use serde_json::{Value, json};
// Inputs only: captured from the unchanged Python CASES closures, never port outputs.
#[test]
fn remaining_contracts() {
    let oracle: Value =
        serde_json::from_str(include_str!("fixtures/w2/b01-contracts.json")).unwrap();
    let inputs: Value = serde_json::from_str(include_str!("fixtures/w2/b01-inputs.json")).unwrap();
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in oracle.as_object().unwrap() {
        let (model, case) = name.split_once('.').unwrap();
        if ![
            "TaskSpec",
            "CompiledJob",
            "DispatchBrief",
            "DispatchBriefSourceRefs",
            "PathFingerprint",
            "ValidationResult",
            "GateBlocked",
        ]
        .contains(&model)
        {
            continue;
        }
        if ["frozen", "delete", "automatic_finalization_allowed"].contains(&case) {
            // Python setattr/delattr and object attributes have no Rust object-surface equivalent.
            exempt += 1;
            continue;
        }
        let observed = replay(model, case, &inputs[name]);
        assert_eq!(&observed, expected, "{name}");
        replayed += 1;
    }
    assert_eq!((replayed, exempt), (162, 13));
    assert_eq!(
        replayed + exempt + 161 + 8,
        oracle.as_object().unwrap().len()
    );
}
fn replay(model: &str, case: &str, data: &Value) -> Value {
    if model == "GateBlocked" {
        let value = GateBlocked::new(
            if case == "default" {
                "policy_deny"
            } else {
                "custom"
            },
            if case == "default" { "" } else { "detail" },
        );
        let mut codes = STANDARD_CODES.to_vec();
        codes.sort();
        return json!({"value":match case { "default" => json!(value.to_string()), "full" => json!([value.code, value.detail, value.to_string()]), "codes" => json!(codes), _ => panic!("unknown gate case") }});
    }
    macro_rules! run {
        ($kind:ty) => {
            <$kind>::from_dict(data).map(|v| {
                assert_eq!(serde_json::to_value(&v).unwrap(), v.to_dict());
                if ["json", "json_unicode"].contains(&case) {
                    json!(v.to_json())
                } else {
                    v.to_dict()
                }
            })
        };
    }
    let result = match model {
        "TaskSpec" => run!(TaskSpec),
        "CompiledJob" => run!(CompiledJob),
        "DispatchBrief" => run!(DispatchBrief),
        "DispatchBriefSourceRefs" => run!(DispatchBriefSourceRefs),
        "PathFingerprint" => run!(PathFingerprint),
        "ValidationResult" => run!(ValidationResult),
        _ => panic!("unknown model {model}"),
    };
    match result {
        Ok(value) => json!({"value":value}),
        Err(error) => json!({"error":error}),
    }
}
#[test]
fn field_errors_skip_after_validator() {
    let inputs: Value = serde_json::from_str(include_str!("fixtures/w2/b01-inputs.json")).unwrap();
    let oracle: Value =
        serde_json::from_str(include_str!("fixtures/w2/b01-contracts.json")).unwrap();
    let mut input = inputs["DispatchBrief.coerce.task_id.0"].clone();
    input["version"] = json!(2);
    assert_eq!(
        replay("DispatchBrief", "minimal", &input),
        oracle["DispatchBrief.coerce.task_id.0"]
    );
}
