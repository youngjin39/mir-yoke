//! Original E17 bootstrap/provider records; private adapters match pinned provider seams.
use super::{executable, reaped, setup};
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
    os::unix::fs::PermissionsExt,
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
            "discovery" | "provider-finalize" => {
                let manager = host
                    .inner
                    .import_capabilities(&host.cli, &root, Output::Activate)
                    .unwrap();
                manager.initialize(&root, None, None).unwrap();
                manager
                    .call(
                        if r["mode"] == "discovery" {
                            "check"
                        } else {
                            "finalize"
                        },
                        vec![],
                        Default::default(),
                    )
                    .map(|v| b::scalar_evidence(&v).unwrap())
            }
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
    for r in records.into_iter().filter(|r| r["mode"] == mode) {
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
        let source = if matches!(mode, "discovery" | "provider-finalize") {
            format!(
                r#"
import types
Path('pid').rename(Path.cwd().parent / 'pid')
r = json.loads({record})
class ReplayManager(CapabilityManager):
 def __init__(self, project_root, **kw):
  assert project_root == Path.cwd() and kw == {{}}
  Path('../trace').write_text('initialize\n')
  self.project_root = project_root
  self.active_receipt_path = project_root / 'receipt.json'
  self.config = types.SimpleNamespace(required_runtimes=('claude-code',),
   plugin_skills={{'mir-core': ('design',)}}, plugin_hooks={{}}, plugin_mcp={{}})
  self._assert_capability_home_safe = lambda **kw: None
  if r['mode'] == 'provider-finalize':
   self._assert_project_lock_path_safe = lambda: None
   self._load_lock = lambda: None if r['case'] == 'missing' else r['lock']
   self._active_integrity = lambda *a: r['case'] != 'integrity'
   self._activation_evidence = lambda *a, **kw: {{'status': 'missing' if r['case'] == 'activation' else 'verified'}}
   self._discovery_evidence = lambda *a: {{'status': 'missing' if r['case'] == 'discovery' else 'verified'}}
 def check(self):
  with Path('../trace').open('a') as f: f.write('discovery\n')
  return self._discovery_evidence(r['lock'], consumer_key='consumer')
 def finalize(self):
  with Path('../trace').open('a') as f: f.write('provider-finalize\n')
  return self._finalize(apply=r['case'] != 'read-only', after_restart=r['case'] != 'restart')
CapabilityManager = ReplayManager
"#,
                record = json!(r.to_string())
            )
        } else {
            source
        };
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
        let invoked = matches!(mode, "discovery" | "provider-finalize")
            || !r["calls"].as_array().unwrap().is_empty();
        assert_eq!(infra.join("pid").exists(), invoked);
        if invoked {
            reaped(&infra);
            assert_eq!(
                fs::read_to_string(infra.join("trace")).unwrap(),
                format!(
                    "initialize\n{}\n",
                    match mode {
                        "activate" => "sync",
                        "finalize" => "finalize",
                        other => other,
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
#[test]
fn discovery() {
    replay("discovery", 6);
}
#[test]
fn provider_finalize() {
    replay("provider-finalize", 7);
}

#[test]
fn installed_bootstrap_entry() {
    let source = r#"
Path('pid').rename(Path.cwd().parent / 'pid')
class CapabilityManager:
 def __init__(self, project_root, **kw):
  assert project_root == Path.cwd() and kw == {}
  Path('../trace').write_text('initialize\n')
 def sync(self, profile, **kw):
  assert profile == 'code_app' and kw == {'apply': True}
  with Path('../trace').open('a') as f: f.write('sync\n')
  return {}
"#;
    let (_tmp, infra) = setup(source);
    let root = infra.join("project");
    for relative in [
        "CLAUDE.md",
        "AGENTS.md",
        ".codex/config.toml",
        ".ai-harness/deny-list.yaml",
        ".claude/agents/main-orchestrator.md",
        ".codex/agents/main-orchestrator.toml",
        ".claude/hooks/test.sh",
    ] {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, "").unwrap();
    }
    let records: Vec<Value> = serde_json::from_str(include_str!("../fixtures/y-e17.json")).unwrap();
    for (relative, body) in [
        (".claude/settings.json", "{\"hooks\":{\"Test\":[]}}"),
        (".codex/hooks.json", "{}"),
        ("config/sub-agent-policy.json", "{}"),
        ("config/adopter-boundary.json", "{}"),
        ("config/adopter-payload.json", "{}"),
        (
            "config/capability-sources.json",
            records[13]["config"].as_str().unwrap(),
        ),
    ] {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, body).unwrap();
    }
    fs::write(
        root.join("harness_a.toml"),
        b::memory_config_text("entry", "code_app", None)
            .unwrap()
            .replace(".mir/memory.db", ".mir/synthetic-memory.sqlite"),
    )
    .unwrap();
    // Only these fake tools are reachable; neither mir nor python is on PATH.
    let tools = infra.join("tools");
    fs::create_dir(&tools).unwrap();
    for name in ["git", "jq"] {
        let path = tools.join(name);
        executable::write(&path, "#!/bin/sh\nexit 1\n").unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
    }
    let out = Command::new(infra.join("mir"))
        .args([
            "bootstrap",
            "--project-root",
            ".",
            "--profile",
            "code_app",
            "--slug",
            "entry",
            "--purpose",
            "Synthetic entry proof",
            "--stack",
            "Rust",
            "--json",
        ])
        .env_clear()
        .env("HOME", &infra)
        .env("PATH", &tools)
        .env("VIRTUAL_ENV", &infra)
        .current_dir(&root)
        .output()
        .unwrap();
    assert_eq!(
        fs::read_to_string(infra.join("trace")).ok().as_deref(),
        Some("initialize\nsync\n"),
        "{out:?}"
    );
    assert_eq!(out.status.code(), Some(1));
    assert!(out.stderr.is_empty(), "{out:?}");
    let receipt: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(
        receipt["capabilities"],
        json!({"status":"failed",
        "reason":"capability sync did not write .mir/capability-lock.json"})
    );
    let value = handoff_packet::python_json::Value::from(&receipt);
    assert_eq!(out.stdout, (value.json_sorted(false) + "\n").as_bytes());
    assert_eq!(
        fs::read(root.join(".mir/bootstrap-receipt.json")).unwrap(),
        (value.json_sorted(true) + "\n").as_bytes()
    );
    assert!(!root.join(".mir/memory.db").exists());
    reaped(&infra);
}
