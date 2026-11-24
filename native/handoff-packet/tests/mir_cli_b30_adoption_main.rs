//! Frozen adoption main oracle; every expectation comes from the Python capture.
#![forbid(unsafe_code)]
#[cfg(windows)]
#[path = "support/windows_oracle.rs"]
mod windows_oracle;
use handoff_packet::mir_cli::bootstrap_adoption::{self as m, Error, Host};
use serde_json::{Value, json};
use std::{
    fs, io,
    path::{Path, PathBuf},
};
#[path = "../src/digest.rs"]
mod digest;

fn put(root: &Path, name: &str, body: impl AsRef<[u8]>) -> PathBuf {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, body).unwrap();
    path
}
fn py_json(v: &Value) -> String {
    match v {
        Value::Array(a) => format!("[{}]", a.iter().map(py_json).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => format!(
            "{{{}}}",
            o.iter()
                .map(|(k, v)| format!("{}: {}", py_json(&json!(k)), py_json(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        _ => serde_json::to_string(v)
            .unwrap()
            .chars()
            .map(|c| {
                if c.is_ascii() {
                    c.to_string()
                } else {
                    c.encode_utf16(&mut [0; 2])
                        .iter()
                        .map(|u| format!("\\u{u:04x}"))
                        .collect::<String>()
                }
            })
            .collect(),
    }
}
fn raw_observation(v: Value, root: &Path) -> Value {
    fn normalize(v: Value, root: &str) -> Value {
        match v {
            Value::String(s) => {
                #[cfg(windows)]
                let s = windows_oracle::root(&s, root, "<tmp>");
                json!(s.replace(root, "<tmp>"))
            }
            Value::Array(a) => a.into_iter().map(|v| normalize(v, root)).collect(),
            Value::Object(o) => o
                .into_iter()
                .map(|(k, v)| (k.replace(root, "<tmp>"), normalize(v, root)))
                .collect(),
            v => v,
        }
    }
    let root_text = root.to_str().unwrap();
    let v = normalize(v, root_text);
    #[cfg(windows)]
    let mut v = normalize(
        v,
        &root_text.trim_start_matches("\\\\?\\").replace('\\', "/"),
    );
    // Path-valued installer mock arguments use the same spelling as validator
    // mocks. Receipt bytes and arbitrary text are checked without this conversion.
    #[cfg(windows)]
    if let Some(installs) = v
        .pointer_mut("/value/installs")
        .and_then(Value::as_array_mut)
    {
        for install in installs {
            for key in ["source_root", "local_source"] {
                if let Some(path) = install[1][key].as_str() {
                    install[1][key] = json!(path.replace('\\', "/"));
                }
            }
        }
    }
    v
}
fn observe(v: Value, root: &Path) -> Value {
    let mut v = raw_observation(v, root);
    if let Some(value) = v.get_mut("value") {
        let text = py_json(value);
        if text.len() > 512 {
            *value = json!({"len":text.len(), "sha256":digest::sha256(text.as_bytes())});
        }
    }
    v
}
fn outcome<T: serde::Serialize>(result: Result<T, Error>) -> Value {
    match result {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":[e.class(), e.to_string()]}),
    }
}
struct Observer {
    root: PathBuf,
    mode: String,
    argv: Vec<String>,
    stdout: String,
    stderr: String,
    calls: Vec<Value>,
    installs: Vec<Value>,
    surfaces: Value,
}
impl Observer {
    fn new(root: &Path, mode: &str) -> Self {
        Self {
            root: root.into(),
            mode: mode.into(),
            argv: vec![],
            stdout: String::new(),
            stderr: String::new(),
            calls: vec![],
            installs: vec![],
            surfaces: json!({}),
        }
    }
}
impl Host for Observer {
    fn read(&mut self, path: &Path) -> io::Result<Vec<u8>> {
        assert!(path.starts_with(&self.root), "read outside root: {path:?}");
        fs::read(path)
    }
    fn git(&mut self, _: &m::GitRequest) -> io::Result<bool> {
        panic!("unexpected git")
    }
    fn jq(&mut self, request: &m::JqRequest) -> io::Result<m::JqOutput> {
        self.calls
            .push(json!([request.argv, request.cwd, request.input,
            {"capture_output":request.capture_output, "check":request.check}]));
        if self.mode == "oserror" {
            return Err(io::Error::other("jq unavailable"));
        }
        let stdout: &[u8] = match self.mode.as_str() {
            "empty" => b"",
            "blank" => b" \n",
            "newlines" => b"{\"hooks\":{}}\n\n",
            "no_newline" => b"{\"hooks\":{}}",
            _ => b"{\"hooks\":{\"a\":[]}}\n",
        };
        Ok(m::JqOutput {
            returncode: i32::from(self.mode == "failure"),
            stdout: stdout.into(),
        })
    }
    fn replace(&mut self, source: &Path, destination: &Path) -> io::Result<()> {
        assert_eq!(source.parent(), destination.parent());
        assert!(
            source
                .file_name()
                .unwrap()
                .to_str()
                .unwrap()
                .starts_with(&format!(
                    ".{}.",
                    destination.file_name().unwrap().to_str().unwrap()
                ))
        );
        assert_ne!(fs::read(source).unwrap(), b"previous");
        if self.mode == "overwrite" || self.mode == "replace_failure" {
            assert_eq!(fs::read(destination).unwrap(), b"previous");
        } else {
            assert!(!destination.exists());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(source).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
        if self.mode == "replace_failure" {
            return Err(io::Error::other("replace denied"));
        }
        m::LocalHost.replace(source, destination)
    }
    fn cwd(&mut self) -> io::Result<PathBuf> {
        Ok(self.root.clone())
    }
    fn env(&mut self, name: &str) -> Option<String> {
        assert_eq!(name, if cfg!(windows) { "USERPROFILE" } else { "HOME" });
        Some(self.root.to_str().unwrap().into())
    }
    fn argv(&mut self) -> Vec<String> {
        self.argv.clone()
    }
    fn stdout(&mut self, text: &str) -> io::Result<()> {
        self.stdout.push_str(text);
        Ok(())
    }
    fn stderr(&mut self, text: &str) -> io::Result<()> {
        self.stderr.push_str(text);
        Ok(())
    }
    fn validation(
        &mut self,
        request: &m::ValidationRequest<'_>,
    ) -> Option<Result<m::ValidationOutput, Error>> {
        self.calls.push(request.python_call());
        let name = request.name();
        let errors = if self.mode == name {
            vec![format!("scripted {name}")]
        } else {
            vec![]
        };
        let (evidence, exceptions) = if name == "_validate_surface_contract" {
            (
                if self.mode == "empty_surfaces" {
                    json!({})
                } else {
                    self.surfaces.clone()
                },
                if self.mode == "exceptions" {
                    vec![json!({"surface":"phase2_spec", "reason":"Deferred"})]
                } else {
                    vec![]
                },
            )
        } else {
            (json!({"status":"scripted"}), vec![])
        };
        Some(Ok(m::ValidationOutput {
            errors,
            evidence,
            exceptions,
        }))
    }
    fn digests(&mut self, _: &Path, _: &Value) -> Option<Result<Vec<Value>, Error>> {
        (self.mode == "digest_error").then(|| Err(m::AdoptionError("digest denied".into()).into()))
    }
    fn digest(&mut self, _: &str, _: &Path) -> Option<Result<String, Error>> {
        (self.mode == "list_settings_error").then(|| Err(m::AdoptionError("bad".into()).into()))
    }
    fn install_evaluator(
        &mut self,
        root: &Path,
        source: &Path,
        local: Option<&Path>,
    ) -> Option<Value> {
        self.installs
            .push(json!([[root], {"source_root":source, "local_source":local}]));
        (self.mode != "install_none").then(|| json!({"path":".mir/bin/evaluator","sha256":"pin"}))
    }
}
fn digest_case(root: &Path, mode: &str) -> Value {
    let path = put(root, "proof", "plain\n\u{e9}");
    let mut host = Observer::new(root, mode);
    if mode == "missing" {
        fs::remove_file(&path).unwrap();
    }
    let result = if mode.starts_with("list") {
        put(root, "z", "last");
        let mut surfaces = json!({"b":{"evidence_paths":["proof","absent"]},
            "a":{"evidence_paths":["proof","z"]},"c":{}});
        if mode == "list_settings_error" {
            surfaces["a"]["evidence_paths"]
                .as_array_mut()
                .unwrap()
                .push(json!(".claude/settings.json"));
        }
        outcome(m::evidence_digests(root, &surfaces, &mut host))
    } else {
        outcome(m::evidence_digest(
            if ["plain", "missing"].contains(&mode) {
                "proof"
            } else {
                ".claude/settings.json"
            },
            &path,
            &mut host,
        ))
    };
    json!({"value":[result,host.calls]})
}
fn atomic_case(root: &Path, mode: &str) -> Value {
    let path = root.join("nested/receipt.json");
    if mode != "new" {
        put(root, "nested/receipt.json", "previous");
    }
    let mut host = Observer::new(root, mode);
    let result = outcome(m::atomic_write_json(
        &path,
        &json!({"z":"\u{e9}","a":[1]}),
        &mut host,
    ));
    let bytes = fs::read(&path)
        .ok()
        .map(|b| b.iter().map(|b| format!("{b:02x}")).collect::<String>());
    let mut names: Vec<_> = fs::read_dir(path.parent().unwrap())
        .unwrap()
        .map(|e| e.unwrap().file_name().into_string().unwrap())
        .collect();
    names.sort();
    json!({"value":[result,bytes,names]})
}
fn main_case(root: &Path, mode: &str, apply: bool, as_json: bool) -> Value {
    let mut host = Observer::new(root, mode);
    let mut surface_text = Vec::new();
    for key in m::SURFACE_KEYS {
        let deferred = ["exceptions", "not_applicable", "content_workspace"].contains(&mode)
            && ["content_onboarding", "memory_acceptance", "phase2_spec"].contains(&key);
        let disposition = if mode == "repository_owned" {
            "repository_owned"
        } else if deferred && key == "content_onboarding" && mode != "exceptions" {
            "not_applicable"
        } else if deferred {
            "exception"
        } else {
            "applied"
        };
        let mut surface = json!({"disposition":disposition, "evidence_paths":["proof"]});
        if deferred {
            surface["reason"] = json!("Deferred");
        }
        host.surfaces[key] = surface;
        surface_text.push(format!(
            "{}: {{\"disposition\": {}, \"evidence_paths\": [\"proof\"]{}}}",
            py_json(&json!(key)),
            py_json(&json!(disposition)),
            if deferred {
                ", \"reason\": \"Deferred\""
            } else {
                ""
            }
        ));
    }
    let profile = if mode == "content_workspace" {
        "content_workspace"
    } else {
        "code_app"
    };
    let manifest = format!(
        "{{\"schema_version\": {}, \"project_slug\": \"sample\", \
        \"repository_archetype\": \"code_app\", \"profile\": \"{profile}\", \
        \"mir_yoke_source_commit\": \"{}\", \"surfaces\": {{{}}}{}}}",
        if mode == "manifest_fields" { 2 } else { 1 },
        if mode == "manifest_fields" {
            "BAD".into()
        } else {
            "a".repeat(40)
        },
        surface_text.join(", "),
        if mode == "manifest_fields" {
            ", \"extra\": 1"
        } else {
            ""
        }
    );
    if mode != "missing" {
        put(
            root,
            "config/bootstrap-adoption.json",
            match mode {
                "invalid" => "{",
                "array" => "[]",
                _ => &manifest,
            },
        );
    }
    put(root, "proof", "Verified");
    let mut args = vec!["--project-root".into(), root.to_str().unwrap().into()];
    if apply {
        args.push("--apply".into());
    }
    if as_json {
        args.push("--json".into());
    }
    match mode {
        "help" => args = vec!["--help".into()],
        "bad_arg" => args = vec!["--bad".into()],
        "missing_arg" => args = vec!["--project-root".into()],
        "native_arg" => args.extend([
            "--native-evaluator".into(),
            root.join("local-evaluator").to_str().unwrap().into(),
        ]),
        _ => (),
    }
    host.argv = [vec!["mir".into()], args.clone()].concat();
    let refs: Vec<_> = args.iter().map(String::as_str).collect();
    let result = outcome(m::main(
        if mode == "argv_none" {
            None
        } else {
            Some(&refs)
        },
        &root.join("source"),
        &root.join("package"),
        &mut host,
    ));
    let mut receipts = json!({});
    let receipt = root.join(".mir/bootstrap-receipt.json");
    if receipt.exists() {
        // Python Path.read_text uses universal newlines. Raw bytes are separately
        // asserted in windows_p3_calls_and_file_effects, including every CR.
        receipts[".mir/bootstrap-receipt.json"] = json!(
            fs::read_to_string(receipt)
                .unwrap()
                .replace("\r\n", "\n")
                .replace('\r', "\n")
        );
    }
    json!({"value":{"result":result, "stdout":host.stdout, "stderr":host.stderr,
        "calls":host.calls, "installs":host.installs, "receipts":receipts}})
}
fn unhex(text: &str) -> Vec<u8> {
    text.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|b| u8::from_str_radix(std::str::from_utf8(b).unwrap(), 16).unwrap())
        .collect()
}
#[test]
fn windows_p3_calls_and_file_effects() {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/w2/unify2-s4.json")).unwrap();
    for (mode, expected) in fixture["records"].as_object().unwrap() {
        let tmp = tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap();
        let root = handoff_packet::supply::plain(tmp.path().to_path_buf());
        let actual = raw_observation(main_case(&root, mode, true, true), &root);
        assert_eq!(
            actual["value"], expected["value"],
            "{mode}: full observation"
        );
        let mut files: Vec<_> = handoff_packet::mir_cli::changes::snapshot_project(&root)
            .unwrap()
            .into_keys()
            .collect();
        files.sort();
        let mut expected_files: Vec<_> = expected["files"]
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect();
        expected_files.sort();
        assert_eq!(files, expected_files, "{mode}: complete file set");
        for (name, bytes) in expected["files"].as_object().unwrap() {
            let mut bytes = unhex(bytes.as_str().unwrap());
            if !cfg!(windows) && name == ".mir/bootstrap-receipt.json" {
                // Derived Unix Path.write_text representation; Windows stays byte-exact.
                bytes = String::from_utf8(bytes)
                    .unwrap()
                    .replace("\r\n", "\n")
                    .into_bytes();
            }
            assert_eq!(fs::read(root.join(name)).unwrap(), bytes, "{mode}: {name}");
        }
    }
}
#[test]
fn every_frozen_record_replays_exactly() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-adoption-main.json")).unwrap();
    assert_eq!(records.as_object().unwrap().len(), 72);
    let mut replayed = 0;
    for (name, expected) in records.as_object().unwrap() {
        let tmp = tempfile::Builder::new()
            .prefix("b30-main-")
            .tempdir_in(std::env::temp_dir().canonicalize().unwrap())
            .unwrap();
        assert!(
            tmp.path()
                .starts_with(std::env::temp_dir().canonicalize().unwrap())
        );
        // Match Python-compatible runtime paths before Observer containment checks.
        let root = handoff_packet::supply::plain(tmp.path().to_path_buf());
        let root = root.as_path();
        let actual = if let Some(mode) = name.strip_prefix("digest.") {
            digest_case(root, mode)
        } else if let Some(mode) = name.strip_prefix("atomic.") {
            atomic_case(root, mode)
        } else if name.starts_with("emit.") {
            let mut host = Observer::new(root, "emit");
            m::emit(
                name.contains("json_True"),
                &json!({"status":"not_ready", "errors":["one","two"],
                "receipt_written":name.contains("written_True"),"extra":"\u{e9}"}),
                &mut host,
            )
            .unwrap();
            json!({"value":host.stdout})
        } else {
            let case = name.strip_prefix("main.scripted_validators.").unwrap();
            let (mode, apply, as_json) = if case.ends_with(".text") {
                (
                    if case.starts_with("pass") {
                        "pass"
                    } else {
                        "_validate_profile"
                    },
                    true,
                    false,
                )
            } else {
                let (mode, apply) = case.split_once(".apply_").unwrap();
                (mode, apply == "True", true)
            };
            main_case(root, mode, apply, as_json)
        };
        let actual = observe(actual, root);
        let mut expected = expected.clone();
        if cfg!(windows) && matches!(name.as_str(), "atomic.new" | "atomic.overwrite") {
            // Pinned _atomic_write_json uses Path.write_text(newline=None).
            let body = String::from_utf8(unhex(expected["value"][1].as_str().unwrap())).unwrap();
            expected["value"][1] = json!(
                body.replace('\n', "\r\n")
                    .as_bytes()
                    .iter()
                    .map(|b| format!("{b:02x}"))
                    .collect::<String>()
            );
        }
        assert_eq!(actual, expected, "record {name}");
        replayed += 1;
        eprintln!("REPLAY {name}");
    }
    assert_eq!(replayed, 72);
    eprintln!("B30 main: replayed={replayed}, exempt=0, total=72");
}
