//! Local adoption installer regressions; no network or consumer repository access.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::adoption_native::{self as adoption, InstallHost, InstallOptions};
use serde_json::{Value, json};
use std::{fs, io, path::Path};

const TARGET: &str = "x86_64-unknown-linux-gnu";
const DATA: &[u8] = b"fixture artifact\n";
const DIGEST: &str = "0fc7c8c357dfa2cc6116cdf1172b5734908a31644d6a807152023dd63d7f151a";
const RELATIVE: &str = ".mir/bin/project-hooks";

struct SyntheticAccount<'a>(&'a Path);
impl InstallHost for SyntheticAccount<'_> {
    fn account_home(&mut self, name: Option<&std::ffi::OsStr>) -> Option<std::path::PathBuf> {
        (name.is_none() || name == Some(std::ffi::OsStr::new("synthetic-owner")))
            .then(|| self.0.to_owned())
    }
}
#[test]
fn local_source_normalizes_duplicate_separators_after_home_expansion() {
    let temp = scratch();
    put(temp.path(), "artifact", DATA);
    let options = InstallOptions {
        target: Some(TARGET),
        local_source: Some(Path::new("~//artifact")),
        home: Some(temp.path()),
        ..Default::default()
    };
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options, &mut adoption::LocalHost),
        Some(receipt())
    );
}
#[test]
fn named_account_local_source_uses_injected_home() {
    let temp = scratch();
    put(temp.path(), "artifact", DATA);
    let options = InstallOptions {
        target: Some(TARGET),
        local_source: Some(Path::new("~synthetic-owner//artifact")),
        ..Default::default()
    };
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options, &mut SyntheticAccount(temp.path())),
        Some(receipt())
    );
}

#[test]
fn default_account_local_source_without_home_uses_injected_account() {
    let temp = scratch();
    put(temp.path(), "artifact", DATA);
    let options = InstallOptions {
        target: Some(TARGET),
        local_source: Some(Path::new("~/artifact")),
        ..Default::default()
    };
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options, &mut SyntheticAccount(temp.path())),
        Some(receipt())
    );
}

fn scratch() -> tempfile::TempDir {
    tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap()
}
fn put(root: &Path, name: &str, data: impl AsRef<[u8]>) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, data).unwrap();
}
fn pin(source: &Path) -> Value {
    json!({"url":source,"size":DATA.len(),"sha256":DIGEST})
}
fn options(pin: &Value) -> InstallOptions<'_> {
    InstallOptions {
        target: Some(TARGET),
        artifact_pin: Some(pin),
        ..Default::default()
    }
}
fn receipt() -> Value {
    json!({"path":RELATIVE,"sha256":DIGEST})
}
fn lock(pin: &Value) -> Value {
    json!({"plugins":{"hooks":{}},"native_artifacts":{"project-hooks":{
        "plugin":"hooks","install_path":"bin/project-hooks","targets":{TARGET:pin}}}})
}

#[test]
fn local_host_installs_raw_and_percent_encoded_file_pins() {
    let temp = scratch();
    let source = temp.path().join("artifact with space");
    fs::write(&source, DATA).unwrap();
    for (i, url) in [
        source.to_str().unwrap().to_owned(),
        format!("file://localhost{}", source.display()).replace(' ', "%20"),
    ]
    .iter()
    .enumerate()
    {
        let root = temp.path().join(format!("project{i}"));
        fs::create_dir(&root).unwrap();
        let mut pin = pin(&source);
        pin["url"] = json!(url);
        assert_eq!(
            adoption::install_project_hooks(&root, &options(&pin), &mut adoption::LocalHost),
            Some(receipt())
        );
        assert_eq!(fs::read(root.join(RELATIVE)).unwrap(), DATA);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(root.join(RELATIVE))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o755
            );
        }
    }
}

#[test]
fn provider_json_bytes_match_python_bom_utf16_and_utf32_loading() {
    let temp = scratch();
    let source = temp.path().join("artifact");
    fs::write(&source, DATA).unwrap();
    let pin = pin(&source);
    let text = serde_json::to_string(&lock(&pin)).unwrap();
    let mut utf16 = vec![0xff, 0xfe];
    for unit in text.encode_utf16() {
        utf16.extend_from_slice(&unit.to_le_bytes());
    }
    let mut bom = vec![0xef, 0xbb, 0xbf];
    bom.extend_from_slice(text.as_bytes());
    // Frozen ba6aa95 provider-json-reference.json records utf8-bom/utf16/utf32.
    let mut utf32 = vec![0xff, 0xfe, 0, 0];
    for character in text.chars() {
        utf32.extend_from_slice(&u32::from(character).to_le_bytes());
    }
    for body in [bom, utf16, utf32] {
        put(temp.path(), ".mir/capability-lock.json", body);
        assert_eq!(
            adoption::provider_pin(temp.path(), "project-hooks", TARGET),
            Some(pin.clone())
        );
    }
}

#[test]
fn invalid_providers_and_local_sources_are_optional_without_target_writes() {
    let temp = scratch();
    let provider = temp.path().join("provider");
    let root = temp.path().join("project");
    fs::create_dir(&root).unwrap();
    for body in [
        b"{".as_slice(),
        b"[]",
        b"null",
        b"{}",
        b"{\"plugins\":{},\"native_artifacts\":[]}",
    ] {
        put(&provider, ".mir/capability-lock.json", body);
        let options = InstallOptions {
            target: Some(TARGET),
            source_root: Some(&provider),
            ..Default::default()
        };
        assert_eq!(
            adoption::install_project_hooks(&root, &options, &mut adoption::LocalHost),
            None
        );
        assert!(!root.join(".mir").exists());
    }
    let missing = temp.path().join("missing");
    let local_options = InstallOptions {
        target: Some(TARGET),
        local_source: Some(&missing),
        ..Default::default()
    };
    assert_eq!(
        adoption::install_project_hooks(&root, &local_options, &mut adoption::LocalHost),
        None
    );
    fs::write(&missing, b"").unwrap();
    assert_eq!(
        adoption::install_project_hooks(&root, &local_options, &mut adoption::LocalHost),
        None
    );
    assert!(!root.join(".mir").exists());
}

struct Denied;
impl InstallHost for Denied {
    fn read(&mut self, _: &str, _: u64) -> io::Result<Vec<u8>> {
        Err(io::Error::other("provider unavailable"))
    }
}
#[test]
fn provider_errors_and_integrity_failures_preserve_existing_bytes() {
    let temp = scratch();
    let source = temp.path().join("artifact");
    fs::write(&source, DATA).unwrap();
    let pin = pin(&source);
    put(temp.path(), RELATIVE, b"old");
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options(&pin), &mut Denied),
        None
    );
    let mut bad = pin.clone();
    bad["sha256"] = json!("0".repeat(64));
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options(&bad), &mut adoption::LocalHost),
        None
    );
    assert_eq!(fs::read(temp.path().join(RELATIVE)).unwrap(), b"old");
    assert_eq!(
        fs::read_dir(temp.path().join(".mir/bin")).unwrap().count(),
        1
    );
    let empty = temp.path().join("empty");
    fs::create_dir(&empty).unwrap();
    assert_eq!(
        adoption::install_project_hooks(&empty, &options(&bad), &mut adoption::LocalHost),
        None
    );
    assert!(!empty.join(".mir").exists());
}

#[test]
fn owner_local_source_expands_home_and_does_not_need_provider() {
    let temp = scratch();
    put(temp.path(), "artifact", DATA);
    let source = Path::new("~/artifact");
    let options = InstallOptions {
        target: Some(TARGET),
        local_source: Some(source),
        home: Some(temp.path()),
        ..Default::default()
    };
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options, &mut adoption::LocalHost),
        Some(receipt())
    );
}

#[cfg(unix)]
mod containment {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    struct Swap<'a> {
        root: &'a Path,
        outside: &'a Path,
        mode: &'a str,
        fail: bool,
    }
    impl InstallHost for Swap<'_> {
        fn before_replace(&mut self, source: &Path, destination: &Path) -> io::Result<()> {
            // A matching outside temporary name catches pathname-based Drop cleanup.
            fs::write(
                self.outside.join(source.file_name().unwrap()),
                b"outside temporary",
            )?;
            put(
                self.outside,
                &format!(".mir/bin/{}", source.file_name().unwrap().to_str().unwrap()),
                b"outside nested temporary",
            );
            match self.mode {
                "parent" => {
                    fs::rename(self.root.join(".mir/bin"), self.root.join("held"))?;
                    symlink(self.outside, self.root.join(".mir/bin"))?;
                }
                "root" => {
                    fs::rename(self.root, self.root.with_extension("held"))?;
                    symlink(self.outside, self.root)?;
                }
                "target" => {
                    symlink(self.outside.join("project-hooks"), destination)?;
                }
                "temporary" => {
                    fs::remove_file(source)?;
                    symlink(self.outside.join("project-hooks"), source)?;
                }
                "regular-temporary" => {
                    fs::remove_file(source)?;
                    fs::write(source, b"unverified attacker bytes")?;
                }
                _ => unreachable!(),
            }
            if self.fail {
                Err(io::Error::other("replacement refused"))
            } else {
                Ok(())
            }
        }
    }
    fn changed_layout(mode: &str, fail: bool) {
        let temp = scratch();
        let root = temp.path().join("project");
        let outside = temp.path().join("outside");
        fs::create_dir(&root).unwrap();
        fs::create_dir(&outside).unwrap();
        put(&outside, "project-hooks", b"outside binary");
        put(&outside, RELATIVE, b"outside nested binary");
        let source = temp.path().join("artifact");
        fs::write(&source, DATA).unwrap();
        let pin = pin(&source);
        assert_eq!(
            adoption::install_project_hooks(
                &root,
                &options(&pin),
                &mut Swap {
                    root: &root,
                    outside: &outside,
                    mode,
                    fail
                }
            ),
            None,
            "{mode} fail={fail}"
        );
        assert_eq!(
            fs::read(outside.join("project-hooks")).unwrap(),
            b"outside binary"
        );
        assert_eq!(
            fs::read(outside.join(RELATIVE)).unwrap(),
            b"outside nested binary"
        );
        let names: Vec<_> = fs::read_dir(&outside)
            .unwrap()
            .map(|e| e.unwrap().file_name())
            .collect();
        let temporary = names
            .iter()
            .find(|n| n.to_str().unwrap().starts_with(".project-hooks."))
            .expect("outside temporary must survive cleanup");
        assert_eq!(
            fs::read(outside.join(temporary)).unwrap(),
            b"outside temporary"
        );
        let held = if mode == "parent" {
            root.join("held")
        } else {
            root.with_extension("held").join(".mir/bin")
        };
        if held.exists() {
            assert_eq!(
                fs::read_dir(held).unwrap().count(),
                0,
                "pinned temporary cleanup"
            );
        }
    }
    #[test]
    fn changed_parent_fails_closed() {
        changed_layout("parent", false)
    }
    #[test]
    fn changed_root_fails_closed() {
        changed_layout("root", false)
    }
    #[test]
    fn cleanup_after_changed_parent_stays_pinned() {
        changed_layout("parent", true)
    }
    #[test]
    fn cleanup_after_changed_root_stays_pinned() {
        changed_layout("root", true)
    }
    fn changed_leaf(mode: &str) {
        let temp = scratch();
        let root = temp.path().join("project");
        let outside = temp.path().join("outside");
        fs::create_dir(&root).unwrap();
        fs::create_dir(&outside).unwrap();
        put(&outside, "project-hooks", b"outside binary");
        let source = temp.path().join("artifact");
        fs::write(&source, DATA).unwrap();
        let pin = pin(&source);
        assert_eq!(
            adoption::install_project_hooks(
                &root,
                &options(&pin),
                &mut Swap {
                    root: &root,
                    outside: &outside,
                    mode,
                    fail: false
                }
            ),
            None,
            "{mode}"
        );
        assert_eq!(
            fs::read(outside.join("project-hooks")).unwrap(),
            b"outside binary"
        );
        assert!(!root.join(RELATIVE).is_file() || root.join(RELATIVE).is_symlink());
        if root.join(".mir/bin").exists() {
            let temporary: Vec<_> = fs::read_dir(root.join(".mir/bin"))
                .unwrap()
                .map(|entry| entry.unwrap().path())
                .filter(|path| {
                    path.file_name()
                        .unwrap()
                        .to_str()
                        .unwrap()
                        .starts_with(".project-hooks.")
                })
                .collect();
            if matches!(mode, "temporary" | "regular-temporary") {
                assert_eq!(temporary.len(), 1, "foreign temporary must survive");
                if mode == "temporary" {
                    assert_eq!(
                        fs::read_link(&temporary[0]).unwrap(),
                        outside.join("project-hooks")
                    );
                } else {
                    assert_eq!(
                        fs::read(&temporary[0]).unwrap(),
                        b"unverified attacker bytes"
                    );
                }
            } else {
                assert!(temporary.is_empty(), "owned temporary must be cleaned");
            }
        }
    }
    #[test]
    fn changed_target_fails_closed() {
        changed_leaf("target")
    }
    #[test]
    fn changed_temporary_fails_closed() {
        changed_leaf("temporary")
    }
    #[test]
    fn changed_regular_temporary_fails_closed() {
        changed_leaf("regular-temporary")
    }
    #[test]
    fn nonexecutable_matching_destination_is_repaired_atomically() {
        let temp = scratch();
        let source = temp.path().join("artifact");
        fs::write(&source, DATA).unwrap();
        let pin = pin(&source);
        put(temp.path(), RELATIVE, DATA);
        fs::set_permissions(
            temp.path().join(RELATIVE),
            fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        assert_eq!(
            adoption::install_project_hooks(temp.path(), &options(&pin), &mut adoption::LocalHost),
            Some(receipt())
        );
        assert_eq!(
            fs::metadata(temp.path().join(RELATIVE))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o755
        );
    }
}

#[test]
fn unsupported_network_and_unsafe_names_have_no_target_effects() {
    let temp = scratch();
    let network =
        json!({"url":"https://example.invalid/artifact","size":DATA.len(),"sha256":DIGEST});
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options(&network), &mut adoption::LocalHost),
        None
    );
    let source = temp.path().join("artifact");
    fs::write(&source, DATA).unwrap();
    let pin = pin(&source);
    for name in ["", ".", "..", "../outside", "a/b", "a\\b"] {
        assert_eq!(
            adoption::install(temp.path(), name, &options(&pin), &mut adoption::LocalHost),
            None
        );
    }
    assert!(!temp.path().join(".mir").exists());
}

#[cfg(unix)]
struct UnusedReplacement;
#[cfg(unix)]
impl InstallHost for UnusedReplacement {
    fn before_replace(&mut self, _: &Path, _: &Path) -> io::Result<()> {
        panic!("verified executable should not be replaced")
    }
}
#[cfg(unix)]
#[test]
fn verified_executable_keeps_existing_inode_even_if_retrieved_bytes_differ() {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let temp = scratch();
    let source = temp.path().join("artifact");
    fs::write(&source, b"bad provider bytes").unwrap();
    let pin = pin(&source);
    put(temp.path(), RELATIVE, DATA);
    let destination = temp.path().join(RELATIVE);
    fs::set_permissions(&destination, fs::Permissions::from_mode(0o755)).unwrap();
    let inode = fs::metadata(&destination).unwrap().ino();
    assert_eq!(
        adoption::install_project_hooks(temp.path(), &options(&pin), &mut UnusedReplacement),
        Some(receipt())
    );
    assert_eq!(fs::metadata(destination).unwrap().ino(), inode);
}

#[cfg(unix)]
#[test]
fn linked_provider_and_source_paths_are_refused_and_all_provider_records_validate() {
    use std::os::unix::fs::symlink;
    let temp = scratch();
    let source = temp.path().join("artifact");
    fs::write(&source, DATA).unwrap();
    let pin = pin(&source);
    let provider = temp.path().join("provider");
    let root = temp.path().join("project");
    fs::create_dir(&root).unwrap();
    let mut invalid = lock(&pin);
    invalid["native_artifacts"]["unrelated"] = json!({});
    put(
        &provider,
        ".mir/capability-lock.json",
        serde_json::to_vec(&invalid).unwrap(),
    );
    let options = InstallOptions {
        target: Some(TARGET),
        source_root: Some(&provider),
        ..Default::default()
    };
    assert_eq!(
        adoption::install_project_hooks(&root, &options, &mut adoption::LocalHost),
        None
    );
    let valid = temp.path().join("valid-lock");
    fs::write(&valid, serde_json::to_vec(&lock(&pin)).unwrap()).unwrap();
    fs::remove_file(provider.join(".mir/capability-lock.json")).unwrap();
    symlink(&valid, provider.join(".mir/capability-lock.json")).unwrap();
    assert_eq!(
        adoption::install_project_hooks(&root, &options, &mut adoption::LocalHost),
        None
    );
    fs::remove_file(provider.join(".mir/capability-lock.json")).unwrap();
    fs::rename(provider.join(".mir"), provider.join("held")).unwrap();
    put(
        &provider,
        "held/capability-lock.json",
        serde_json::to_vec(&lock(&pin)).unwrap(),
    );
    symlink(provider.join("held"), provider.join(".mir")).unwrap();
    assert_eq!(
        adoption::install_project_hooks(&root, &options, &mut adoption::LocalHost),
        None
    );
    let linked = temp.path().join("linked-artifact");
    symlink(&source, &linked).unwrap();
    let mut linked_pin = pin.clone();
    linked_pin["url"] = json!(linked);
    let linked_options = InstallOptions {
        target: Some(TARGET),
        artifact_pin: Some(&linked_pin),
        ..Default::default()
    };
    assert_eq!(
        adoption::install_project_hooks(&root, &linked_options, &mut adoption::LocalHost),
        None
    );
    assert!(!root.join(".mir").exists());
}

#[cfg(unix)]
struct ReplaceCreatedDirectory<'a> {
    directory: &'a Path,
    saved: &'a Path,
    replaced: bool,
}

#[cfg(unix)]
impl InstallHost for ReplaceCreatedDirectory<'_> {
    fn before_replace(&mut self, _: &Path, _: &Path) -> io::Result<()> {
        fs::rename(self.directory, self.saved)?;
        fs::create_dir(self.directory)?;
        self.replaced = true;
        Err(io::Error::other("replacement refused"))
    }
}

#[cfg(unix)]
#[test]
fn installer_cleanup_preserves_foreign_directory_replacements() {
    for relative in [".mir/bin", ".mir"] {
        let temp = scratch();
        let root = temp.path().join("project");
        fs::create_dir(&root).unwrap();
        let source = temp.path().join("artifact");
        fs::write(&source, DATA).unwrap();
        let pin = pin(&source);
        let directory = root.join(relative);
        let saved = temp.path().join("saved");
        let mut host = ReplaceCreatedDirectory {
            directory: &directory,
            saved: &saved,
            replaced: false,
        };
        assert_eq!(
            adoption::install_project_hooks(&root, &options(&pin), &mut host),
            None
        );
        assert!(host.replaced, "{relative} callback was not reached");
        assert!(
            directory.is_dir(),
            "{relative} foreign directory was deleted"
        );
        assert_eq!(fs::read_dir(&directory).unwrap().count(), 0);
        assert!(saved.is_dir(), "{relative} original directory was deleted");
        assert_eq!(fs::read_dir(saved).unwrap().count(), 0);
    }
}
