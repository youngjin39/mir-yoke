use handoff_packet::mir_core::contracts::{
    agent_profile::AgentProfile, conductor_mode::ConductorMode,
};
use serde_json::{Value, json};
#[test]
fn frozen_models() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/w2/b01-contracts.json")).unwrap();
    let minimal = json!({"name":"agent","slug":"family","model":"sonnet","description":"d","system_prompt":"s","context_budget_tokens":1000});
    let mut full = minimal.clone();
    for (k, v) in json!({"role_binding":"reviewer","tools":["tool"],"forbidden_tools":["deny"],"temperature":2,"max_output_tokens":16000,"stop_sequences":["stop"],"allowed_files":["src/**"],"provenance":{"source":"ref"}}).as_object().unwrap() {
        full[k] = v.clone();
    }
    let exemptions = [
        (
            "AgentProfile.frozen",
            "Python setattr has no Rust operation",
        ),
        (
            "AgentProfile.delete",
            "Python delattr has no Rust operation",
        ),
    ];
    for (name, reason) in exemptions {
        assert!(fixture.get(name).is_some(), "{name}: {reason}");
    }
    let variants = json!({"model":["opus","haiku","invalid"],"role_binding":["conductor","planner","tester","invalid"],"context_budget_tokens":[999,200000,200001,"1000","bad"],"temperature":[-0.1,0,2.1,"0.5"],"max_output_tokens":[255,256,16001,"256"]});
    let (mut replayed, mut exempt, mut deferred) = (0, 0, 0);
    for (name, expected) in fixture.as_object().unwrap() {
        let (model, case) = name.split_once('.').unwrap();
        if ![
            "AgentProfile",
            "ConductorMode",
            "RouteDecision",
            "DiscordEvent",
            "ProviderResult",
        ]
        .contains(&model)
        {
            continue;
        }
        if ["RouteDecision", "DiscordEvent", "ProviderResult"].contains(&model) {
            deferred += 1; // Whole models deferred under the 320-line prefix allowance.
            continue;
        }
        if exemptions.iter().any(|(key, _)| key == name) {
            exempt += 1;
            continue;
        }
        let observed = if model == "ConductorMode" {
            if case == "values" {
                json!({"value":ConductorMode::ALL.map(|v| v.as_str())})
            } else {
                match ConductorMode::parse(if case == "invalid" { "invalid" } else { case }) {
                    Ok(v) => {
                        assert_eq!(serde_json::to_value(v).unwrap(), json!(v.as_str()));
                        json!({"value":v.as_str()})
                    }
                    Err(e) => json!({"error":e}),
                }
            }
        } else {
            let mut data = if ["full", "json"].contains(&case) || case.starts_with("default.") {
                full.clone()
            } else {
                minimal.clone()
            };
            if case == "missing" {
                data = json!({});
            } else if case == "extra" {
                data["unexpected"] = 1.into();
            } else if let Some(field) = case.strip_prefix("default.") {
                data.as_object_mut().unwrap().remove(field);
            } else if let Some(field) = case.strip_prefix("int_to_str.") {
                data[field] = 7.into();
            } else if !case.starts_with("fork.") && !["minimal", "full", "json"].contains(&case) {
                let (field, index) = case.split_once('.').unwrap();
                data[field] = variants[field][index.parse::<usize>().unwrap()].clone();
            }
            match AgentProfile::from_dict(&data) {
                Err(e) => json!({"error":e}),
                Ok(mut value) => {
                    if let Some(fork) = case.strip_prefix("fork.") {
                        let overrides = match fork {
                            "unchanged" => json!({}),
                            "valid" => json!({"name":"fork","temperature":1}),
                            "unvalidated" => json!({"context_budget_tokens":-1}),
                            "extra" => json!({"unexpected":1}),
                            _ => panic!("unmapped {name}"),
                        };
                        value = value.fork(&overrides);
                    }
                    assert_eq!(serde_json::to_value(&value).unwrap(), value.to_dict());
                    if case == "json" {
                        json!({"value":value.to_json()})
                    } else {
                        json!({"value":value.to_dict()})
                    }
                }
            }
        };
        assert_eq!(&observed, expected, "{name}");
        replayed += 1;
    }
    assert_eq!((replayed, exempt, deferred), (47, 2, 59));
    assert_eq!(replayed + exempt + deferred, 108);
}
