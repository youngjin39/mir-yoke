//! Original E17 records 0..16; private CLI adapter only for arbitrary stub exit codes.
use super::{reaped, setup};
use handoff_packet::mir_cli::{
    bootstrap::{self as b, Host},
    capability::Manager,
    capability_manager::Output,
};
use handoff_packet::python_json::Text;
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
    process::Command,
};

struct ReplayHost {
    inner: b::ProductionHost,
    cli: PathBuf,
    calls: Vec<Value>,
    cli_stub: bool,
    finalize: bool,
}
impl Host for ReplayHost {
    fn env(&mut self, name: &str) -> Option<String> {
        self.inner.env(name)
    }
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, b::Error> {
        self.inner.resolve(path)
    }
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, b::Error> {
        self.inner.expanduser(path)
    }
    fn is_dir(&mut self, path: &Path) -> bool {
        self.inner.is_dir(path)
    }
    fn writable(&mut self, path: &Path) -> bool {
        self.inner.writable(path)
    }
    fn device(&mut self, path: &Path) -> Result<u64, b::Error> {
        self.inner.device(path)
    }
    fn capability_import_for(&mut self, root: &Path, finalize: bool) -> Result<(), b::Error> {
        self.finalize = finalize;
        self.inner
            .import_capabilities(
                &self.cli,
                root,
                if finalize {
                    Output::Finalize
                } else {
                    Output::Activate
                },
            )
            .map(|_| ())
    }
    fn capability_main(&mut self, argv: &[String]) -> Result<b::CapabilityOutput, b::Error> {
        self.calls.push(json!(argv));
        if !self.cli_stub {
            return self.inner.capability_main(argv);
        }
        // The four original fake_cli records return arbitrary code 7, outside the real CLI's
        // return contract. Adapt only that seam; import, RPC, capture and cleanup stay real.
        let root = std::env::current_dir().unwrap();
        let manager = self.inner.import_capabilities(
            &self.cli,
            &root,
            if self.finalize {
                Output::Finalize
            } else {
                Output::Activate
            },
        )?;
        manager.initialize(&root, None, None)?;
        let code = manager.call(&argv[0], vec![json!(argv)], Default::default())?;
        Ok(b::CapabilityOutput {
            code: b::scalar_evidence(&code)?.as_i64().unwrap() as i32,
            stdout: Text::from_wtf8(&manager.captured).unwrap(),
            stderr: "".into(),
        })
    }
}

fn snapshot(root: &Path, base: &Path) -> Value {
    let mut files = serde_json::Map::new();
    for entry in fs::read_dir(root).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            files.extend(snapshot(&path, base).as_object().unwrap().clone());
        } else {
            files.insert(
                path.strip_prefix(base).unwrap().to_str().unwrap().into(),
                json!(fs::read(path).unwrap()),
            );
        }
    }
    Value::Object(files)
}

#[test]
fn child() {
    let Ok(record) = std::env::var("Y_E17_ORIGINAL") else {
        return;
    };
    let r: Value = serde_json::from_str(&record).unwrap();
    let root = std::env::current_dir().unwrap();
    let infra = root.parent().unwrap();
    let stdout = fs::File::create(infra.join("stdout.bin")).unwrap();
    let stderr = fs::File::create(infra.join("stderr.bin")).unwrap();
    std::io::stdout().flush().unwrap();
    std::io::stderr().flush().unwrap();
    // Capture route bytes without libtest's banner or completion text.
    unsafe {
        assert_eq!(libc::dup2(stdout.as_raw_fd(), 1), 1);
        assert_eq!(libc::dup2(stderr.as_raw_fd(), 2), 2);
    }
    {
        let mut host = ReplayHost {
            inner: b::ProductionHost::default(),
            cli: infra.join("mir"),
            calls: vec![],
            cli_stub: r.get("code").is_some(),
            finalize: false,
        };
        let result = match r["mode"].as_str().unwrap() {
            "activate" => b::activate_capabilities(&root, "code_app", &mut host)
                .map(|(s, v)| json!([s, b::scalar_evidence(&v).unwrap()])),
            "finalize" => b::finalize_capabilities(&root, r.get("prior"), &mut host)
                .map(|(s, v)| json!([s, b::scalar_evidence(&v).unwrap()])),
            "lock" => b::capability_lock_evidence(&root, &mut host.inner)
                .map(|(s, v)| json!([s, b::scalar_evidence(&v).unwrap()])),
            "config" => host
                .inner
                .capability_config_plugins(&root.join("config/capability-sources.json"))
                .map(|plugins| {
                    let mut keys: Vec<_> = plugins.as_object().unwrap().keys().collect();
                    keys.sort();
                    json!(keys)
                }),
            _ => unreachable!(),
        };
        let result = match result {
            Ok(v) => json!({"value":v}),
            Err(e) => json!({"class":e.class,"message":e.message}),
        };
        fs::write(infra.join("result.json"), result.to_string()).unwrap();
        fs::write(infra.join("calls.json"), json!(host.calls).to_string()).unwrap();
    }
    std::io::stdout().flush().unwrap();
    std::io::stderr().flush().unwrap();
    std::process::exit(0);
}

fn replay(mode: &str, count: usize) {
    let records: Vec<Value> = serde_json::from_str(include_str!("../fixtures/y-e17.json")).unwrap();
    let mut checked = 0;
    for r in records.into_iter().take(16).filter(|r| r["mode"] == mode) {
        let source = format!(
            r#"
Path('pid').rename(Path.cwd().parent / 'pid')
r = json.loads({record})
class CapabilityManager:
 def __init__(self, project_root, **kw):
  assert project_root == Path.cwd() and kw == {{}}
  Path('../trace').write_text('initialize\n')
 def run(self, method, args, kw):
  with Path('../trace').open('a') as f: f.write(method+'\n')
  assert method == ('sync' if r['mode'] == 'activate' else 'finalize')
  if 'code' in r:
   assert list(args) == [[v.replace('{{ROOT}}',str(Path.cwd())) for v in r['calls'][0]]] and kw == {{}}
   print(r.get('out',''),end='')
   print(r.get('err',''),end='',file=sys.stderr)
   return r['code']
  assert args == (('code_app',) if method == 'sync' else ())
  assert kw == ({{'apply':True}} if method == 'sync' else {{'apply':True,'after_restart':True}})
  return {{}}
 def sync(self,*a,**kw): return self.run('sync',a,kw)
 def finalize(self,*a,**kw): return self.run('finalize',a,kw)
"#,
            record = json!(r.to_string())
        );
        let (_tmp, infra) = setup(&format!("import json, sys\n{source}"));
        let root = infra.join("project");
        fs::create_dir_all(root.join(".mir")).unwrap();
        for (name, body) in r["files"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, body.as_str().unwrap()).unwrap();
        }
        let expected_files: serde_json::Map<String, Value> = r["files"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(name, body)| (name.clone(), json!(body.as_str().unwrap().as_bytes())))
            .collect();
        let out = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "original_bootstrap_replays::child",
                "--nocapture",
                "--quiet",
            ])
            .env_clear()
            .env("HOME", &root)
            .env("PATH", &infra)
            .env("Y_E17_ORIGINAL", r.to_string())
            .current_dir(&root)
            .output()
            .unwrap();
        assert_eq!(out.status.code(), Some(0), "{mode}/{}: {out:?}", r["case"]);
        assert_eq!(out.stdout, b"\nrunning 1 test\n");
        assert!(out.stderr.is_empty(), "{out:?}");
        let actual: Value =
            serde_json::from_slice(&fs::read(infra.join("result.json")).unwrap()).unwrap();
        assert_eq!(actual, r["result"], "{mode}/{}", r["case"]);
        for (file, field) in [("stdout.bin", "stdout"), ("stderr.bin", "stderr")] {
            assert_eq!(
                fs::read(infra.join(file)).unwrap(),
                r[field].as_str().unwrap().as_bytes(),
                "{mode}/{} {field}",
                r["case"]
            );
        }
        let calls = fs::read_to_string(infra.join("calls.json"))
            .unwrap()
            .replace(root.to_str().unwrap(), "{ROOT}");
        assert_eq!(serde_json::from_str::<Value>(&calls).unwrap(), r["calls"]);
        assert_eq!(
            snapshot(&root, &root),
            Value::Object(expected_files),
            "{mode}/{} files",
            r["case"]
        );
        let invoked = !r["calls"].as_array().unwrap().is_empty();
        assert_eq!(infra.join("pid").exists(), invoked);
        if invoked {
            reaped(&infra);
            assert_eq!(
                fs::read_to_string(infra.join("trace")).unwrap(),
                format!(
                    "initialize\n{}\n",
                    if mode == "activate" {
                        "sync"
                    } else {
                        "finalize"
                    }
                )
            );
        }
        checked += 1;
    }
    assert_eq!(checked, count);
}
#[test]
fn activate() {
    replay("activate", 4);
}
#[test]
fn finalize() {
    replay("finalize", 5);
}
#[test]
fn lock() {
    replay("lock", 5);
}
#[test]
fn config() {
    replay("config", 2);
}
