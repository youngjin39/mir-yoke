use serde_json::{Value, json};

// Only direct-call observations become provider/hook expectations. Console
// CRLF bytes remain frozen separately and are never used as direct-call text.
pub fn select(mut common: Value, consumer: &str, windows: bool) -> Value {
    if !windows {
        return common;
    }
    let capture: Value =
        serde_json::from_str(include_str!("../fixtures/unify2_c_recursion_windows.json")).unwrap();
    let key = if consumer == "provider" {
        "records"
    } else {
        "cases"
    };
    let records = common[key].as_array_mut().unwrap();
    for record in capture[consumer]["records"].as_array().unwrap() {
        if record["route"] == "console" {
            continue;
        }
        let name = record["name"].as_str().unwrap().split_once('.').unwrap().1;
        let exception = &record["exception"];
        let selected = if consumer == "provider" {
            let (code, stderr) = if !exception.is_null() {
                (
                    1,
                    format!(
                        "{}: {}\n",
                        exception["class"].as_str().unwrap(),
                        exception["message"].as_str().unwrap()
                    ),
                )
            } else if record["result"].as_array().unwrap().is_empty() {
                (0, String::new())
            } else {
                (
                    2,
                    format!(
                        "runtime manifest error: {}\n",
                        record["result"][0].as_str().unwrap()
                    ),
                )
            };
            json!({"name":name,"body_hex":record["input"]["tokenized_hex"],
                "code":code,"stderr":stderr})
        } else {
            json!({"name":name,"input_kind":"file",
                "bytes_hex":record["input"]["tokenized_hex"],
                "kind":exception["class"],"message":exception["message"]})
        };
        if let Some(existing) = records.iter_mut().find(|r| r["name"] == name) {
            *existing = selected;
        } else {
            records.push(selected);
        }
    }
    common
}

#[test]
fn windows_recursion_selector_is_strict() {
    let provider: Value = serde_json::from_str(include_str!(
        "../../../../tests/fixtures/runtime_manifest_verify_1324a3c.json"
    ))
    .unwrap();
    let brief: Value = serde_json::from_str(include_str!(
        "../../../../tests/fixtures/yoke_local_brief.json"
    ))
    .unwrap();
    for (common, consumer, key, witness) in [
        (provider, "provider", "records", "deep-extra"),
        (brief, "brief", "cases", "json_recursion_9996"),
    ] {
        assert_eq!(select(common.clone(), consumer, false), common);
        let windows = select(common.clone(), consumer, true);
        let records = windows[key].as_array().unwrap();
        let selected = records.iter().find(|r| r["name"] == witness).unwrap();
        if consumer == "provider" {
            assert_eq!(selected["code"], 1, "Windows deep-extra must refuse");
        } else {
            assert_eq!(selected["kind"], "RecursionError");
        }
        let extra = if consumer == "provider" { 16 } else { 8 };
        assert_eq!(records.len(), common[key].as_array().unwrap().len() + extra);
        for original in common[key].as_array().unwrap() {
            if !original["name"].as_str().unwrap().starts_with("depth-")
                && original["name"] != "deep-extra"
                && !original["name"]
                    .as_str()
                    .unwrap()
                    .starts_with("json_recursion_")
            {
                assert!(records.contains(original));
            }
        }
    }
}
