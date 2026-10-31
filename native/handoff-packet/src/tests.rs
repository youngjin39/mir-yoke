use super::*;
#[test]
fn word_specialization_cache_is_separate() {
    for text in ["agent", "agent\u{d55c}", "agent\u{301}", "agent"] {
        assert_eq!(
            has(r"\bagent\b", text, false).unwrap(),
            text != "agent\u{d55c}"
        );
    }
    for text in ["\u{d55c}", "a", "\u{d55c}"] {
        assert!(has(r"^\w+$", text, false).unwrap());
    }
}
#[test]
fn imperative() {
    assert!(detect("Write a handoff for another agent.").unwrap());
}
#[test]
fn korean() {
    // Korean "please write a handoff for another agent."
    assert!(detect("\u{b2e4}\u{b978} \u{c5d0}\u{c774}\u{c804}\u{d2b8} \u{d578}\u{b4dc}\u{c624}\u{d504}\u{b97c} \u{c791}\u{c131}\u{d574} \u{c8fc}\u{c138}\u{c694}.").unwrap());
}
#[test]
fn received() {
    assert!(recipient("Qualified target: yoke:item\nPins: supplied\nMay: read").unwrap());
}
#[test]
fn command_ban() {
    assert!(restricted("No commands.").unwrap());
    assert!(restricted("May not:\r\n- run commands").unwrap());
    assert!(restricted(&format!("No commands.\n{}", "\u{d55c}".repeat(360_000))).unwrap());
    let owner = owner_sections(
        "May: read\nMay not: edit files\nExclude: `private`; other\nSources: src/a.py",
    )
    .unwrap();
    assert_eq!(owner.may, "read");
    assert_eq!(owner.sources, "src/a.py");
    assert!(owner.explicit_authority);
    assert_eq!(owner.excluded, vec!["private", "other"]);
    assert!(files_restricted(&owner).unwrap());
    assert!(!restricted("May not: run commands except `pwd`").unwrap());
    assert!(
        !files_restricted(&owner_sections("May not: edit files outside src/").unwrap()).unwrap()
    );
}
#[test]
fn namespaced_tool() {
    assert_eq!(tool_kind("functions.Bash").unwrap(), "bash");
}
#[test]
fn interpreter() {
    assert_eq!(tool_kind("mcp__python_repl__exec").unwrap(), "python_repl");
}
#[test]
fn nested_call() {
    assert_eq!(
        code_shell_calls("tools.exec_command({cmd:'pwd'})").unwrap()[0].1["command"],
        "pwd"
    );
}
#[test]
fn dynamic_call() {
    assert_eq!(code_shell_calls("tools.js(options)").unwrap().len(), 1);
}
#[test]
fn sha256_matches_reference_at_padding_boundaries() {
    // Expected values come from Python hashlib over bytes (i * 7) % 251.
    for (len, expected) in [
        (
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        (
            1,
            "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
        ),
        (
            55,
            "8af594de0e003fdee5c8bb088216c824349b4137070f559574f4a4bddd27b714",
        ),
        (
            56,
            "db81bc2bfd43620591df192139062da77d4c376f1888ea3d2190bd07c8d901f9",
        ),
        (
            57,
            "4d95ad65f5ec430c9a97ae9243b87d4d6fa0c474288c93cecfbfe9257e711780",
        ),
        (
            63,
            "bd535b38bf0d0d1a09d370b7e34b2696cea3767801a45d5611a4aaa6954e8527",
        ),
        (
            64,
            "292be91abe8c0909fe3d26575af5755eee74d23816dc68c3ba41765136967654",
        ),
        (
            65,
            "ba65aedf7884642499a59ae124894611d986cf429e69f569488048af3a99e25a",
        ),
        (
            119,
            "d367ab298e74477421127b0b448667c37c006c636f5738f081c39388756e5fad",
        ),
        (
            120,
            "be7beb9c82089eb08da8fe6eb30c13b9d56869014e228a8c3eb0fdfe832efab2",
        ),
        (
            127,
            "770cba7b80c7615a327db5812ccd3f80895d801b587448fcd0b2c1a10f5c88a3",
        ),
        (
            128,
            "cb5311e1d7aa8e11d6af7081f3ffc3e4efa008c7483a1a791fe170bf37546ba7",
        ),
        (
            1000,
            "59425e4412e296fc74736673ce067027f384203f59c0d2c3e6be7b13347b3ffc",
        ),
    ] {
        let data: Vec<u8> = (0..len).map(|i| ((i * 7) % 251) as u8).collect();
        assert_eq!(crate::digest::sha256(&data), expected, "length {len}");
    }
}
