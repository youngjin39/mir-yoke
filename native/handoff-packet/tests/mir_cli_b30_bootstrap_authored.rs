//! All 83 cells are compared to the unmodified Python capture, including call traces.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::bootstrap::{self as m, Error, Host};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};
#[path = "../src/digest.rs"]
mod digest;

fn put(root: &Path, name: &str, body: impl AsRef<[u8]>) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, body).unwrap();
}
fn py_json(value: &Value) -> String {
    match value {
        Value::Array(v) => format!("[{}]", v.iter().map(py_json).collect::<Vec<_>>().join(", ")),
        Value::Object(v) => {
            let sorted: BTreeMap<_, _> = v.iter().collect();
            format!(
                "{{{}}}",
                sorted
                    .iter()
                    .map(|(k, v)| format!("{}: {}", py_json(&json!(k)), py_json(v)))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        _ => value
            .to_string()
            .chars()
            .map(|c| {
                if c.is_ascii() {
                    c.to_string()
                } else {
                    c.encode_utf16(&mut [0; 2])
                        .iter()
                        .map(|u| format!("\\u{u:04x}"))
                        .collect()
                }
            })
            .collect(),
    }
}
fn compact(value: Value) -> Value {
    let text = py_json(&value);
    if text.len() <= 512 {
        value
    } else {
        json!({"len": text.len(), "sha256": digest::sha256(text.as_bytes())})
    }
}
fn normalise(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => {
            let s = s.replace(root.to_str().unwrap(), "<tmp>");
            #[cfg(windows)]
            let s = s
                .replace("\\\\?\\", "")
                .replace(
                    root.to_str().unwrap().trim_start_matches("\\\\?\\"),
                    "<tmp>",
                )
                .replace(
                    &root
                        .to_str()
                        .unwrap()
                        .trim_start_matches("\\\\?\\")
                        .replace('\\', "/"),
                    "<tmp>",
                )
                .replace("<tmp>\\", "<tmp>/");
            json!(s)
        }
        Value::Array(v) => Value::Array(v.into_iter().map(|v| normalise(v, root)).collect()),
        Value::Object(v) => Value::Object(
            v.into_iter()
                .map(|(k, v)| (k, normalise(v, root)))
                .collect(),
        ),
        v => v,
    }
}
fn onboarding() -> Value {
    json!({"schema_version":1,"profile":"content_workspace",
        "archives":[{"path":"notes","kind":"directory"}],"scan":{}})
}
struct Fake {
    root: PathBuf,
    replies: Vec<(i32, Vec<u8>)>,
    calls: Vec<Value>,
}
impl Fake {
    fn new(root: &Path, replies: Vec<(i32, Vec<u8>)>) -> Self {
        Self {
            root: root.into(),
            replies,
            calls: vec![],
        }
    }
}
impl Host for Fake {
    fn env(&mut self, name: &str) -> Option<String> {
        panic!("unexpected env {name}")
    }
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error> {
        Ok(path.canonicalize().unwrap())
    }
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error> {
        if path == Path::new("~") {
            Ok(self.root.clone())
        } else {
            Ok(path.into())
        }
    }
    fn is_dir(&mut self, path: &Path) -> bool {
        path.is_dir()
    }
    fn writable(&mut self, _: &Path) -> bool {
        panic!("unexpected writable")
    }
    fn device(&mut self, _: &Path) -> Result<u64, Error> {
        panic!("unexpected device")
    }
    fn run(&mut self, request: &m::CommandRequest) -> Result<m::CommandOutput, Error> {
        assert_eq!(request.cwd, self.root);
        assert!(request.stdin_null && request.capture_output && !request.check);
        assert!(request.environment.is_empty());
        assert_eq!(request.text, request.argv.get(1).unwrap() != "show");
        let reply = self
            .replies
            .get(self.calls.len())
            .expect("unexpected process")
            .clone();
        self.calls
            .push(json!([request.argv, request.cwd, -3, null]));
        Ok(m::CommandOutput {
            returncode: reply.0,
            stdout: reply.1,
            stderr: vec![],
        })
    }
}
fn ok_reply(text: &str) -> (i32, Vec<u8>) {
    (0, text.as_bytes().to_vec())
}
#[cfg(unix)]
fn link(target: &Path, path: &Path) {
    std::os::unix::fs::symlink(target, path).unwrap();
}
#[cfg(windows)]
fn link(_: &Path, _: &Path) {
    unreachable!("symlink cells are explicitly exempt on Windows")
}
fn files(root: &Path, current: &Path, result: &mut BTreeMap<String, Value>) {
    let mut entries: Vec<_> = fs::read_dir(current)
        .unwrap()
        .map(|p| p.unwrap().path())
        .collect();
    entries.sort();
    for path in entries {
        if path.is_file() {
            let body = fs::read_to_string(&path)
                .unwrap()
                .replace("\r\n", "\n")
                .replace('\r', "\n");
            let body = normalise(json!(body), root);
            result.insert(
                path.strip_prefix(root)
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .replace('\\', "/"),
                compact(body),
            );
        } else if path.is_dir() && !path.is_symlink() {
            files(root, &path, result);
        }
    }
}
fn authored(root: &Path, mode: &str) -> Result<Value, Error> {
    let content = mode.starts_with("content");
    if let Some((kind, name)) = mode.split_once(':') {
        if kind == "dir_file" {
            put(root, name, "blocked");
        } else {
            fs::create_dir(root.join("target")).unwrap();
            link(&root.join("target"), &root.join(name));
        }
    }
    if mode == "kept" {
        for name in [
            "harness_a.toml",
            ".mir/repo-profile.toml",
            "tasks/tdd.json",
            "tasks/plan.md",
        ] {
            put(root, name, "authored");
        }
    }
    if mode == "content_kept" {
        put(root, "docs/project-purpose.md", "authored purpose");
        let mut value = onboarding();
        value["extra"] = json!(true);
        put(root, "config/content-onboarding.json", py_json(&value));
    }
    if mode == "content_invalid" {
        put(root, "config/content-onboarding.json", "{}");
    }
    if mode == "replace" {
        put(root, "CLAUDE.md", "Provider contract");
        put(
            root,
            "config/adopter-payload.json",
            py_json(&json!({"files":[{
            "path":"CLAUDE.md","sha256":digest::sha256(b"Provider contract")}]})),
        );
    }
    let mut host = Fake::new(
        root,
        vec![ok_reply(if mode == "bad_commit" {
            "invalid"
        } else {
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        })],
    );
    m::ensure_authored_files(
        root,
        "sample",
        if content {
            "content_workspace"
        } else {
            "code_app"
        },
        "Build tools",
        &["Rust".into()],
        content.then_some(&onboarding()),
        content.then_some("Purpose\n"),
        mode == "replace",
        &mut host,
    )?;
    let mut written = BTreeMap::new();
    files(root, root, &mut written);
    Ok(json!([[null, host.calls], written]))
}
fn validate(root: &Path, mode: &str) -> Result<Value, Error> {
    let mut host = Fake::new(root, vec![]);
    let mut body = m::repo_profile_text(
        root,
        "sample",
        "code_app",
        "Build tools",
        &["Rust".into()],
        "unverified",
        &mut host,
    )?;
    body = match mode {
        "invalid" => "[".into(),
        "no_repo" => "".into(),
        "repo_type" => "repo=1".into(),
        "execution_type" => format!("execution=1\n{}", body.split("[execution]").next().unwrap()),
        "gates_type" => format!("gates=1\n{}", body.split("[gates]").next().unwrap()),
        "identity" => body.replace("Build tools", "TODO"),
        "stack" => body.replace("[\"Rust\"]", "\"Rust\""),
        "mismatch" => body.replace(
            "non_code_profile = \"code_app\"",
            "non_code_profile = \"other\"",
        ),
        "memory" => body.replace(
            "requires_memory_store = true",
            "requires_memory_store = false",
        ),
        "capabilities" => body.replace(
            "requires_global_capabilities = true",
            "requires_global_capabilities = false",
        ),
        _ => body,
    };
    if mode != "missing" {
        put(root, "profile.toml", body);
    }
    m::validate_existing_profile(&root.join("profile.toml"), "code_app")
}
fn release(root: &Path, mode: &str) -> Result<Value, Error> {
    let boundary = json!({"schema_version":1,"provider_markers":["provider"],
        "provider_text_markers":[{"path":"CLAUDE.md","contains":"Provider"}]});
    put(root, "provider", "marker");
    put(root, "CLAUDE.md", "Provider contract");
    let controls = [
        "config/adopter-boundary.json",
        "config/adopter-payload.json",
    ];
    put(root, controls[0], py_json(&boundary));
    put(
        root,
        controls[1],
        py_json(&json!({"files":[{"path":"CLAUDE.md",
        "sha256":digest::sha256(b"Provider contract")}]})),
    );
    let mut replies = vec![
        ok_reply("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        (0, fs::read(root.join(controls[0])).unwrap()),
        (0, fs::read(root.join(controls[1])).unwrap()),
    ];
    match mode {
        "git_error" => replies[0] = (1, vec![]),
        "bad_commit" => replies[0] = ok_reply("invalid"),
        "show_error" => replies[1] = (1, vec![]),
        "show_error_same" => replies[1].0 = 1,
        "control_changed" => replies[2] = ok_reply("different"),
        "contract_changed" | "rewrite_changed" => put(root, "CLAUDE.md", "Authored"),
        "no_marker" => fs::remove_file(root.join("provider")).unwrap(),
        "no_text" => {
            let mut boundary = boundary;
            boundary["provider_text_markers"] = json!([]);
            put(root, controls[0], py_json(&boundary));
            replies[1] = (0, fs::read(root.join(controls[0])).unwrap());
        }
        "invalid_boundary" => put(root, controls[0], "{}"),
        _ => {}
    }
    if mode.starts_with("rewrite") {
        let value = m::rewrite_release_matched(
            root,
            &[
                ("CLAUDE.md".into(), "Product".into()),
                ("missing".into(), "new".into()),
            ],
        )?;
        return Ok(json!([
            value,
            fs::read_to_string(root.join("CLAUDE.md")).unwrap()
        ]));
    }
    let mut host = Fake::new(root, replies);
    let value = m::is_raw_provider_checkout(root, &mut host)?;
    Ok(json!([value, host.calls]))
}
fn ownership(root: &Path, mode: &str) -> Result<Value, Error> {
    const PROVIDER: &str = "https://example.invalid/provider.git";
    if mode != "missing" {
        put(
            root,
            "config/capability-sources.json",
            match mode {
                "invalid" => "{".into(),
                "no_source" => "{}".into(),
                _ => py_json(&json!({"source":{"url":PROVIDER}})),
            },
        );
    }
    let mut replies = vec![ok_reply("")];
    match mode {
        "git_error" => replies = vec![(1, vec![])],
        "foreign" | "provider" | "push_error" | "mixed" => {
            replies = vec![
                ok_reply(" origin \n"),
                match mode {
                    "push_error" => (1, vec![]),
                    "provider" => ok_reply("git@example.invalid:provider.git\n"),
                    _ => ok_reply("https://example.invalid/product.git\n"),
                },
            ];
            if mode == "mixed" {
                replies = vec![
                    ok_reply("z\na\n"),
                    ok_reply(&format!("{PROVIDER}\nDISABLED\n")),
                    ok_reply("DISABLED\n"),
                ];
            }
        }
        "git_error_output" => {
            replies = vec![
                (1, b" origin \n".to_vec()),
                ok_reply("https://example.invalid/product.git\n"),
            ]
        }
        _ => {}
    }
    let mut host = Fake::new(root, replies);
    let value = m::source_control_ownership(root, &mut host)?;
    Ok(json!([value, host.calls]))
}
fn case(root: &Path, name: &str) -> Result<Value, Error> {
    let (kind, mode) = name.split_once('.').unwrap_or((name, ""));
    match kind {
        "memory" => Ok(json!(m::memory_config_text(
            "sample",
            if mode == "no_onboarding" {
                "content_workspace"
            } else {
                mode
            },
            (mode != "no_onboarding").then_some(&onboarding())
        )?)),
        "contract" => Ok(json!(m::product_contract_text(
            "sample",
            mode,
            "Build tools"
        ))),
        "profile_text" => {
            let (profile, index) = mode.split_once('.').unwrap();
            let stack = match index {
                "0" => vec![],
                "1" => vec!["Rust".into()],
                _ => vec!["Rust".into(), "SQL".into(), "\u{e9}".into()],
            };
            let mut host = Fake::new(root, vec![]);
            Ok(json!(m::repo_profile_text(
                root,
                "sample-project",
                profile,
                "Build \"tools\"\n\u{e9}",
                &stack,
                &"b".repeat(40),
                &mut host
            )?))
        }
        "authored" => authored(root, mode),
        "validate" => validate(root, mode),
        "release" => release(root, mode),
        "ownership" => ownership(root, mode),
        "payload" => {
            let bodies = [
                None,
                Some("{"),
                Some("[]"),
                Some("{}"),
                Some(concat!(
                    "{\"files\":[null,1,{}, {\"path\":\"a\",\"sha256\":2},",
                    "{\"path\":\"a\",\"sha256\":\"last\"}]}"
                )),
            ];
            if let Some(body) = bodies[mode.parse::<usize>().unwrap()] {
                put(root, "config/adopter-payload.json", body);
            }
            m::release_payload_digests(root).map(|v| json!(v))
        }
        "safe" => {
            let mut path = root.join("file");
            if ["file", "link", "nested", "escape"].contains(&mode) {
                put(root, "file", "body");
            }
            if mode == "directory" {
                fs::create_dir(&path).unwrap();
            }
            if mode == "link" || mode == "escape" {
                link(
                    if mode == "link" {
                        &path
                    } else {
                        root.parent().unwrap()
                    },
                    &root.join("link"),
                );
                path = root.join("link");
            }
            if mode == "nested" {
                link(root, &root.join("link"));
                path = root.join("link/file");
            }
            Ok(json!(m::is_safe_existing_project_file(root, &path)))
        }
        "urls" => Ok(json!(
            [
                "https://example.invalid/provider.git",
                "SSH://u@EXAMPLE.invalid:22/a.git",
                "git@example.invalid:a.git/",
                "https://EXAMPLE.invalid:443/a.git",
                "ssh://host:123/a.git",
                "https://host:bad/a.git",
                "https://[invalid",
                "",
                " nonsense ",
                "C:\\repo.git",
                "https://user:pass@host/A.git/?q=x"
            ]
            .map(m::normalise_git_url)
        )),
        "urls_edge" => Ok(json!(
            [
                "a/b@host:x/y",
                "dir/sub:x",
                " \x1chost:a.git\x1f",
                "https://ho\tst/a.git",
                "https://host:+1/a.git",
                "ssh://a/b@host/c.git"
            ]
            .map(m::normalise_git_url)
        )),
        _ => panic!("unmapped frozen record {name}"),
    }
}
#[test]
fn replay_all_83_frozen_records() {
    let records: BTreeMap<String, Value> =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-authored.json")).unwrap();
    assert_eq!(records.len(), 83);
    let mut profiles: Vec<_> = m::PROFILE_CHOICES.to_vec();
    profiles.sort();
    let captured_profiles: Vec<_> = records
        .keys()
        .filter_map(|name| name.strip_prefix("memory."))
        .filter(|name| *name != "no_onboarding")
        .collect();
    assert_eq!(profiles, captured_profiles);
    let mut replayed = 0;
    let mut exempt = 0;
    let mut failures = vec![];
    for (name, expected) in records {
        if cfg!(windows)
            && (name.starts_with("authored.dir_link:")
                || ["safe.link", "safe.nested", "safe.escape"].contains(&name.as_str()))
        {
            exempt += 1;
            println!("{name}: exempt (Windows symlink privilege)");
            continue;
        }
        let temp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        let root = temp.path().canonicalize().unwrap();
        let actual = match case(&root, &name) {
            Ok(value) => json!({"value":compact(normalise(value,&root))}),
            Err(e) => normalise(json!({"error":[e.class,e.message]}), &root),
        };
        replayed += 1;
        println!("{name}: replayed");
        if actual != expected {
            failures.push(format!("{name}\nactual: {actual}\nexpected: {expected}"));
        }
    }
    assert_eq!(
        (replayed, exempt),
        if cfg!(windows) { (76, 7) } else { (83, 0) }
    );
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
