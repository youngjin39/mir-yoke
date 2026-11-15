// Frozen Windows Python 3.12.13 capture; pins are embedded in the fixture.
// Legacy hook-import failures are not a native facade oracle.
pub fn record(route: &str, option: &str) -> serde_json::Value {
    let capture: serde_json::Value =
        serde_json::from_str(include_str!("../fixtures/windows_executor_text.json")).unwrap();
    assert_eq!(capture["platform"], "win32");
    capture["records"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["route"] == route && r["option"] == option)
        .unwrap()
        .clone()
}

pub fn bytes(record: &serde_json::Value, stream: &str) -> Vec<u8> {
    assert_eq!(record["native_gate_covered"], true);
    let hex = record[format!("{stream}_hex")].as_str().unwrap();
    (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
        .collect()
}
