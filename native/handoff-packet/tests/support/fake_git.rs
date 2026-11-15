use std::{fs, path::Path, process::Command, sync::OnceLock};

pub fn install(tools: &Path, command: &mut Command, changed: &str, mode: &str) {
    static BUILD: OnceLock<Vec<u8>> = OnceLock::new();
    let build = BUILD.get_or_init(|| {
        let dir = tempfile::tempdir().unwrap();
        let output = Command::new(std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into()))
            .env("RUSTUP_AUTO_INSTALL", "0")
            .arg(Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/git_fixture.rs"))
            .args(["--edition=2024", "-o"])
            .arg(
                dir.path()
                    .join(format!("git{}", std::env::consts::EXE_SUFFIX)),
            )
            .output()
            .unwrap();
        assert!(output.status.success(), "rustc: {output:?}");
        fs::read(
            dir.path()
                .join(format!("git{}", std::env::consts::EXE_SUFFIX)),
        )
        .unwrap()
    });
    let executable = tools.join(format!("git{}", std::env::consts::EXE_SUFFIX));
    fs::write(&executable, build).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
    }
    command
        .env("PATH", tools)
        .env("MIR_TEST_GIT_CHANGED", changed)
        .env("MIR_TEST_GIT_MODE", mode);
}
