//! Result shares the status parser/codec and cannot launch a fallback process.
#[test]
fn result_has_no_decline_child_or_python_forwarding() {
    let source = include_str!("../src/executor_status.rs");
    assert!(source.contains("raw[index] == \"result\""));
    assert!(source.contains("if args.result"));
    for forbidden in [
        "executor_protocol::decline",
        "tools.mir_executor.cli",
        "cli_jobs",
        "Command::new",
        "LocalBridge",
        "return 64",
    ] {
        assert!(!source.contains(forbidden), "{forbidden}");
    }
    let entry = include_str!("../src/executor_query.rs");
    assert!(
        entry.find("executor_status::owns").unwrap()
            < entry.find("parse(std::env::args_os()").unwrap()
    );
}
