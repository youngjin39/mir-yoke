#![cfg(unix)]
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::mir_core::capabilities::native::{
    self, ArtifactHost, PlacementMutation, PlacementOptions,
};
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    fs, io,
    os::unix::fs::{PermissionsExt, symlink},
    path::{Path, PathBuf},
};

const TARGET: &str = "aarch64-apple-darwin";
const PAYLOAD: &[u8] = b"native payload\n";

fn scratch() -> tempfile::TempDir {
    tempfile::tempdir().unwrap()
}
struct Host {
    counter: usize,
    warm: Vec<PathBuf>,
    mutation: Option<(PlacementMutation, PathBuf, PathBuf, PathBuf)>,
    failure: Option<PlacementMutation>,
}
impl Host {
    fn new() -> Self {
        Self {
            counter: 0,
            warm: vec![],
            mutation: None,
            failure: None,
        }
    }
}
impl ArtifactHost for Host {
    fn read(&mut self, url: &str, size: u64) -> Result<Vec<u8>, String> {
        native::LocalArtifactHost.read(url, size)
    }
    fn warm(&mut self, path: &Path) {
        self.warm.push(path.to_owned());
    }
    fn temporary_name(&mut self) -> OsString {
        self.counter += 1;
        format!(".tmp-native-{}", self.counter).into()
    }
    fn before_mutation(&mut self, site: PlacementMutation, _: &Path) -> io::Result<()> {
        if self.failure == Some(site) {
            return Err(io::Error::from_raw_os_error(libc::EACCES));
        }
        if self
            .mutation
            .as_ref()
            .is_some_and(|(selected, ..)| *selected == site)
        {
            let (_, path, saved, outside) = self.mutation.take().unwrap();
            fs::rename(&path, saved)?;
            symlink(outside, path)?;
        }
        Ok(())
    }
}
fn records(source: &Path, plugin: &str, name: &str, relative: &str, target: &str) -> Value {
    json!({name:{"plugin":plugin,"install_path":relative,"targets":{target:{
        "url":source,"size":PAYLOAD.len(),"sha256":digest::sha256(PAYLOAD)
    }}}})
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn ordered(tree: &Value) -> handoff_packet::python_json::Value {
    handoff_packet::python_json::parse(&tree.to_string()).unwrap()
}
fn snapshot(base: &Path, root: &Path, path: &Path, files: &mut serde_json::Map<String, Value>) {
    let mut entries: Vec<_> = fs::read_dir(path)
        .unwrap()
        .map(|e| e.unwrap().path())
        .collect();
    entries.sort();
    for path in entries {
        let key = path
            .strip_prefix(root)
            .unwrap()
            .to_str()
            .unwrap()
            .to_owned();
        let metadata = fs::symlink_metadata(&path).unwrap();
        if metadata.is_symlink() {
            files.insert(key, json!({"link":fs::read_link(path).unwrap().to_str().unwrap().replace(base.to_str().unwrap(),"<base>")}));
        } else if metadata.is_dir() {
            files.insert(
                key,
                json!({"directory":true,"mode":metadata.permissions().mode() & 0o777}),
            );
            snapshot(base, root, &path, files);
        } else {
            files.insert(key, json!({"bytes":hex(&fs::read(path).unwrap()),"mode":metadata.permissions().mode() & 0o777}));
        }
    }
}
#[test]
fn pinned_python_placement_and_warmup_records_match() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/stage-e02b-placement.json")).unwrap();
    assert_eq!(
        fixture["reference"],
        "ba6aa95673deefcb5f418b3fe9f3007f9b22e62a:src/mir/core/capabilities/native.py"
    );
    for row in fixture["records"].as_array().unwrap() {
        let case = row["case"].as_str().unwrap();
        let temp = scratch();
        let base = temp.path().canonicalize().unwrap();
        let root = base.join("root");
        fs::create_dir(&root).unwrap();
        let source = base.join("source");
        fs::write(&source, PAYLOAD).unwrap();
        let plugin = row["plugin"].as_str().unwrap();
        let name = row["name"].as_str().unwrap();
        let relative = row["relative"].as_str().unwrap();
        let target = row["target"].as_str().unwrap_or(TARGET);
        let destination = root.join(format!(
            "{relative}{}",
            if target.ends_with("windows-msvc") {
                ".exe"
            } else {
                ""
            }
        ));
        let mut tree = records(&source, plugin, name, relative, target);
        if case == "missing-source" {
            fs::remove_file(&source).unwrap();
        }
        if matches!(
            case,
            "oversize" | "fail-remove-temporary" | "fail-remove-directory"
        ) {
            fs::write(&source, [PAYLOAD, b"x"].concat()).unwrap();
        }
        if matches!(case, "bad-sha" | "warm-bad-sha") {
            tree[name]["targets"][target]["sha256"] = json!("0".repeat(64));
        }
        if case == "no-pin" {
            tree[name]["targets"] = json!({});
        }
        if case == "other-plugin" {
            tree[name]["plugin"] = json!("other");
        }
        if matches!(
            case,
            "existing"
                | "destination-link"
                | "readonly-parent"
                | "metadata-exists"
                | "metadata-link"
                | "fail-remove-installed"
        ) || case.starts_with("warm-")
        {
            fs::create_dir(root.join("bin")).unwrap();
        }
        match case {
            "existing" => fs::write(&destination, b"existing").unwrap(),
            "destination-link" => symlink(&source, &destination).unwrap(),
            "parent-link" => {
                fs::create_dir(base.join("outside")).unwrap();
                symlink(base.join("outside"), root.join("bin")).unwrap();
            }
            "parent-file" => fs::write(root.join("bin"), b"parent").unwrap(),
            "metadata-exists" => {
                fs::write(root.join("bin/native-artifacts.json"), b"existing metadata").unwrap()
            }
            "fail-remove-installed" => {
                fs::write(root.join("bin/native-artifacts.json"), b"existing metadata").unwrap()
            }
            "metadata-link" => symlink(&source, root.join("bin/native-artifacts.json")).unwrap(),
            "readonly-parent" => {
                fs::set_permissions(root.join("bin"), fs::Permissions::from_mode(0o500)).unwrap()
            }
            _ => (),
        }
        if case.starts_with("warm-") && case != "warm-missing" {
            if case == "warm-link" {
                symlink(&source, &destination).unwrap();
            } else {
                fs::write(&destination, PAYLOAD).unwrap();
            }
        }
        let mut host = Host::new();
        host.failure = match case {
            "fail-publish" => Some(PlacementMutation::PublishArtifact),
            "fail-metadata-publish" => Some(PlacementMutation::PublishMetadata),
            "fail-remove-installed" => Some(PlacementMutation::RemoveInstalled),
            "fail-remove-temporary" => Some(PlacementMutation::RemoveTemporary),
            "fail-remove-directory" => Some(PlacementMutation::RemoveDirectory),
            _ => None,
        };
        let ordered_tree = if case == "multi-order" {
            tree[name]["targets"] = json!({});
            handoff_packet::python_json::parse(&format!(
                "{{\"z-last-name-first\":{},\"a-first-name-last\":{}}}",
                tree[name], tree[name]
            ))
            .unwrap()
        } else {
            ordered(&tree)
        };
        let result = if case.starts_with("warm-") {
            native::warm_artifacts(&root, plugin, &ordered_tree, Some(target), &mut host);
            Ok(vec![])
        } else {
            native::place_artifacts(
                &root,
                plugin,
                &ordered_tree,
                PlacementOptions {
                    target: row["target"].as_str(),
                    disabled: case == "disabled",
                },
                &mut host,
            )
        };
        let (warnings, error) = match result {
            Ok(warnings) => (warnings, Value::Null),
            Err(error) => (
                error.warnings,
                json!(error.message.replace(base.to_str().unwrap(), "<base>")),
            ),
        };
        let stderr = warnings
            .iter()
            .map(|s| format!("{s}\n"))
            .collect::<String>()
            .replace(base.to_str().unwrap(), "<base>");
        assert_eq!(stderr, row["stderr"], "{case} stderr");
        assert_eq!(error, row["error"], "{case} error");
        let mut files = serde_json::Map::new();
        snapshot(&base, &root, &root, &mut files);
        assert_eq!(json!(files), row["files"], "{case} files");
        assert_eq!(
            json!(
                host.warm
                    .iter()
                    .map(|p| p.strip_prefix(&root).unwrap().to_str().unwrap())
                    .collect::<Vec<_>>()
            ),
            row["warm"],
            "{case} warm"
        );
        if case == "readonly-parent" {
            fs::set_permissions(root.join("bin"), fs::Permissions::from_mode(0o700)).unwrap();
        }
    }
}

#[test]
fn warm_verification_does_not_follow_a_linked_parent() {
    let temp = scratch();
    let base = temp.path().canonicalize().unwrap();
    let root = base.join("root");
    let outside = base.join("outside");
    fs::create_dir(&root).unwrap();
    fs::create_dir(&outside).unwrap();
    let source = outside.join("runtime.exe");
    fs::write(&source, PAYLOAD).unwrap();
    symlink(&outside, root.join("bin")).unwrap();
    let target = "x86_64-pc-windows-msvc";
    let tree = records(&source, "p", "runtime", "bin/runtime", target);
    native::validate_artifacts(&tree, &json!({"p": {}}), false).unwrap();
    let mut host = Host::new();
    native::warm_artifacts(&root, "p", &ordered(&tree), Some(target), &mut host);
    assert!(
        host.warm.is_empty(),
        "linked parent must skip warm verification"
    );
    assert_eq!(fs::read(&source).unwrap(), PAYLOAD);
}

#[test]
#[rustfmt::skip]
fn every_placement_and_rollback_mutation_stays_in_the_pinned_root() {
    use PlacementMutation::*;
    for site in [
        CreateDirectory,
        CreateTemporary,
        SetExecutable,
        PublishArtifact,
        PublishMetadata,
        RemoveInstalled,
        RemoveTemporary,
        RemoveDirectory,
    ] {
        let temp = scratch();
        let base = temp.path().canonicalize().unwrap();
        let root = base.join("root");
        let outside = base.join("outside");
        fs::create_dir(&root).unwrap();
        fs::create_dir(&outside).unwrap();
        let bin = root.join("bin");
        if !matches!(site, CreateDirectory | RemoveDirectory) {
            fs::create_dir(&bin).unwrap();
        }
        let source = base.join("source");
        fs::write(&source, PAYLOAD).unwrap();
        let mut tree = records(&source, "mir-mcp", "mir-mcp", "bin/runtime", TARGET);
        if matches!(site, RemoveTemporary | RemoveDirectory) {
            tree["mir-mcp"]["targets"][TARGET]["sha256"] = json!("0".repeat(64));
        }
        if site == RemoveInstalled {
            fs::write(bin.join("native-artifacts.json"), b"existing metadata").unwrap();
        }
        for name in [
            "runtime",
            "native-artifacts.json",
            ".tmp-native-1",
            ".tmp-native-2",
        ] {
            fs::write(outside.join(name), b"outside sentinel").unwrap();
        }
        let mut host = Host::new();
        let changed = if site == CreateDirectory {
            root.clone()
        } else {
            bin.clone()
        };
        let saved = base.join("saved");
        host.mutation = Some((site, changed, saved.clone(), outside.clone()));
        let _ = native::place_artifacts(
            &root,
            "mir-mcp",
            &ordered(&tree),
            PlacementOptions {
                target: Some(TARGET),
                disabled: false,
            },
            &mut host,
        );
        assert!(host.mutation.is_none(), "{site:?} callback was not reached");
        for name in [
            "runtime",
            "native-artifacts.json",
            ".tmp-native-1",
            ".tmp-native-2",
        ] {
            assert_eq!(
                fs::read(outside.join(name)).unwrap(),
                b"outside sentinel",
                "{site:?}/{name}"
            );
        }
        assert_eq!(fs::read_dir(&outside).unwrap().count(), 4, "{site:?}");
        if matches!(
            site,
            CreateTemporary | SetExecutable | RemoveInstalled | RemoveTemporary
        ) {
            assert!(!saved.join("runtime").exists(), "{site:?} rollback");
        }
        // Relocation moves owned temporaries outside root; cleanup preserves them.
        for (name, preserved, bytes, mode) in [
            (".tmp-native-1", matches!(site, SetExecutable | PublishArtifact | RemoveTemporary), PAYLOAD.to_vec(), if site == RemoveTemporary { 0o600 } else { 0o755 }),
            (".tmp-native-2", site == PublishMetadata, format!("{{\"mir-mcp\": {{\"sha256\": \"{}\", \"size\": 15, \"target\": \"{TARGET}\"}}}}", digest::sha256(PAYLOAD)).into_bytes(), 0o600),
        ] {
            let path = saved.join(name);
            assert_eq!(path.exists(), preserved, "{site:?}/{name}");
            if preserved {
                assert_eq!(fs::read(&path).unwrap(), bytes, "{site:?}/{name}");
                assert_eq!(fs::metadata(path).unwrap().permissions().mode() & 0o777, mode, "{site:?}/{name}");
            }
        }
    }
}

#[test]
fn root_dotdot_spelling_works_and_cannot_hide_a_linked_ancestor() {
    let temp = scratch();
    let base = temp.path().canonicalize().unwrap();
    let root = base.join("root");
    fs::create_dir_all(root.join("nested")).unwrap();
    let source = base.join("source");
    fs::write(&source, PAYLOAD).unwrap();
    let tree = records(
        &source,
        "mir-lifecycle-hooks",
        "project-hooks",
        "bin/runtime",
        TARGET,
    );
    let mut host = Host::new();
    let warnings = native::place_artifacts(
        &root.join("nested/.."),
        "mir-lifecycle-hooks",
        &ordered(&tree),
        PlacementOptions {
            target: Some(TARGET),
            disabled: false,
        },
        &mut host,
    )
    .unwrap();
    assert!(warnings.is_empty(), "{warnings:?}");
    assert_eq!(fs::read(root.join("bin/runtime")).unwrap(), PAYLOAD);
    let outside = base.join("outside");
    fs::create_dir(&outside).unwrap();
    symlink(&outside, root.join("linked")).unwrap();
    let warnings = native::place_artifacts(
        &root.join("linked/.."),
        "mir-lifecycle-hooks",
        &ordered(&tree),
        PlacementOptions {
            target: Some(TARGET),
            disabled: false,
        },
        &mut host,
    )
    .unwrap();
    assert_eq!(warnings.len(), 1);
    assert!(warnings[0].contains("linked native artifact parent"));
    assert_eq!(fs::read_dir(outside).unwrap().count(), 0);
}

fn leaf_swap(site: PlacementMutation) {
    let temp = scratch();
    let base = temp.path().canonicalize().unwrap();
    let root = base.join("root");
    fs::create_dir_all(root.join("bin")).unwrap();
    let outside = base.join("outside");
    fs::write(&outside, b"outside sentinel").unwrap();
    let source = base.join("source");
    fs::write(&source, PAYLOAD).unwrap();
    let tree = records(&source, "mir-mcp", "mir-mcp", "bin/runtime", TARGET);
    let temporary = root.join(if site == PlacementMutation::PublishArtifact {
        "bin/.tmp-native-1"
    } else {
        "bin/.tmp-native-2"
    });
    let mut host = Host::new();
    host.mutation = Some((site, temporary, base.join("saved"), outside.clone()));
    let result = native::place_artifacts(
        &root,
        "mir-mcp",
        &ordered(&tree),
        PlacementOptions {
            target: Some(TARGET),
            disabled: false,
        },
        &mut host,
    );
    assert!(host.mutation.is_none(), "{site:?} was not reached");
    assert_eq!(fs::read(&outside).unwrap(), b"outside sentinel");
    assert!(
        !root.join("bin/runtime").exists(),
        "{site:?}: unverified artifact published"
    );
    assert!(
        !root.join("bin/native-artifacts.json").exists(),
        "{site:?}: unverified metadata published"
    );
    assert!(
        result.is_err() || !result.unwrap().is_empty(),
        "{site:?}: reported success"
    );
}

#[test]
fn temporary_artifact_leaf_swap_cannot_publish_an_unverified_link() {
    leaf_swap(PlacementMutation::PublishArtifact);
}

#[test]
fn temporary_metadata_leaf_swap_cannot_publish_an_unverified_link() {
    leaf_swap(PlacementMutation::PublishMetadata);
}

struct CleanupReplacementHost {
    inner: Host,
    site: PlacementMutation,
    leaf: Option<PathBuf>,
    saved: PathBuf,
    replaced: bool,
}

impl ArtifactHost for CleanupReplacementHost {
    fn read(&mut self, url: &str, size: u64) -> Result<Vec<u8>, String> {
        self.inner.read(url, size)
    }

    fn temporary_name(&mut self) -> OsString {
        self.inner.temporary_name()
    }

    fn before_mutation(&mut self, site: PlacementMutation, path: &Path) -> io::Result<()> {
        if site == self.site && !self.replaced {
            let path = self.leaf.as_deref().unwrap_or(path);
            fs::rename(path, &self.saved)?;
            if site == PlacementMutation::RemoveDirectory {
                fs::create_dir(path)?;
            } else {
                fs::write(path, b"foreign replacement")?;
                fs::set_permissions(path, fs::Permissions::from_mode(0o640))?;
            }
            self.replaced = true;
        }
        Ok(())
    }
}

fn cleanup_leaf_replacement(site: PlacementMutation) {
    let temp = scratch();
    let base = temp.path().canonicalize().unwrap();
    let root = base.join("root");
    fs::create_dir(&root).unwrap();
    let source = base.join("source");
    fs::write(&source, PAYLOAD).unwrap();
    let mut tree = records(&source, "mir-mcp", "mir-mcp", "bin/runtime", TARGET);
    let foreign = if site == PlacementMutation::RemoveDirectory {
        tree["mir-mcp"]["targets"][TARGET]["sha256"] = json!("0".repeat(64));
        root.join("bin")
    } else {
        fs::create_dir(root.join("bin")).unwrap();
        fs::write(root.join("bin/native-artifacts.json"), b"existing metadata").unwrap();
        root.join("bin/runtime")
    };
    let saved = base.join("saved");
    let mut host = CleanupReplacementHost {
        inner: Host::new(),
        site,
        leaf: None,
        saved: saved.clone(),
        replaced: false,
    };
    let result = native::place_artifacts(
        &root,
        "mir-mcp",
        &ordered(&tree),
        PlacementOptions {
            target: Some(TARGET),
            disabled: false,
        },
        &mut host,
    );
    assert!(host.replaced, "{site:?} callback was not reached");
    assert!(foreign.exists(), "{site:?} deleted a foreign replacement");
    if site == PlacementMutation::RemoveDirectory {
        assert!(foreign.is_dir());
        assert_eq!(fs::read_dir(&foreign).unwrap().count(), 0);
        assert!(saved.is_dir());
    } else {
        assert_eq!(fs::read(&foreign).unwrap(), b"foreign replacement");
        assert_eq!(fs::read(&saved).unwrap(), PAYLOAD);
    }
    let error = result.expect_err("foreign cleanup replacement must fail closed");
    assert!(error.message.starts_with("OSError:"), "{}", error.message);
}

#[test]
fn installed_rollback_preserves_a_foreign_leaf_replacement() {
    cleanup_leaf_replacement(PlacementMutation::RemoveInstalled);
}

#[test]
fn created_directory_cleanup_preserves_a_foreign_leaf_replacement() {
    cleanup_leaf_replacement(PlacementMutation::RemoveDirectory);
}

fn regular_temporary_swap(site: PlacementMutation, metadata: bool) {
    let temp = scratch();
    let base = temp.path().canonicalize().unwrap();
    let root = base.join("root");
    fs::create_dir_all(root.join("bin")).unwrap();
    let source = base.join("source");
    fs::write(&source, PAYLOAD).unwrap();
    let tree = records(&source, "mir-mcp", "mir-mcp", "bin/runtime", TARGET);
    let leaf = root.join(if metadata {
        "bin/.tmp-native-2"
    } else {
        "bin/.tmp-native-1"
    });
    let mut host = CleanupReplacementHost {
        inner: Host::new(),
        site,
        leaf: Some(leaf.clone()),
        saved: base.join("saved"),
        replaced: false,
    };
    let result = native::place_artifacts(
        &root,
        "mir-mcp",
        &ordered(&tree),
        PlacementOptions {
            target: Some(TARGET),
            disabled: false,
        },
        &mut host,
    );
    assert!(host.replaced, "{site:?} callback was not reached");
    assert_eq!(fs::read(&leaf).unwrap(), b"foreign replacement");
    assert_eq!(
        fs::metadata(&leaf).unwrap().permissions().mode() & 0o777,
        0o640
    );
    assert!(!root.join("bin/runtime").exists(), "{result:?}");
    assert!(
        !root.join("bin/native-artifacts.json").exists(),
        "{result:?}"
    );
    assert!(result.is_err(), "{site:?} reported success");
}

#[test]
fn swap_regular_before_chmod() {
    regular_temporary_swap(PlacementMutation::SetExecutable, false);
}

#[test]
fn swap_regular_before_publish_artifact() {
    regular_temporary_swap(PlacementMutation::PublishArtifact, false);
}

#[test]
fn swap_regular_before_publish_metadata() {
    regular_temporary_swap(PlacementMutation::PublishMetadata, true);
}
