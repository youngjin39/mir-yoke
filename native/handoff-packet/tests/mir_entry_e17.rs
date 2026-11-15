//! Y-E17A: acquisition replay. Real provider/session binding remains OPEN in split.md.
use handoff_packet::mir_cli::{bootstrap as b, capability};
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
    ) -> Result<Value, b::Error> {
        assert_eq!(args, vec![json!("code_app")]);
        if method == "sync" {
            assert_eq!(kwargs, json!({"apply": true}).as_object().unwrap().clone());
        } else {
            assert_eq!(method, "status");
            assert!(kwargs.is_empty());
        }
        if self.case == "console-error" {
            return Err(b::Error::new("CapabilityError", "provider refused"));
        }
        if self.case == "console-change" {
            fs::write(self.root.join(".mir/capability-lock.json"), "{}").unwrap();
        }
        Ok(json!({"ready": true}))
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
        Ok(b::CapabilityOutput {
            code: self.record["code"].as_i64().unwrap_or(0) as i32,
            stdout: self.record["out"].as_str().unwrap_or("").into(),
            stderr: self.record["err"].as_str().unwrap_or("").into(),
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
            "activate" => b::activate_capabilities(&root, "code_app", &mut host).map(|v| json!(v)),
            "finalize" => {
                let value =
                    b::finalize_capabilities(&root, r.get("prior"), &mut host).map(|v| json!(v));
                if !host.calls.is_empty() {
                    stderr = r["err"].as_str().unwrap_or("").into();
                }
                value
            }
            "lock" => b::capability_lock_evidence(&root, &mut host).map(|v| json!(v)),
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
                stdout = output.stdout;
                stderr = output.stderr;
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
