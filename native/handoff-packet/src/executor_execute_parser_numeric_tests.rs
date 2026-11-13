use super::*;

#[test]
fn direct_numeric_parser_matches_frozen_python_reference() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../tests/fixtures/executor_direct_numeric_reference.json"
    ))
    .unwrap();
    let mut mismatches = Vec::new();
    for (index, record) in fixture["records"].as_array().unwrap().iter().enumerate() {
        let argv = record["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| OsString::from(value.as_str().unwrap()))
            .collect::<Vec<_>>();
        let flag = record["argv"][1]
            .as_str()
            .unwrap()
            .split('=')
            .next()
            .unwrap();
        let actual = parse(&argv, Path::new("/synthetic"));
        let matched = match actual {
            Parsed::Args(args) if record["code"] == 0 => {
                let value = &args[flag[2..].replace('-', "_")];
                let text = if let Some(raw) = value["__native_integer"].as_str() {
                    raw.to_owned()
                } else if let Some(raw) = value["__native_float"].as_str() {
                    raw.trim().to_ascii_lowercase().replace("+infinity", "inf")
                } else if flag == "--stall-timeout" {
                    crate::python_json::Number {
                        token: value.to_string(),
                    }
                    .py_str()
                } else {
                    value.to_string()
                };
                text == record["value"].as_str().unwrap()
            }
            Parsed::Output {
                text, code, error, ..
            } => {
                code == record["code"].as_i64().unwrap() as i32
                    && error
                    && text == record["stderr"].as_str().unwrap_or("")
            }
            _ => false,
        };
        if !matched {
            mismatches.push(format!("record {index} {flag}"));
        }
    }
    assert!(
        mismatches.is_empty(),
        "numeric reference mismatches: {mismatches:?}"
    );
}
