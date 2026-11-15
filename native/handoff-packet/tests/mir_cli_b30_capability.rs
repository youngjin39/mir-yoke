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
            for separator in ["/", r"\"] {
                text = text.replace(
                    &format!("directory: '{spelling}{separator}"),
                    &format!("directory: '<tmp>{separator}"),
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

#[path = "b30_capability_support/mod.rs"]
mod capability;
#[path = "b30_hooks_support/mod.rs"]
mod hooks;
#[path = "b30_native_support/mod.rs"]
mod native;

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
        let observed = if name.starts_with("native.") {
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
        assert_eq!(&actual, expected, "record {name}");
        replayed += 1;
    }
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
