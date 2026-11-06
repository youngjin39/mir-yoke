use handoff_packet::mir_core::contracts::{
    agent_profile::AgentProfile, conductor_mode::ConductorMode, discord_event::DiscordEvent,
    provider_result::ProviderResult, route_decision::RouteDecision,
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
    let (mut replayed, mut exempt, mut records) = (0, 0, 0);
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
        records += 1;
        if exemptions.iter().any(|(key, _)| key == name) || ["frozen", "delete"].contains(&case) {
            // Python setattr/delattr have no operation on private Rust storage.
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
            if model != "AgentProfile" {
                data = json!({"RouteDecision":{"type":null,"mode":"deterministic","signals":{"file":"true"},"executor_provider":"provider","reviewer_provider":null},"DiscordEvent":{"chat_id":"chat","message_id":"message","user":"agent","user_id":"id","timestamp":"time","content":"hello"},"ProviderResult":{"status":"success","exit_code":0,"stdout_tail":"","stderr_tail":"","wall_seconds":0,"session_uuid":"session","provider":"provider"}})[model].clone();
                if ["full", "json"].contains(&case) || case.starts_with("default.") {
                    let extra = json!({"RouteDecision":{"type":"feature","mode":"supervisor_needed","reviewer_provider":"reviewer"},"DiscordEvent":{"attachments":[{"path":"asset"}],"reply_to":"parent","source":"other"},"ProviderResult":{"artifacts":[{"path":"asset"}],"tokens_used":{"input":"2"},"argv_snapshot":["tool"],"exit_code":"1","wall_seconds":"1.5"}})[model].clone();
                    data.as_object_mut()
                        .unwrap()
                        .extend(extra.as_object().unwrap().clone());
                }
            }
            if case == "coerce.wall_seconds_inf" {
                data["wall_seconds"] = json!("inf");
                let value = ProviderResult::from_dict(&data).unwrap();
                let n = value.wall_seconds();
                assert!(value.to_dict()["wall_seconds"].is_null());
                assert!(n.is_infinite() && n.is_sign_positive());
                assert_eq!(expected, &json!({"value":"inf"}));
                replayed += 1;
                continue;
            }
            if let Some(coerce) = case.strip_prefix("coerce.") {
                let (field, index) = coerce.rsplit_once('.').unwrap();
                let table = json!({"AgentProfile":{"tools":[5,"tool",[1],null,["a","b"]],"provenance":[{"a":1},[],null,{"a":null}],"context_budget_tokens":[1500.0,1500.5,true," 1500 ",null,"1_000","1e3"],"temperature":[true,null,"bad"," 1 ","inf",1],"name":[null,["x"],1.5,true]},"RouteDecision":{"signals":[{"f":1},{"f":0},{"f":2},{"f":"yes"},{"f":"on"},{"f":null},{"f":1.0},[]],"reviewer_provider":[5,null]},"DiscordEvent":{"attachments":[[1],["x"],[{}],{"path":"a"},null,"ab"],"reply_to":[5,null]},"ProviderResult":{"exit_code":[1.0,1.5,true," 2 ",null],"tokens_used":[{"a":"x"},{"a":1.5},{"a":true},[]],"wall_seconds":[true," 1.5 "],"argv_snapshot":[[1],"ab",null],"stdout_tail":[null,5]}})[model].clone();
                data[field] = table[field][index.parse::<usize>().unwrap()].clone();
            } else if case == "missing" {
                data = json!({});
            } else if case == "extra" {
                data["unexpected"] = 1.into();
            } else if let Some(field) = case.strip_prefix("default.") {
                data.as_object_mut().unwrap().remove(field);
            } else if let Some(field) = case.strip_prefix("int_to_str.") {
                data[field] = 7.into();
            } else if !case.starts_with("fork.") && !["minimal", "full", "json"].contains(&case) {
                let (field, index) = case.split_once('.').unwrap();
                let other = json!({"type":["bugfix","refactor","security","research","unknown","bad"],"mode":["bad"],"signals":[{"file":"false"},{"file":"bad"}],"status":["failed","timeout","cancelled","invalid"],"wall_seconds":[-0.1,"bad"],"exit_code":["bad"],"stdout_tail":["x".repeat(16384),"x".repeat(16385)],"stderr_tail":["x".repeat(16384),"x".repeat(16385)]});
                data[field] = if model == "AgentProfile" {
                    &variants
                } else {
                    &other
                }[field][index.parse::<usize>().unwrap()]
                .clone();
            }
            if model != "AgentProfile" {
                let result = match model {
                    "RouteDecision" => {
                        RouteDecision::from_dict(&data).map(|v| (v.to_dict(), v.to_json()))
                    }
                    "DiscordEvent" => {
                        DiscordEvent::from_dict(&data).map(|v| (v.to_dict(), v.to_json()))
                    }
                    _ => ProviderResult::from_dict(&data).map(|v| (v.to_dict(), v.to_json())),
                };
                let observed = match result {
                    Ok((dict, text)) => {
                        json!({"value":if case == "json" { json!(text) } else { dict }})
                    }
                    Err(e) => json!({"error":e}),
                };
                assert_eq!(&observed, expected, "{name}");
                replayed += 1;
                continue;
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
    assert_eq!((replayed, exempt), (161, 8));
    assert_eq!(replayed + exempt, records);
}
