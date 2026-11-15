// Select reference text-stream bytes; never pass actual output or file contents here.
pub fn expected_text(text: &str, windows: bool) -> String {
    text.replace('\n', if windows { "\r\n" } else { "\n" })
}

#[test]
fn expected_text_selects_only_platform_newlines() {
    let text = "usage: mir\n\nUnicode: —\n";
    assert_eq!(expected_text(text, false), text);
    assert_eq!(
        expected_text(text, true),
        "usage: mir\r\n\r\nUnicode: —\r\n"
    );
    assert_eq!(expected_text("", true), "");
}
