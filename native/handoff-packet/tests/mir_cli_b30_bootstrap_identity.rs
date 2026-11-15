//! Replay all bootstrap identity cells against the frozen, unmodified Python oracle.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::bootstrap::{self as m, Error, Host};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::Path, path::PathBuf};

#[path = "../src/digest.rs"]
mod digest;

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|v| (*v).into()).collect()
}
fn success(value: impl serde::Serialize) -> Value {
    json!({"value": value})
}
fn outcome<T: serde::Serialize>(value: Result<T, Error>) -> Value {
    match value {
        Ok(value) => success(value),
        Err(error) => json!({"error": [error.class, error.message]}),
    }
}
fn put(root: &Path, name: &str, body: impl AsRef<[u8]>) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, body).unwrap();
}
// json.dumps(sort_keys=True) uses spaces and ASCII escapes, including surrogate pairs.
fn py_json(value: &Value) -> String {
    match value {
        Value::Array(values) => format!(
            "[{}]",
            values.iter().map(py_json).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(values) => {
            let sorted: BTreeMap<_, _> = values.iter().collect();
            format!(
                "{{{}}}",
                sorted
                    .iter()
                    .map(|(key, value)| format!("{}: {}", py_json(&json!(key)), py_json(value)))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        _ => serde_json::to_string(value)
            .unwrap()
            .chars()
            .map(|ch| {
                if ch.is_ascii() {
                    ch.to_string()
                } else {
                    ch.encode_utf16(&mut [0; 2])
                        .iter()
                        .map(|unit| format!("\\u{unit:04x}"))
                        .collect::<String>()
                }
            })
            .collect(),
    }
}
fn observe(mut value: Value, tmp: &Path) -> Value {
    #[cfg(windows)]
    {
        // canonicalize() may add a verbatim prefix absent from the original temp root.
        fn strip_verbatim(value: &mut Value) {
            match value {
                Value::String(text) => *text = text.replace("\\\\?\\", ""),
                Value::Array(values) => values.iter_mut().for_each(strip_verbatim),
                Value::Object(values) => values.values_mut().for_each(strip_verbatim),
                _ => {}
            }
        }
        strip_verbatim(&mut value);
    }
    let text = serde_json::to_string(&value).unwrap();
    let escaped = serde_json::to_string(tmp.to_str().unwrap()).unwrap();
    value = serde_json::from_str(&text.replace(&escaped[1..escaped.len() - 1], "<tmp>")).unwrap();
    #[cfg(windows)]
    {
        let posix = tmp
            .to_str()
            .unwrap()
            .trim_start_matches("\\\\?\\")
            .replace('\\', "/");
        let text = serde_json::to_string(&value).unwrap();
        value = serde_json::from_str(&text.replace(&posix, "<tmp>")).unwrap();
        // The oracle records Path string output on Unix; preserve logical relative paths.
        fn separators(value: &mut Value) {
            match value {
                Value::String(text) => *text = text.replace('\\', "/"),
                Value::Array(values) => values.iter_mut().for_each(separators),
                Value::Object(values) => values.values_mut().for_each(separators),
                _ => {}
            }
        }
        separators(&mut value);
    }
    if let Some(result) = value.get_mut("value") {
        let text = py_json(result);
        if text.len() > 512 {
            *result = json!({"len": text.len(), "sha256": digest::sha256(text.as_bytes())});
        }
    }
    value
}

struct StorageHost<'a> {
    tmp: &'a Path,
    mode: &'a str,
}
impl Host for StorageHost<'_> {
    fn env(&mut self, name: &str) -> Option<String> {
        if self.mode == "unset" {
            return None;
        }
        if self.mode == "wrong" {
            return Some(self.tmp.join("wrong").to_str().unwrap().into());
        }
        if name == "MIR_BOOTSTRAP_RUNTIME_ID" {
            return Some(
                if self.mode == "missing_runtime" {
                    ""
                } else {
                    "runtime"
                }
                .into(),
            );
        }
        let path = match name {
            "UV_CACHE_DIR" => "storage/uv/cache",
            "UV_PYTHON_INSTALL_DIR" => "storage/uv/python",
            "MIR_CAPABILITY_HOME" => "storage/mir/capabilities",
            "UV_TOOL_DIR" => "storage/mir/cli/runtime/tools",
            "UV_TOOL_BIN_DIR" => "storage/mir/cli/runtime/bin",
            "UV_PROJECT_ENVIRONMENT" => "project/.venv",
            _ => panic!("unexpected host environment read: {name}"),
        };
        Some(self.tmp.join(path).to_str().unwrap().into())
    }
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error> {
        Ok(path.into())
    }
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error> {
        Ok(path.into())
    }
    fn is_dir(&mut self, path: &Path) -> bool {
        self.mode != "not_directory"
            && (self.mode != "missing_dirs" || path == self.tmp.join("storage"))
    }
    fn writable(&mut self, _path: &Path) -> bool {
        self.mode != "unwritable"
    }
    fn device(&mut self, path: &Path) -> Result<u64, Error> {
        if self.mode == "stat_error" {
            return Err(Error::new("OSError", "scripted stat failure"));
        }
        Ok(
            if self.mode == "different" && path != self.tmp.join("project")
                || self.mode == "payload_device" && path == self.tmp.join("storage/uv/cache")
            {
                2
            } else {
                1
            },
        )
    }
}

fn parse(tmp: &Path, name: &str) -> Value {
    let mut args = match name {
        "help" => strings(&["--help"]),
        "no_args" => vec![],
        "defaults" => strings(&["--profile", "x"]),
        "unknown" => strings(&["--profile", "x", "--unknown"]),
        "full" => strings(&[
            "--profile",
            "content_workspace",
            "--project-root",
            "project",
            "--slug",
            "slug",
            "--purpose",
            "Curate",
            "--stack",
            "a,b",
            "--stack",
            "c",
            "--archive",
            "a=notes",
            "--storage-root",
            "storage",
            "--json",
            "--finalize",
            "--architecture-initialized",
            "--skip-capability-activation",
            "--allow-incomplete",
        ]),
        _ => strings(&["--profile", "x"]),
    };
    if let Some(option) = name.strip_prefix("missing_") {
        args.push(format!("--{option}"));
    }
    if let Some(option) = name.strip_prefix("value_") {
        args.push(format!("--{option}=x"));
    }
    let result = m::parse(&args, tmp);
    success(
        result
            .value
            .unwrap_or_else(|| json!([result.code, result.stdout, result.stderr])),
    )
}

#[cfg(unix)]
fn symlink(target: &Path, link: &Path) {
    std::os::unix::fs::symlink(target, link).unwrap();
}
#[cfg(windows)]
fn symlink(target: &Path, link: &Path) {
    std::os::windows::fs::symlink_dir(target, link).unwrap();
}
fn content(tmp: &Path, action: &str, index: usize) -> Value {
    let root = tmp.join("project");
    fs::create_dir(&root).unwrap();
    for (name, body) in [
        ("notes/a.md", "searchable alpha"),
        ("notes/b.PDF", "binary"),
        ("notes/c.exe", "ignored"),
        ("other.txt", "another record"),
        ("docs/skip.md", "hidden"),
        (".hidden/a.md", "hidden"),
        ("README.md", "hidden"),
        ("empty/x.bin", "ignored"),
    ] {
        put(&root, name, body);
    }
    if action == "relative" {
        let absolute = root.join("notes");
        let raw = [
            "notes/../other.txt",
            ".",
            "",
            "../escape",
            absolute.to_str().unwrap(),
        ];
        return outcome(m::project_relative(&root, raw[index]));
    }
    if ["discover", "supported", "scan"].contains(&action) {
        let mode = match action {
            "discover" => [
                "notes",
                "other.txt",
                "missing",
                "symlink",
                "nested_symlink",
                "escape_link",
            ][index],
            "supported" => ["notes", "other.txt", "notes/b.PDF", "missing"][index],
            _ => ["notes", "symlink"][index],
        };
        if ["symlink", "nested_symlink", "escape_link"].contains(&mode) {
            let link = root.join(if mode == "nested_symlink" {
                "notes/link"
            } else {
                "link"
            });
            let target = if mode == "escape_link" {
                tmp.into()
            } else {
                root.join("notes")
            };
            symlink(&target, &link);
        }
        let path = root.join(match mode {
            "symlink" | "escape_link" => "link",
            "nested_symlink" => "notes",
            _ => mode,
        });
        return match action {
            "discover" => outcome(m::discoverable_content_files(&root, &path)),
            "supported" => outcome(m::supported_content_files(&root, &path)),
            _ => outcome(m::scan_content_candidates(&root)),
        };
    }
    let archives = if action == "archives" {
        let cases: &[&[&str]] = &[
            &[],
            &[" Notes = notes "],
            &["one=other.txt"],
            &["bad"],
            &["!=notes"],
            &["n=notes", "n=other.txt"],
            &["n=missing"],
            &["n=empty"],
            &["n=notes/b.PDF"],
            &["n=notes", "m=notes/a.md"],
            &["n=notes/a.md", "m=notes"],
            &["n=other.txt", "m=other.txt"],
            &["n=../escape"],
            &["n=."],
            &["bad=invalid.txt"],
            &["n=notes/c.exe"],
            &["n=short.txt"],
            &["n=link"],
        ];
        match index {
            12 => put(tmp, "escape/a.md", "searchable"),
            14 => put(&root, "invalid.txt", [0xff]),
            16 => put(&root, "short.txt", "tiny"),
            17 => symlink(&root.join("notes"), &root.join("link")),
            _ => {}
        }
        strings(cases[index])
    } else {
        let cases: &[&[&str]] = &[&[], &["n=notes"], &["n=notes/a.md", "m=other.txt"]];
        strings(cases[index])
    };
    if action == "archives" {
        outcome(m::parse_content_archives(&root, &archives))
    } else {
        outcome(m::build_content_onboarding(
            &root,
            "Curate records",
            &strings(&["text"]),
            &archives,
        ))
    }
}

fn load(tmp: &Path, index: usize) -> Value {
    let path = tmp.join("manifest.json");
    let manifest = json!({"schema_version": 1, "profile": "content_workspace",
        "archives": [{}], "scan": {}});
    let bytes = match index {
        0 => None,
        1 => Some(b"{".to_vec()),
        2 => Some(b"[]".to_vec()),
        3 => Some(b"{}".to_vec()),
        4 => Some(vec![0xff]),
        _ => {
            let mut value = manifest;
            match index {
                5 => {}
                6 => value["schema_version"] = json!(2),
                7 => value["profile"] = json!("code_app"),
                8 => value["archives"] = json!([]),
                9 => value["archives"] = json!({}),
                10 => value["scan"] = json!([]),
                11 => value["scan"] = json!({"unclassified": ["notes"]}),
                _ => panic!("unknown load cell: {index}"),
            }
            Some(serde_json::to_vec(&value).unwrap())
        }
    };
    if let Some(bytes) = bytes {
        fs::write(&path, bytes).unwrap();
    }
    outcome(m::load_content_onboarding(&path))
}
fn replay(name: &str, tmp: &Path) -> Value {
    let (action, cell) = name.split_once('.').unwrap();
    if action == "parse" {
        return parse(tmp, cell);
    }
    if action == "storage" {
        let disk = tmp.join("storage");
        return outcome(m::storage_preflight(
            &tmp.join("project"),
            if cell == "default" { None } else { Some(&disk) },
            &mut StorageHost { tmp, mode: cell },
        ));
    }
    if action == "definition" {
        assert_eq!(cell, "text");
        return success(m::project_definition_text(
            "Curate records",
            &strings(&["a", "b"]),
        ));
    }
    let index: usize = cell.parse().unwrap();
    match action {
        "slug" => outcome(m::normalise_slug(
            &[
                " Mixed SLUG! ".into(),
                "".into(),
                "___".into(),
                "a".repeat(64),
                "a".repeat(65),
                "\u{e9}".into(),
                "a__b-c".into(),
                "PROJECT".into(),
            ][index],
        )),
        "stack" => {
            let cases: &[&[&str]] = &[&[], &[" a,b ", "b,,C", "a"], &["TODO", "todo"], &[" , "]];
            success(m::normalise_stack(&strings(cases[index])))
        }
        "identity" => {
            let cases: &[(Option<&str>, &[&str])] = &[
                (None, &[]),
                (Some(" "), &["text"]),
                (Some("a\nb"), &["text"]),
                (Some("a\rb"), &["text"]),
                (Some("TODO mission"), &["text"]),
                (Some("Curate records"), &[]),
                (Some("Curate records"), &["unknown", "TODO"]),
                (Some("Curate records"), &["text"]),
                (Some("Curate records"), &[""]),
            ];
            success(m::validate_project_identity(
                cases[index].0,
                &strings(cases[index].1),
            ))
        }
        "relative" | "discover" | "supported" | "scan" | "archives" | "build" => {
            content(tmp, action, index)
        }
        "query" => outcome(m::acceptance_query(
            [
                "small alpha searchable",
                "TODO placeholder unknown",
                "123456",
                "\u{e9}\u{e9}\u{e9}\u{e9}\u{e9}\u{e9}",
                "tiny",
            ][index],
            "notes",
        )),
        "query_edge" => outcome(m::acceptance_query(
            [
                "de\u{17f}cribe searchable",
                "DESCR\u{130}BE descr\u{131}be searchable",
                "\u{e9}\u{e9}\u{e9} tiny searchable",
                "abc\u{301}def searchable",
            ][index],
            "notes",
        )),
        "stack_edge" => {
            let cases: &[&[&str]] = &[&[" a\x1c", "\x1fb,\x1c"]];
            success(m::normalise_stack(&strings(cases[index])))
        }
        "identity_edge" => {
            let cases: &[(Option<&str>, &[&str])] = &[
                (Some("descr\u{130}be it"), &["descr\u{131}be"]),
                (
                    Some("todoist planning"),
                    &["mytodo", "todo_list", "de\u{17f}cribe"],
                ),
                (
                    Some("Curate records"),
                    &["replace-me", "replace me", "replaceme"],
                ),
            ];
            success(m::validate_project_identity(
                cases[index].0,
                &strings(cases[index].1),
            ))
        }
        "load" => load(tmp, index),
        "globs" => success(m::content_archive_globs(
            &json!({"archives": ([json!([]), json!([
            null, {}, {"path": "notes", "kind": "directory"},
            {"path": "one.md", "kind": "file"}, {"path": "one.md", "kind": "file"}
        ])][index])}),
        )),
        "args" => outcome(m::content_archive_args(
            &json!({"archives": ([json!([]), json!([
            null, {"classification": "project-definition"},
            {"classification": "notes", "path": "notes"}
        ]), json!([{}])][index])}),
        )),
        _ => panic!("unhandled frozen record: {name}"),
    }
}

#[test]
fn every_frozen_record_replays_exactly() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-identity.json")).unwrap();
    assert_eq!(records.as_object().unwrap().len(), 118);
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        if cfg!(windows)
            && [
                "discover.3",
                "discover.4",
                "discover.5",
                "scan.1",
                "archives.17",
            ]
            .contains(&name.as_str())
        {
            eprintln!("EXEMPT {name}: symlink creation requires Windows host privilege");
            exempt += 1;
            continue;
        }
        let tmp = tempfile::Builder::new()
            .prefix("b30-bootstrap-")
            .tempdir_in(std::env::temp_dir().canonicalize().unwrap())
            .unwrap();
        assert!(
            tmp.path()
                .starts_with(std::env::temp_dir().canonicalize().unwrap())
        );
        let actual = observe(replay(name, tmp.path()), tmp.path());
        assert_eq!(&actual, expected, "record {name}");
        replayed += 1;
        eprintln!("REPLAY {name}");
    }
    assert_eq!(replayed + exempt, 118);
    assert_eq!(exempt, if cfg!(windows) { 5 } else { 0 });
    eprintln!("B30 bootstrap identity: replayed={replayed}, exempt={exempt}, total=118");
}

#[cfg(windows)]
#[test]
fn wt_path_content_root_spellings_keep_containment() {
    let temp = tempfile::tempdir().unwrap();
    let verbatim = temp.path().canonicalize().unwrap();
    let plain = handoff_packet::supply::plain(verbatim.clone());
    fs::create_dir(plain.join("notes")).unwrap();
    for root in [&plain, &verbatim] {
        let (path, relative) = m::project_relative(root, "notes").unwrap();
        assert_eq!(path, root.join("notes"));
        assert_eq!(relative, "notes");
        for raw in [".", "../outside", plain.to_str().unwrap()] {
            assert!(m::project_relative(root, raw).is_err(), "{root:?}: {raw}");
        }
    }
    let outside = tempfile::tempdir().unwrap();
    let result = std::process::Command::new("cmd.exe")
        .args(["/D", "/C", "mklink", "/J"])
        .arg(plain.join("escape"))
        .arg(handoff_packet::supply::plain(outside.path().to_owned()))
        .current_dir(&plain)
        .env("HOME", &plain)
        .output()
        .unwrap();
    assert!(result.status.success(), "{result:?}");
    assert!(m::project_relative(&verbatim, "escape").is_err());
}

#[cfg(windows)]
#[path = "support/wt_path.rs"]
mod wt_path_frozen;

#[cfg(windows)]
#[test]
fn wt_path_content_matches_windows_capture() {
    let (_temp, root, records) = wt_path_frozen::setup();
    let verbatim = root.canonicalize().unwrap();
    let mut checked = 0;
    for record in records {
        let Some(raw) = record["route"].as_str().unwrap().strip_prefix("content.") else {
            continue;
        };
        let (base, raw) = match raw {
            "verbatim_root" => (&verbatim, "notes"),
            "canonical_root" => (&root, "notes"),
            _ => (&root, raw),
        };
        match m::project_relative(base, raw) {
            Ok((path, relative)) => assert_eq!(
                json!([path.to_str().unwrap(), relative]),
                record["value"],
                "{raw}"
            ),
            Err(error) => {
                assert_eq!(error.class, record["error"].as_str().unwrap(), "{raw}");
                assert_eq!(error.message, record["message"].as_str().unwrap(), "{raw}");
                assert!(record["errno"].is_null() && record["winerror"].is_null());
            }
        }
        checked += 1;
    }
    assert_eq!(checked, 11);
}
