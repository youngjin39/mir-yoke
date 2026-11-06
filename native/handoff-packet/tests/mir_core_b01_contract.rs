use handoff_packet::mir_core::{instance_id::InstanceIdResolver, tool_contract::*};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};

#[test]
fn frozen_contract_and_instance_records() {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/w2/b01.json")).unwrap();
    let base = json!({"idempotency_key":"k","precondition":"ready","dry_run":true,"side_effect_summary":"none"});
    let mut covered = BTreeSet::new();
    for (name, expected) in fixture.as_object().unwrap() {
        let observed = if let Some(case) = name.strip_prefix("contract.") {
            if let Some(key) = case.strip_prefix("key_") {
                let parts: &[&str] = match key {
                    "none" => &[],
                    "one" => &["write_file"],
                    "parts" => &["a", "b|c", ""],
                    "unicode" => &["\u{ba85}", "\u{e9}"],
                    _ => panic!("unmapped {name}"),
                };
                json!({"value":make_idempotency_key(parts)})
            } else {
                let mut data = base.clone();
                match case {
                    "minimal" | "from_json" => (),
                    "extra" => {
                        data["dry_run"] = false.into();
                        data["extra"] = json!({"z":1,"a":[1]});
                    }
                    "empty_extra" => data["extra"] = json!({}),
                    "summary_200" => data["side_effect_summary"] = "x".repeat(200).into(),
                    "summary_201" => data["side_effect_summary"] = "x".repeat(201).into(),
                    "summary_not_str" => data["side_effect_summary"] = 5.into(),
                    "missing_all" => data = json!({}),
                    "missing_precondition" => data = json!({"idempotency_key":"k"}),
                    "missing_dry_run" => data = json!({"idempotency_key":"k","precondition":"p"}),
                    "missing_summary" => {
                        data = json!({"idempotency_key":"k","precondition":"p","dry_run":false})
                    }
                    _ => panic!("unmapped {name}"),
                }
                let result = if case == "from_json" {
                    ToolContract::from_json(&data.to_string())
                } else {
                    ToolContract::from_dict(&data)
                };
                match result {
                    Ok(contract) => json!({"value":contract.to_json()}),
                    Err(error) => json!({"error":[error.kind(),error.to_string()]}),
                }
            }
        } else if let Some(case) = name.strip_prefix("instance.") {
            let temp = tempfile::tempdir().unwrap();
            let bodies: &[Option<&str>] = match case {
                "first_file" => &[Some("machine-1\n"), Some("machine-2")],
                "blank_then_second" => &[Some(" \n"), Some("machine-2\n"), Some("machine-3")],
                "missing_then_third" => &[None, None, Some("uuid-3")],
                "fallback"
                | "fallback_other_host"
                | "fallback_empty_node"
                | "fallback_no_migration" => &[None, None, None],
                _ => panic!("unmapped {name}"),
            };
            let paths = bodies
                .iter()
                .enumerate()
                .map(|(i, body)| {
                    let path = temp.path().join(format!("id-{i}"));
                    if let Some(body) = body {
                        std::fs::write(&path, body).unwrap();
                    }
                    path
                })
                .collect();
            let node = match case {
                "fallback_other_host" => "host-b",
                "fallback_empty_node" => "",
                _ => "host-a",
            };
            let migration = if case == "fallback_no_migration" {
                temp.path()
                    .join("engine/memory/migrations/001_claude_memory_schema.sql")
            } else {
                Path::new(env!("CARGO_MANIFEST_DIR")).join(
                    "../../src/mir/core/engine/memory/migrations/001_claude_memory_schema.sql",
                )
            };
            let mut resolver = InstanceIdResolver::new(paths, node.into(), migration);
            json!({"value":resolver.current_instance_id().unwrap()})
        } else {
            continue;
        };
        assert_eq!(&observed, expected, "{name}");
        covered.insert(name);
    }
    assert_eq!(covered.len(), 22);
}

#[test]
fn injected_schema_bytes_and_cache() {
    let temp = tempfile::tempdir().unwrap();
    let migration = temp.path().join("schema.sql");
    std::fs::write(&migration, b"schema\r\n").unwrap();
    let id = temp.path().join("id");
    let mut resolver = InstanceIdResolver::new(vec![id.clone()], "host-a".into(), migration);
    // Independent SHA256 of b"host-aschema\r\n", including CRLF bytes.
    assert_eq!(
        resolver.current_instance_id().unwrap(),
        "52f1b0d3ac3743421e99e14f8d589d24f6e7c8207a7e504a96380fb0f3c8877e"
    );
    std::fs::write(&id, "new-id").unwrap();
    assert_ne!(resolver.current_instance_id().unwrap(), "new-id");
    assert_eq!(resolver.cache_info(), (1, 1, 1, 1));
    resolver.cache_clear();
    assert_eq!(resolver.cache_info(), (0, 0, 1, 0));
    assert_eq!(resolver.current_instance_id().unwrap(), "new-id");
    resolver.cache_clear();
    std::fs::write(&id, [0xff]).unwrap();
    assert_eq!(
        resolver.current_instance_id().unwrap_err().kind(),
        "UnicodeDecodeError"
    );
    assert_eq!(resolver.cache_info(), (0, 1, 1, 0));
    std::fs::write(&id, "recovered").unwrap();
    assert_eq!(resolver.current_instance_id().unwrap(), "recovered");
    for summary in [json!(true), Value::Null, json!(1.5)] {
        let error = ToolContract::from_dict(&json!({"idempotency_key":1,"precondition":null,"dry_run":"yes","side_effect_summary":summary})).unwrap_err();
        assert_eq!(error.kind(), "TypeError");
    }
    let contract = ToolContract::from_json(r#"{"idempotency_key":1,"precondition":null,"dry_run":"yes","side_effect_summary":"\ud83d\ude80","extra":{},"ignored":1}"#).unwrap();
    assert!(contract.to_json().contains(r"\ud83d\ude80"));
    assert!(!contract.to_json().contains("ignored"));
}
