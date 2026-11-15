// Windows witnesses captured from the pinned Python, never from native output.
#[cfg(windows)]
pub fn record(route: &str) -> serde_json::Value {
    let capture: serde_json::Value =
        serde_json::from_str(include_str!("../fixtures/wt-path-records-windows.json")).unwrap();
    capture["records"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["route"] == route)
        .unwrap()
        .clone()
}

pub fn root_token(text: &str, root: &std::path::Path, token: &str) -> String {
    let raw = root.to_str().unwrap();
    text.replace(&raw.replace('\\', "\\\\"), token)
        .replace(raw, token)
}
