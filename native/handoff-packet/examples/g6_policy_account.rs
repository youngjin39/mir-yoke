//! G6 test driver: inject an account home into the unchanged policy query library.
use std::{collections::BTreeMap, env, ffi::OsString, path::PathBuf};

fn main() {
    let args: Vec<OsString> = env::args_os().skip(3).collect(); // --home-root ROOT
    let environment: BTreeMap<String, String> = env::vars().collect();
    let account = PathBuf::from(&environment["G6_POLICY_ACCOUNT_HOME"]);
    let output = handoff_packet::executor_policy_query::query(
        &args,
        &env::current_dir().unwrap(),
        &account,
        &environment,
    );
    let Some((stdout, stderr, code)) = output else {
        std::process::exit(64)
    };
    print!("{stdout}");
    eprint!("{stderr}");
    std::process::exit(code);
}
