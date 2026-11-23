//! Replay the unmodified Python B30 oracle through library-only Rust modules.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::changes;
use serde_json::{Value, json};
use std::{fs, path::Path};

fn observe_root(name: &str, mut value: Value, root: &str) -> Value {
    // a61c3013 project_hooks.py:61,119: receipt read raises; degraded stdout
    // contains errno's filename repr. Tokenize the root, never its suffix.
    if name == "hooks.check.uninstalled"
        && let Some(text) = value["value"][1].as_str()
    {
        let plain = root.strip_prefix(r"\\?\").unwrap_or(root);
        let mut text = text.to_owned();
        let mut spellings = Vec::new();
        for spelling in [root.to_owned(), plain.to_owned(), plain.replace('\\', "/")] {
            let encoded = serde_json::to_string(&spelling).unwrap();
            spellings.push(encoded[1..encoded.len() - 1].to_owned());
            spellings.push(spelling);
        }
        spellings.sort_by_key(|s| std::cmp::Reverse(s.len()));
        for spelling in spellings {
            for separator in ["/", r"\", r"\\"] {
                text = text.replace(
                    &format!(": '{spelling}{separator}"),
                    &format!(": '<tmp>{separator}"),
                );
            }
        }
        value["value"][1] = json!(text);
    }
    value
}

#[test]
fn wt_core_a_d_roots() {
    let root = r"\\?\C:\synthetic\case";
    let encoded = serde_json::to_string(root).unwrap();
    for spelling in [
        root,
        r"C:\synthetic\case",
        "C:/synthetic/case",
        &encoded[1..encoded.len() - 1],
    ] {
        for suffix in [
            "/project/.mir/bin/project-hooks.json",
            r"\project\.mir\bin\project-hooks.json",
        ] {
            let text = format!(
                "project-hooks: degraded: [Errno 2] No such file or directory: '{spelling}{suffix}'\n"
            );
            let input = json!({"value":[1,text,text,{},[]]});
            let mut expected = input.clone();
            expected["value"][1] = json!(format!(
                "project-hooks: degraded: [Errno 2] No such file or directory: '<tmp>{suffix}'\n"
            ));
            assert_eq!(
                observe_root("hooks.check.uninstalled", input.clone(), root),
                expected
            );
            assert_eq!(observe_root("other", input.clone(), root), input);
            let other = text.replace("case", "case-other");
            let input = json!({"value":[1,other,"",{},[]]});
            assert_eq!(
                observe_root("hooks.check.uninstalled", input.clone(), root),
                input
            );
        }
    }
}

#[test]
fn w_errno_observe_localized_filename() {
    let root = r"C:\synthetic\case";
    let filename = format!(r"{root}\project\.mir\bin\project-hooks.json");
    let filename = handoff_packet::executor_text::repr(&filename);
    let text = format!(
        "project-hooks: degraded: [Errno 3] \u{c9c0}\u{c815}\u{b41c} \
         \u{acbd}\u{b85c}\u{b97c} \u{cc3e}\u{c744} \
         \u{c218} \u{c5c6}\u{c2b5}\u{b2c8}\u{b2e4}.: {filename}\n"
    );
    let expected = text.replace(&root.replace('\\', r"\\"), "<tmp>");
    let input = json!({"value":[1,text,"",{},[]]});
    assert_eq!(
        observe_root("hooks.check.uninstalled", input, root)["value"][1],
        expected
    );
}

#[path = "b30_capability_support/mod.rs"]
mod capability;
#[path = "b30_hooks_support/mod.rs"]
mod hooks;
#[path = "b30_native_support/mod.rs"]
mod native;

#[test]
fn s01_frozen_root_resolution() {
    use handoff_packet::mir_cli::bootstrap::{Host, ProductionHost};
    let oracle: Value = serde_json::from_str(include_str!("fixtures/wt-s01-resolve.json")).unwrap();
    assert_eq!(
        oracle["reference_pin"],
        "a61c3013dc382989c321577bb93dd937d11884fd"
    );
    let temp = tempfile::tempdir().unwrap();
    let root = handoff_packet::supply::plain(temp.path().canonicalize().unwrap());
    fs::write(root.join("file"), "synthetic").unwrap();
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink("absent", root.join("dangling")).unwrap();
        std::os::unix::fs::symlink("loop", root.join("loop")).unwrap();
    }
    // Only path-valued fields are translated to the host's separator/anchor.
    let expand = |text: &str| {
        if text == "{ANCHOR}" {
            root.ancestors().last().unwrap().to_owned()
        } else {
            text.strip_prefix("{ROOT}")
                .unwrap()
                .split('/')
                .filter(|s| !s.is_empty())
                .fold(root.clone(), |path, part| path.join(part))
        }
    };
    for r in oracle["records"].as_array().unwrap() {
        if cfg!(windows) && matches!(r["case"].as_str(), Some("dangling" | "loop")) {
            continue; // These two frozen records require Unix symlink semantics.
        }
        let actual = ProductionHost::default().resolve(&expand(r["input"].as_str().unwrap()));
        if let Some(value) = r["value"].as_str() {
            assert_eq!(actual.unwrap(), expand(value), "{r}");
        } else {
            let error = actual.unwrap_err();
            assert_eq!(error.class, r["class"].as_str().unwrap());
            assert_eq!(
                error.message,
                r["message"]
                    .as_str()
                    .unwrap()
                    .replace("{ROOT}", root.to_str().unwrap())
            );
        }
    }
}

#[cfg(windows)]
#[test]
fn s01_windows_drive_roots() {
    use handoff_packet::mir_cli::bootstrap::{Host, ProductionHost};
    let temp = tempfile::tempdir().unwrap();
    let verbatim = temp.path().canonicalize().unwrap();
    for root in [handoff_packet::supply::plain(verbatim.clone()), verbatim] {
        let anchor = root.ancestors().last().unwrap();
        for (input, expected) in [
            (root.clone(), root.clone()),
            (anchor.to_owned(), anchor.to_owned()),
            (
                root.join("missing").join("tail"),
                root.join("missing").join("tail"),
            ),
            (
                root.join("missing").join("..").join("tail"),
                root.join("tail"),
            ),
        ] {
            let actual = ProductionHost::default().resolve(&input).unwrap();
            assert_eq!(actual.as_os_str(), expected.as_os_str(), "{input:?}");
        }
    }
}

#[cfg(windows)]
#[test]
fn s01_windows_frozen_root_resolution() {
    use handoff_packet::mir_cli::bootstrap::{Host, ProductionHost};
    let records: Value = serde_json::from_slice(
        &fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/wt-s01-resolve-windows.json"),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(
        records["reference_pin"],
        "a61c3013dc382989c321577bb93dd937d11884fd"
    );
    assert_eq!(records["platform"], "win32");
    assert!(matches!(
        records["records"].as_array().unwrap().len(),
        11 | 19
    ));
    // Captured paths are tokenized against the exact synthetic capture roots.
    let temp = tempfile::tempdir().unwrap();
    let plain = handoff_packet::supply::plain(temp.path().canonicalize().unwrap());
    fs::write(plain.join("file"), "synthetic").unwrap();
    for r in records["records"].as_array().unwrap() {
        let root = match r["kind"].as_str().unwrap() {
            "plain" => plain.clone(),
            "verbatim" => plain.canonicalize().unwrap(),
            "unc" | "verbatim-unc" => {
                let root = std::path::PathBuf::from(
                    std::env::var_os("MIR_WT_S01_UNC_ROOT").expect("synthetic UNC root required"),
                );
                if r["kind"] == "verbatim-unc" {
                    root.canonicalize().unwrap()
                } else {
                    root
                }
            }
            other => panic!("unknown root kind {other}"),
        };
        let expand = |text: &str| {
            text.replace("{ROOT_SLASH}", &root.to_str().unwrap().replace('\\', "/"))
                .replace("{ROOT}", root.to_str().unwrap())
                .replace(
                    "{ANCHOR}",
                    root.ancestors().last().unwrap().to_str().unwrap(),
                )
        };
        let actual =
            ProductionHost::default().resolve(Path::new(&expand(r["input"].as_str().unwrap())));
        if let Some(value) = r["value"].as_str() {
            assert_eq!(
                actual.unwrap().as_os_str(),
                Path::new(&expand(value)).as_os_str(),
                "{r}"
            );
        } else {
            let error = actual.unwrap_err();
            assert_eq!(error.class, r["class"].as_str().unwrap());
            assert_eq!(error.message, expand(r["message"].as_str().unwrap()));
        }
    }
}

fn windows_exemption(name: &str) -> Option<&'static str> {
    if cfg!(windows) {
        match name {
            "changes.snapshot_and_diff"
            | "native.project_hooks.linked"
            | "native.project_hooks.linked-parent"
            | "hooks.path.normal" => {
                return Some("symlink creation requires Windows host privilege");
            }
            "hooks.check.not-executable" => {
                return Some("Unix executable permission has no Windows equivalent");
            }
            _ => {}
        }
    }
    None
}

fn snapshot_case(tmp: &Path) -> Value {
    fs::write(tmp.join("a"), "before").unwrap();
    fs::create_dir(tmp.join(".git")).unwrap();
    fs::write(tmp.join(".git/ignored"), "ignored").unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink("a", tmp.join("link")).unwrap();
    let before = changes::snapshot_project(tmp).unwrap();
    fs::remove_file(tmp.join("a")).unwrap();
    fs::write(tmp.join("z"), "after").unwrap();
    let after = changes::snapshot_project(tmp).unwrap();
    let paths = changes::changed_paths(&before, &after);
    json!({"value": [before, after, paths]})
}

fn excluded_case(tmp: &Path) -> Value {
    for name in [
        ".git/a",
        ".pytest_cache/b",
        ".venv/c",
        "__pycache__/d.pyc",
        "pkg/__pycache__/m.pyc",
        "pkg/.venv/e",
        "docs/.git",
        ".venvx/keep",
        "pkg/__pycache__x/n",
        "pkg/keep.py",
    ] {
        let path = tmp.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, name).unwrap();
    }
    let keys: Vec<_> = changes::snapshot_project(tmp)
        .unwrap()
        .into_keys()
        .collect();
    json!({"value": keys})
}

#[test]
fn every_frozen_record_replays_exactly() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-capability.json")).unwrap();
    let records = records.as_object().unwrap();
    assert_eq!(records.len(), 60);
    let (mut replayed, mut exempt) = (0, 0);
    let mut failures = Vec::new();
    for (name, expected) in records {
        if let Some(reason) = windows_exemption(name) {
            eprintln!("EXEMPT {name}: {reason}");
            exempt += 1;
            continue;
        }
        let root = tempfile::Builder::new()
            .prefix("b30-")
            .tempdir_in(std::env::temp_dir().canonicalize().unwrap())
            .unwrap();
        assert!(
            root.path()
                .starts_with(std::env::temp_dir().canonicalize().unwrap())
        );
        let observed = std::panic::catch_unwind(|| {
            if name.starts_with("native.") {
                native::replay(name, root.path())
            } else if name.starts_with("hooks.") {
                hooks::replay(name, root.path())
            } else if name.starts_with("capability.") {
                capability::replay(name, root.path())
            } else if name == "changes.excluded" {
                excluded_case(root.path())
            } else {
                assert_eq!(name, "changes.snapshot_and_diff");
                snapshot_case(root.path())
            }
        });
        let Ok(observed) = observed else {
            failures.push(format!("record {name}: replay panicked"));
            replayed += 1;
            continue;
        };
        // Match observe(): serialize first, then replace only the case's temporary root.
        let actual = serde_json::to_string(&observed).unwrap();
        let prefix = serde_json::to_string(root.path().to_str().unwrap()).unwrap();
        let actual = actual.replace(&prefix[1..prefix.len() - 1], "<tmp>");
        let actual = observe_root(
            name,
            serde_json::from_str(&actual).unwrap(),
            root.path().to_str().unwrap(),
        );
        let actual: Value = observe_paths(name, actual);
        // Apply the same existing field observation to the selected platform oracle.
        let expected = observe_paths(name, platform_expected(name, expected, cfg!(windows)));
        let expected = capability::expected_command_list(name, expected);
        if actual != expected {
            failures.push(format!(
                "record {name}: actual={actual}, expected={expected}"
            ));
        }
        replayed += 1;
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
    assert_eq!(replayed + exempt, 60);
    assert_eq!(exempt, if cfg!(windows) { 5 } else { 0 });
    eprintln!("B30: replayed={replayed}, deferred=0, exempt={exempt}, total=60");
}

fn observe_paths(name: &str, mut value: Value) -> Value {
    // Python a61c3013:src/mir/cli/capability.py:90-94 passes Path kwargs;
    // tests/test_w2_b30_capability_frozen.py:250 serializes them with default=str.
    // Normalize only the two synthetic init kwargs, never payload/error text.
    if name.starts_with("capability.") && value["value"][4][0][0] == "init" {
        for (key, leaf) in [("config_path", "config"), ("capability_home", "home")] {
            if value["value"][4][0][2][key] == format!(r"<tmp>\{leaf}") {
                value["value"][4][0][2][key] = json!(format!("<tmp>/{leaf}"));
            }
        }
    }
    // Python a61c3013:src/mir/cli/project_hooks.py:71-72 uses str(binary), cwd=root;
    // tests/test_w2_b30_capability_frozen.py:250 serializes the Path with default=str.
    if name == "hooks.check.normal" {
        for (field, from, to) in [
            (
                "/value/4/0/argv/0",
                r"<tmp>\project\.mir\bin\project-hooks",
                "<tmp>/project/.mir/bin/project-hooks",
            ),
            ("/value/4/0/cwd", r"<tmp>\project", "<tmp>/project"),
        ] {
            if value.pointer(field) == Some(&json!(from)) {
                *value.pointer_mut(field).unwrap() = json!(to);
            }
        }
    }
    value
}

#[test]
fn wt_core_a_paths() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-capability.json")).unwrap();
    for (name, expected) in records.as_object().unwrap() {
        assert_eq!(observe_paths(name, expected.clone()), *expected);
        if !name.starts_with("capability.") || expected["value"][4][0][0] != "init" {
            continue;
        }
        let mut input = expected.clone();
        for key in ["config_path", "capability_home"] {
            if let Some(text) = input["value"][4][0][2][key].as_str() {
                input["value"][4][0][2][key] = json!(text.replace('/', r"\"));
            }
        }
        input["value"][2] = json!(r"keep <tmp>\config");
        input["value"][4][0][2]["other"] = json!(r"<tmp>\home");
        let mut wanted = expected.clone();
        wanted["value"][2] = input["value"][2].clone();
        wanted["value"][4][0][2]["other"] = input["value"][4][0][2]["other"].clone();
        assert_eq!(observe_paths(name, input.clone()), wanted, "{name}");
        assert_eq!(observe_paths("hooks.path.normal", input.clone()), input);
    }
}

#[test]
fn wt_core_a_c_paths() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-capability.json")).unwrap();
    let expected = &records["hooks.check.normal"];
    assert_eq!(
        observe_paths("hooks.check.normal", expected.clone()),
        *expected
    );
    let mut input = expected.clone();
    input["value"][4][0]["argv"][0] = json!(r"<tmp>\project\.mir\bin\project-hooks");
    input["value"][4][0]["cwd"] = json!(r"<tmp>\project");
    input["value"][4][0]["argv"][1] = json!(r"<tmp>\project");
    input["value"][2] = json!(r"keep <tmp>\project");
    let mut wanted = expected.clone();
    wanted["value"][4][0]["argv"][1] = input["value"][4][0]["argv"][1].clone();
    wanted["value"][2] = input["value"][2].clone();
    assert_eq!(observe_paths("hooks.check.normal", input.clone()), wanted);
    assert_eq!(observe_paths("hooks.check.other", input.clone()), input);
    input["value"][4][0]["argv"][0] = json!(r"elsewhere\project\.mir\bin\project-hooks");
    input["value"][4][0]["cwd"] = json!(r"<tmp>\project-other");
    assert_eq!(observe_paths("hooks.check.normal", input.clone()), input);
}

fn platform_expected(name: &str, expected: &Value, windows: bool) -> Value {
    // Only these explicitly uncaptured records retain the Unix expectation.
    if !windows
        || matches!(
            name,
            "changes.snapshot_and_diff"
                | "hooks.check.not-executable"
                | "hooks.path.normal"
                | "native.project_hooks.linked"
                | "native.project_hooks.linked-parent"
        )
    {
        return expected.clone();
    }
    let capture: Value = serde_json::from_str(
        &include_str!("fixtures/w2/b30-capability-windows-all.json").replace("{ROOT}", "<tmp>"),
    )
    .unwrap();
    capture["records"]
        .get(name)
        .expect("record missing from Windows capture")
        .clone()
}

#[test]
fn wt_core_a_f_expectations() {
    let unix: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-capability.json")).unwrap();
    let capture: Value = serde_json::from_str(
        &include_str!("fixtures/w2/b30-capability-windows-all.json").replace("{ROOT}", "<tmp>"),
    )
    .unwrap();
    let captured = capture["records"].as_object().unwrap();
    // These records are absent from the PC capture; retain their existing handling.
    let absent = [
        "changes.snapshot_and_diff",
        "hooks.check.not-executable",
        "hooks.path.normal",
        "native.project_hooks.linked",
        "native.project_hooks.linked-parent",
    ];
    assert_eq!(captured.len(), 55);
    assert_eq!(capture["exempt"], json!(absent));
    assert_eq!(
        captured.len() + absent.len(),
        unix.as_object().unwrap().len()
    );
    let single: Value = serde_json::from_str(
        &include_str!("fixtures/w2/b30-capability-windows.json").replace("{ROOT}", "<tmp>"),
    )
    .unwrap();
    assert_eq!(captured["hooks.check.uninstalled"], single);
    for name in captured.keys() {
        assert!(unix.get(name).is_some(), "unknown captured record {name}");
    }
    for (name, expected) in unix.as_object().unwrap() {
        assert_eq!(platform_expected(name, expected, false), *expected);
        let wanted = if absent.contains(&name.as_str()) {
            assert!(!captured.contains_key(name));
            expected
        } else {
            captured
                .get(name)
                .expect("record missing from Windows capture")
        };
        assert_eq!(platform_expected(name, expected, true), *wanted, "{name}");
        // Distinguish selection even where the two platform values happen to match.
        let sentinel = json!({"wrong_unix_expectation":name});
        let wanted = if absent.contains(&name.as_str()) {
            &sentinel
        } else {
            wanted
        };
        assert_eq!(platform_expected(name, &sentinel, true), *wanted, "{name}");
    }
}
