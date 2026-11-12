//! Cancel uses the owned query family without a Python forward or signal route.
#[test]
fn cancel_has_no_decline_child_or_python_forwarding() {
    let source = include_str!("../src/executor_status.rs");
    assert!(source.contains("raw[index] == \"cancel\""));
    assert!(source.contains("registry.cancel(&job)"));
    for forbidden in [
        "executor_protocol::decline",
        "executor_protocol::claim",
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
