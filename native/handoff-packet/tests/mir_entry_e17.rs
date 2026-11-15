//! Y-E17A: acquisition replay. Real provider/session binding remains OPEN in split.md.
use handoff_packet::mir_cli::{bootstrap as b, capability};
use handoff_packet::python_json::{self as py, Text};
use serde_json::{Map, Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
};

struct Provider {
    root: PathBuf,
    case: String,
}
impl capability::Manager for Provider {
    fn initialize(
        &mut self,
        root: &Path,
        config: Option<&Path>,
        home: Option<&Path>,
    ) -> Result<(), b::Error> {
        assert_eq!(root, self.root);
        assert!(config.is_none() && home.is_none());
        Ok(())
    }
    fn call(
        &mut self,
        method: &str,
        args: Vec<Value>,
        kwargs: Map<String, Value>,
    ) -> Result<py::Value, b::Error> {
        assert_eq!(args, vec![json!("code_app")]);
        if method == "sync" {
            assert_eq!(kwargs, json!({"apply": true}).as_object().unwrap().clone());
        } else {
            assert_eq!(method, "status");
            assert!(kwargs.is_empty());
        }
        if self.case.starts_with("console-error") {
            return Err(b::Error::new(
                "CapabilityError",
                if self.case == "console-error-cr" {
                    "provider\r\nrefused\r"
                } else {
                    "provider refused"
                },
            ));
        }
        if self.case == "console-change" {
            fs::write(self.root.join(".mir/capability-lock.json"), "{}").unwrap();
        }
        Ok(py::Value::from(&json!({"ready": true})))
    }
}
struct Host {
    record: Value,
    calls: Vec<Value>,
}
impl b::Host for Host {
    fn env(&mut self, _: &str) -> Option<String> {
        panic!("unexpected environment access")
    }
    fn resolve(&mut self, _: &Path) -> Result<PathBuf, b::Error> {
        panic!("unexpected path access")
    }
    fn expanduser(&mut self, _: &Path) -> Result<PathBuf, b::Error> {
        panic!("unexpected home access")
    }
    fn is_dir(&mut self, _: &Path) -> bool {
        panic!("unexpected path access")
    }
    fn writable(&mut self, _: &Path) -> bool {
        panic!("unexpected path access")
    }
    fn device(&mut self, _: &Path) -> Result<u64, b::Error> {
        panic!("unexpected device access")
    }
    fn run(&mut self, _: &b::CommandRequest) -> Result<b::CommandOutput, b::Error> {
        panic!("unexpected process execution")
    }
    fn capability_main(&mut self, argv: &[String]) -> Result<b::CapabilityOutput, b::Error> {
        self.calls.push(json!(argv));
        let text = |key: &str| {
            let bytes =
                serde_json::from_value::<Vec<u8>>(self.record[format!("{key}_bytes")].clone())
                    .unwrap_or_else(|_| {
                        self.record[key].as_str().unwrap_or("").as_bytes().to_vec()
                    });
            Text::from_wtf8(&bytes).unwrap()
        };
        Ok(b::CapabilityOutput {
            code: self.record["code"].as_i64().unwrap_or(0) as i32,
            stdout: text("out"),
            stderr: text("err"),
        })
    }
}
#[test]
fn frozen_capability_acquisition() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e17.json")).unwrap();
    let scratch = Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/Y-E17");
    fs::create_dir_all(&scratch).unwrap();
    let mut checked = 0;
    for r in records
        .iter()
        .filter(|r| r["mode"] != "discovery" && r["mode"] != "provider-finalize")
    {
        let temp = tempfile::tempdir_in(&scratch).unwrap();
        let root = temp.path().canonicalize().unwrap();
        for (name, body) in r["files"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, body.as_str().unwrap()).unwrap();
        }
        fs::create_dir_all(root.join(".mir")).unwrap();
        let mut host = Host {
            record: r.clone(),
            calls: vec![],
        };
        let mut stdout = String::new();
        let mut stderr = String::new();
        let result: Result<Value, b::Error> = match r["mode"].as_str().unwrap() {
            "activate" => b::activate_capabilities(&root, "code_app", &mut host)
                .map(|v| json!([v.0, b::scalar_evidence(&v.1).unwrap()])),
            "finalize" => {
                let value = b::finalize_capabilities(&root, r.get("prior"), &mut host)
                    .map(|v| json!([v.0, b::scalar_evidence(&v.1).unwrap()]));
                if !host.calls.is_empty() {
                    stderr = r["err"].as_str().unwrap_or("").into();
                }
                value
            }
            "lock" => b::capability_lock_evidence(&root, &mut host)
                .map(|v| json!([v.0, b::scalar_evidence(&v.1).unwrap()])),
            "config" => b::Host::capability_config_plugins(
                &mut b::ProductionHost::default(),
                &root.join("config/capability-sources.json"),
            )
            .map(|v| {
                let mut keys: Vec<_> = v.as_object().unwrap().keys().cloned().collect();
                keys.sort();
                json!(keys)
            }),
            "console" => {
                let argv: Vec<_> = r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| {
                        if v == "." {
                            root.to_str().unwrap().to_owned()
                        } else {
                            v.as_str().unwrap().to_owned()
                        }
                    })
                    .collect();
                let mut provider = Provider {
                    root: root.clone(),
                    case: r["case"].as_str().unwrap().into(),
                };
                let output = b::CapabilityOutput::run(&argv, &mut provider).unwrap();
                stdout = output.stdout.as_str().unwrap().into();
                stderr = output.stderr.as_str().unwrap().into();
                Ok(json!(output.code))
            }
            mode => panic!("unhandled {mode}"),
        };
        let value = match result {
            Ok(v) => json!({"value": v}),
            Err(e) => json!({"class": e.class, "message": e.message}),
        };
        let actual =
            json!({"result": value, "stdout": stdout, "stderr": stderr, "calls": host.calls});
        let actual: Value =
            serde_json::from_str(&actual.to_string().replace(root.to_str().unwrap(), "{ROOT}"))
                .unwrap();
        for field in ["result", "stdout", "stderr", "calls"] {
            // Python sorts CLI output keys, so byte comparison (not parsed JSON) is intentional.
            assert_eq!(
                actual[field], r[field],
                "{}: {} {field}",
                r["mode"], r["case"]
            );
        }
        assert!(!root.join(".mir/memory.db").exists());
        checked += 1;
    }
    assert_eq!(checked, 20);
}

fn replay(mode: &str) {
    let records = py::parse(include_str!("fixtures/y-e17b2b1b2a.json")).unwrap();
    for r in records
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["mode"].as_str() == Some(mode))
    {
        let temp = tempfile::tempdir().unwrap();
        fs::create_dir(temp.path().join(".mir")).unwrap();
        if let Some(body) = r["files"].get(".mir/capability-lock.json") {
            let path = temp.path().join(".mir/capability-lock.json");
            fs::write(path, body.as_str().unwrap()).unwrap();
        }
        let bytes = |key| {
            r[key]
                .as_text()
                .map(|s| s.render().unwrap())
                .unwrap_or_default()
        };
        let mut host = Host {
            record: json!({"code":if r.get("code").is_some() {7} else {0},
            "out_bytes":bytes("out"), "err_bytes":bytes("err")}),
            calls: vec![],
        };
        let prior = serde_json::json!({"status":"restart_required"});
        let (status, evidence) = match mode {
            "activate" => b::activate_capabilities(temp.path(), "code_app", &mut host),
            "finalize" => b::finalize_capabilities(temp.path(), Some(&prior), &mut host),
            _ => b::capability_lock_evidence(temp.path(), &mut host),
        }
        .unwrap();
        let expected = r["result"]["value"].as_array().unwrap();
        assert_eq!(Some(status.as_str()), expected[0].as_str());
        assert_eq!(evidence.json_sorted(false), expected[1].json_sorted(false));
        if r["case"].as_str() == Some("surrogate-pair") {
            assert_eq!(
                evidence["reason"].as_text().unwrap().codepoints,
                [0xd800, 0xdc00]
            );
        }
        assert_eq!(
            b::scalar_evidence(&evidence).is_err(),
            r["case"].as_str() != Some("missing-plugins")
        );
    }
}
#[test]
fn activate() {
    replay("activate");
}
#[test]
fn finalize() {
    replay("finalize");
}
#[test]
fn lock() {
    replay("lock");
}

#[test]
fn output_admission() {
    let records = py::parse(include_str!("fixtures/y-e17b2b1b2a.json")).unwrap();
    let r = b::scalar_evidence(
        records
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["mode"].as_str() == Some("console"))
            .unwrap(),
    )
    .unwrap();
    let temp = tempfile::tempdir().unwrap();
    let mut provider = Provider {
        root: temp.path().canonicalize().unwrap(),
        case: "console-error-cr".into(),
    };
    let argv = vec![
        "sync".into(),
        "--profile".into(),
        "code_app".into(),
        "--project-root".into(),
        provider.root.display().to_string(),
        "--json".into(),
        "--apply".into(),
    ];
    let out = b::CapabilityOutput::run(&argv, &mut provider).unwrap();
    assert_eq!(out.code, r["result"]["value"].as_i64().unwrap() as i32);
    assert_eq!(
        out.stdout.render().unwrap(),
        r["stdout"].as_str().unwrap().as_bytes()
    );
    assert_eq!(
        out.stderr.render().unwrap(),
        r["stderr"].as_str().unwrap().as_bytes()
    );
}

#[test]
fn scalar_surrogate_recursion() {
    // Raw Python code points, not JSON escapes which would combine the pair.
    for text in [
        "\"PAIR\"",
        "[\"PAIR\"]",
        "{\"nested\":[{\"PAIR\":0}]}",
        "{\"nested\":[{\"key\":\"PAIR\"}]}",
    ] {
        let (before, after) = text.split_once("PAIR").unwrap();
        let points = before
            .chars()
            .map(u32::from)
            .chain([0xd800, 0xdc00])
            .chain(after.chars().map(u32::from))
            .collect();
        let value = py::parse_codepoints(points).unwrap();
        let err = b::scalar_evidence(&value).unwrap_err();
        assert_eq!(err.class, "ValueError");
        assert!(err.message.starts_with("scalar-only bootstrap boundary:"));
        let scalar = py::parse(&text.replace("PAIR", "\u{10000}")).unwrap();
        assert!(b::scalar_evidence(&scalar).is_ok());
    }
}

#[test]
fn lock_decode_failure() {
    let temp = tempfile::tempdir().unwrap();
    fs::create_dir(temp.path().join(".mir")).unwrap();
    fs::write(temp.path().join(".mir/capability-lock.json"), [0xff]).unwrap();
    let mut host = Host {
        record: json!({}),
        calls: vec![],
    };
    let err = b::capability_lock_evidence(temp.path(), &mut host).unwrap_err();
    assert_eq!(err.class, "UnicodeDecodeError");
    assert!(host.calls.is_empty());
}
