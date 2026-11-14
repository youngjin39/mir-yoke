fn main() {
    #[cfg(unix)]
    std::process::exit(handoff_packet::user_runtime_cli::run(
        &std::env::args_os().skip(1).collect::<Vec<_>>(),
    ));
    #[cfg(not(unix))]
    {
        eprintln!("error: runtime home identity requires Unix");
        std::process::exit(2);
    }
}
