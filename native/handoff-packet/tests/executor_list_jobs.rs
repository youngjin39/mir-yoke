//! List queries share owned parsing and cannot launch a Python fallback.
#[test]
fn list_jobs_has_no_decline_child_or_python_forwarding() {
    let source = include_str!("../src/executor_status.rs");
    assert!(source.contains("raw[index] == \"list-jobs\""));
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
