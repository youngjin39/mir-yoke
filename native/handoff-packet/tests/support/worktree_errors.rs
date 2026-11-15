// The captured OS text stays frozen; std::io::Error uses this runtime's
// FormatMessageW locale. CPython strips trailing spaces, CR/LF and periods.
#[cfg(windows)]
pub fn frozen(name: &str, path: &std::path::Path) -> String {
    let text = include_str!("../fixtures/executor_worktree_errors-windows.json");
    let corpus: serde_json::Value = serde_json::from_str(text).unwrap();
    let record = &corpus["records"][name];
    let prefix = if let Some(code) = record["winerror"].as_i64() {
        let os = std::io::Error::from_raw_os_error(code as i32).to_string();
        let suffix = format!(" (os error {code})");
        format!(
            "[WinError {code}] {}",
            os.strip_suffix(&suffix)
                .unwrap_or(&os)
                .trim_end_matches([' ', '\r', '\n', '.'])
        )
    } else {
        let text = record["text"].as_str().unwrap();
        text.split(": '<ROOT>").next().unwrap().into()
    };
    format!("{prefix}: {}", path_repr(path))
}
pub fn path_repr(path: &std::path::Path) -> String {
    #[cfg(windows)]
    let path = &path.components().collect::<std::path::PathBuf>();
    handoff_packet::executor_text::repr(&path.to_string_lossy())
}
