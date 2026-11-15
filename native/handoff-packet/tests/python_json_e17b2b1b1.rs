use handoff_packet::python_json::{Text, parse};
use serde_json::Value;
fn record() -> Value {
    serde_json::from_str(include_str!("fixtures/y-e17b2b1b1.json")).unwrap()
}
fn text(r: &Value) -> Text {
    parse(r["text"].as_str().unwrap())
        .unwrap()
        .as_text()
        .unwrap()
        .clone()
}
fn bytes(v: &Value) -> Vec<u8> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|n| n.as_u64().unwrap() as u8)
        .collect()
}
#[test]
fn codec_admission() {
    let r = record();
    assert_eq!(Text::from_wtf8(&bytes(&r["wtf8"])).unwrap(), text(&r));
    for e in r["errors"].as_array().unwrap() {
        assert_eq!(
            Text::from_wtf8(&bytes(&e["bytes"]))
                .unwrap_err()
                .to_string(),
            e["message"]
        );
    }
    assert!(Text::from_wtf8(&[]).unwrap().is_empty());
}
#[test]
fn codec_strip() {
    let r = record();
    assert_eq!(serde_json::json!(text(&r).strip().codepoints), r["strip"]);
    assert!(Text::from_wtf8(b" \x1c\x1f").unwrap().strip().is_empty());
}
#[test]
fn codec_concat() {
    let r = record();
    let suffix = parse(r#""\ud800\\ud800""#).unwrap();
    assert_eq!(
        serde_json::json!(text(&r).concat(suffix.as_text().unwrap()).codepoints),
        r["concat"]
    );
}
#[test]
fn codec_plain_render() {
    let r = record();
    assert_eq!(text(&r).render().unwrap(), bytes(&r["wtf8"]));
}
#[test]
fn codec_compact() {
    let r = record();
    assert_eq!(
        parse(r["value"].as_str().unwrap())
            .unwrap()
            .json_sorted(false),
        r["compact"]
    );
}
#[test]
fn codec_pretty() {
    let r = record();
    assert_eq!(
        parse(r["value"].as_str().unwrap())
            .unwrap()
            .json_sorted(true),
        r["pretty"]
    );
}
