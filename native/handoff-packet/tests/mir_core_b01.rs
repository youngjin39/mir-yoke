use handoff_packet::executor_local::LocalConfig;
use handoff_packet::mir_core::{canonical::*, structured_error::*};
use serde_json::{Value, json};
#[test]
fn frozen_records() {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/w2/b01.json")).unwrap();
    let cases = r#"canonical.sorted_nested|{"z":1,"a":{"y":[3,{"b":1,"a":2}],"x":null}}
canonical.unicode_escapes|{"s":"\uba85\u0301\n\t\"\\\u0000\u007f\u2028\ud83d\ude80"}
canonical.numbers|{"i":1,"f":1.0,"nz":-0.0,"big":1e16,"small":1.5e-7,"huge":18446744073709551616,"neg":-3,"third":0.3333333333333333}
canonical.non_finite|{"nan":NaN,"inf":Infinity,"ninf":-Infinity}
canonical.bool_null|{"t":true,"f":false,"n":null}
canonical.omit_default|{"b":2,"signature":"x","nested":{"signature":"kept"}}
canonical.omit_custom|{"b":2,"signature":"x","drop":1}
canonical.omit_none|{"signature":"x"}
canonical.empty|{}
error.minimal|{"type":"policy","recoverable":false,"summary":"blocked"}
error.full|{"type":"tool_failure","recoverable":true,"summary":"retry","details_ref":"log:1","context":{"z":1,"a":"\u00e9"}}
error.empty_context|{"type":"schema","recoverable":true,"summary":"s","context":{},"details_ref":""}
error.non_bool_recoverable|{"type":"unknown","recoverable":"yes","summary":3}
error.ignored_extra|{"type":"interrupt","recoverable":false,"summary":"s","other":1}
error.missing_all|{}
error.missing_recoverable|{"type":"policy","summary":"s"}
error.missing_summary|{"type":"policy","recoverable":false}
error.invalid_type|{"type":"bad","recoverable":false,"summary":"s"}
error.from_json|{"summary":"s","type":"transition","recoverable":true}
error.from_json_invalid|{
error.types|{}
error.emit_default|{"type":"policy","recoverable":false,"summary":"blocked"}
error.emit_prefix|{"type":"policy","recoverable":false,"summary":"blocked"}"#;
    let mut covered = std::collections::BTreeSet::new();
    for line in cases.trim().lines() {
        let (name, input) = line.split_once('|').unwrap();
        covered.insert(name);
        let observed = if name.starts_with("canonical.") {
            let config = LocalConfig::parse(input).unwrap();
            let omit = match name {
                "canonical.omit_custom" => Some(&["drop"][..]),
                "canonical.omit_none" => Some(&[][..]),
                _ => None,
            };
            let value = Value::Object(config.raw().clone());
            let text = canonical_json_with_numbers(&value, omit, config.numeric_tag());
            json!({"value":text})
        } else if name == "error.types" {
            json!({"value":ErrorType::ALL.map(ErrorType::as_str)})
        } else {
            match StructuredError::from_json(input) {
                Ok(error) => {
                    let text = if name.starts_with("error.emit_") {
                        let mut bytes = Vec::new();
                        let prefix = (name == "error.emit_prefix").then_some("[hook]");
                        error.write_to(&mut bytes, prefix).unwrap();
                        String::from_utf8(bytes).unwrap()
                    } else {
                        error.to_json()
                    };
                    json!({"value":text})
                }
                Err(error) => json!({"error":[error.kind(),error.to_string()]}),
            }
        };
        assert_eq!(observed, fixture[name], "{name}");
    }
    for (name, reason) in [
        ("canonical.int_keys", "non-string keys"),
        ("canonical.mixed_keys", "non-string keys"),
        ("canonical.model", "Pydantic model"),
        ("canonical.tuple_value", "Python tuple"),
        ("canonical.set_value", "Python set"),
        ("canonical.pairs", "Python pairs coercion"),
    ] {
        assert!(fixture.get(name).is_some(), "{name}: {reason}");
        covered.insert(name);
    }
    let keys = fixture.as_object().unwrap().keys().map(String::as_str);
    let scoped = keys.filter(|k| k.starts_with("canonical.") || k.starts_with("error."));
    assert_eq!(covered, scoped.collect());
}
