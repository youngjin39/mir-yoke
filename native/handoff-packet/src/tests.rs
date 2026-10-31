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
