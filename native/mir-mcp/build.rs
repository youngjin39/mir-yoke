//! Embed the same long-path opt-in the Python reference interpreter declares, so paths
//! beyond MAX_PATH open exactly when the host enables long paths for Python too.
fn main() {
    println!("cargo:rerun-if-changed=windows-long-paths.manifest");
    if std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc") {
        let manifest = std::path::Path::new(&std::env::var("CARGO_MANIFEST_DIR").unwrap())
            .join("windows-long-paths.manifest");
        println!("cargo:rustc-link-arg-bins=/MANIFEST:EMBED");
        println!(
            "cargo:rustc-link-arg-bins=/MANIFESTINPUT:{}",
            manifest.display()
        );
    }
}
