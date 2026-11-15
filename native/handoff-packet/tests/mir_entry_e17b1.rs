#![cfg(unix)]
use handoff_packet::mir_cli::{capability::Manager, capability_manager::*};
use serde_json::{Value, json};
use std::{
    fs,
    os::unix::ffi::OsStrExt,
    os::unix::fs::{PermissionsExt, symlink},
    path::{Path, PathBuf},
};
fn setup(source: Option<&str>) -> (tempfile::TempDir, PathBuf, PathBuf) {
    let scratch = std::env::temp_dir();
    fs::create_dir_all(&scratch).unwrap();
    let temp = tempfile::tempdir_in(scratch).unwrap();
    let root = temp.path().canonicalize().unwrap();
    let python = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.venv/bin/python");
    for dir in ["project", "outside"] {
        fs::create_dir_all(root.join(dir)).unwrap();
    }
    let cli = root.join("mir-cli");
    let bridge = include_str!("../../../src/mir/cli/capability_manager_bridge.py");
    let bootstrap = format!(
        r#"import os,sys,runpy,json,pathlib,shutil
root = pathlib.Path({})
source = json.loads({})
if source is None:
 shutil.copytree({}, root/'mir')
else:
 for p in ('mir','mir/cli','mir/core','mir/core/capabilities'):
  (root/p).mkdir(parents=True,exist_ok=True); (root/p/'__init__.py').write_text('')
 (root/'mir/core/capabilities/manager.py').write_text(source)
(root/'mir/cli/capability_manager_bridge.py').write_text({})
sys.path.insert(0,str(root))
assert sys.argv[1:7]==['run-python','--project-root',str(root),'--','-m','mir.cli.capability_manager_bridge']
sys.argv = ['bridge', *sys.argv[7:]]
runpy.run_module('mir.cli.capability_manager_bridge',run_name='__main__')
"#,
        json!(root),
        json!(json!(source).to_string()),
        json!(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../src/mir")),
        json!(bridge)
    );
    let shell = format!(
        "#!/bin/sh\nexec /usr/bin/env -i HOME='{}' '{}' -I -c '{}' \"$@\"\n",
        root.display(),
        python.display(),
        bootstrap.replace('\'', "'\\''")
    );
    fs::write(&cli, shell).unwrap();
    fs::set_permissions(&cli, fs::Permissions::from_mode(0o755)).unwrap();
    (temp, root, cli)
}

#[test]
fn held_output_fd_returns() {
    let (_temp, root, cli) = setup(Some(
        "import os,signal\nsignal.alarm(2)\nclass CapabilityManager:\n def __init__(self): self.held=os.dup(1)\n",
    ));
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    assert!(m.request(json!({"op":"initialize"})).is_ok());
}

#[test]
fn raw_then_python_output_order() {
    let (_temp, root, cli) = setup(Some(
        "import os\nos.write(1,b'raw-first'); print('python-second',end='')\nclass CapabilityManager: pass\n",
    ));
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    let r = m.request(json!({"op":"import"})).unwrap();
    assert_eq!(
        r.events,
        vec![Event::Stdout(b"raw-firstpython-second".to_vec())]
    );
}

#[test]
fn final_reply_does_not_wait_for_provider_thread() {
    let (_temp, root, cli) = setup(Some(
        "import threading,time,signal\nsignal.alarm(2)\nclass CapabilityManager:\n def __init__(self): threading.Thread(target=lambda: time.sleep(2)).start()\n",
    ));
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    m.request(json!({"op":"initialize"})).unwrap();
    let start = std::time::Instant::now();
    assert!(m.finish().is_ok() && start.elapsed().as_secs_f64() < 1.0);
}

#[test]
fn child_exit_and_partial_frames_do_not_wait_for_descendants() {
    for wire in [
        "",
        "{",
        r#"{"value":null,"error":null,"events":[]}"#,
        "{\"value\":null,\"error\":null,\"events\":[]}\n",
    ] {
        let (_temp, root, cli) = setup(Some(""));
        fs::write(&cli, format!("#!/bin/sh\nexport HOME='{}'\nread line\n/bin/sleep 2 &\necho $! > descendant\nprintf '%s' '{}'\n", root.display(), wire)).unwrap();
        let mut m = ProductionManager::start(&cli, &root).unwrap();
        let start = std::time::Instant::now();
        let result = m.request(json!({"op":"import"}));
        let finish = wire.ends_with('\n').then(|| m.finish());
        let elapsed = start.elapsed();
        let pid = fs::read_to_string(root.join("descendant")).unwrap();
        let _ = std::process::Command::new("/bin/kill").arg(pid).output();
        if let Some(finish) = finish {
            finish.unwrap();
        }
        let expected = match wire {
            "" => Some(Failure::Eof),
            s if s.ends_with('\n') => None,
            _ => Some(Failure::Malformed),
        };
        assert_eq!(result.err().map(|e| e.kind), expected);
        assert!(elapsed.as_secs_f64() < 1.0, "{wire:?}: {elapsed:?}");
    }
}

#[test]
fn manager_boundary() {
    let (_temp, root, cli) = setup(Some(
        "import sys,os\nprint('import',end='')\nclass CapabilityManager:\n def __init__(self,*a,**kw): self.token=73\n def _finalize(self): return 999\n def status(self,*a,**kw):\n  print('out',end=''); print('err',end='',file=sys.stderr)\n  os.write(1,b'r'*100000+b'\\xff'); os.write(2,b's'*100000)\n  return [self.token,a,kw,os.getpid()]\n",
    ));
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    let import = m.request(json!({"op":"import"})).unwrap();
    assert_eq!(import.events, vec![Event::Stdout(b"import".to_vec())]);
    let invalid = Path::new(std::ffi::OsStr::from_bytes(b"\xff"));
    assert_eq!(
        m.initialize(invalid, None, None).unwrap_err().class,
        "UnicodeEncodeError"
    );
    assert_eq!(
        m.initialize(&root, Some(invalid), None).unwrap_err().class,
        "UnicodeEncodeError"
    );
    m.initialize(&root.join("project"), None, None).unwrap();
    let reply = m
        .request(json!({"op":"call","method":"status","args":["p"],"kwargs":{"mcp":true}}))
        .unwrap();
    let expected = json!([73,["p"],{"mcp":true}]);
    assert_eq!(
        reply.value.as_array().unwrap()[..3],
        expected.as_array().unwrap()[..]
    );
    for (request, class) in [
        (json!({"op":"call","method":"_finalize"}), "ValueError"),
        (json!({"op":"initialize"}), "RuntimeError"),
        (json!({"op":"unknown"}), "ValueError"),
    ] {
        assert_eq!(m.request(request).unwrap().error.unwrap().class, class);
    }
    let (mut stdout, mut stderr) = (Vec::new(), Vec::new());
    for event in &reply.events {
        match event {
            Event::Stdout(b) => stdout.extend_from_slice(b),
            Event::Stderr(b) => stderr.extend_from_slice(b),
        }
    }
    let expected = [vec![b'r'; 100000].as_slice(), &[255], b"out"].concat();
    assert_eq!(stdout, expected);
    assert_eq!(stderr, [vec![b's'; 100000].as_slice(), b"err"].concat());
    let pid = reply.value[3].to_string();
    drop(m);
    let mut probe = std::process::Command::new("/bin/kill");
    let status = probe.args(["-0", &pid]).output().unwrap().status;
    assert!(!status.success());
    let (_temp, root, cli) = setup(Some("raise ImportError('missing provider')"));
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    let error = m.request(json!({"op":"import"})).unwrap().error.unwrap();
    assert_eq!(error.message, "missing provider");
    let fixture: Value = serde_json::from_str(include_str!("fixtures/y-e17b1.json")).unwrap();
    for record in fixture["records"].as_array().unwrap() {
        let (_temp, root, cli) = setup(None);
        let case = record["case"].as_str().unwrap();
        let config = fixture["config"].as_str().unwrap();
        let config = if case == "constructor" { "{}" } else { config };
        fs::write(root.join("config.json"), config).unwrap();
        let mut m = ProductionManager::start(&cli, &root).unwrap();
        let init = m.initialize(
            &root.join("project"),
            Some(&root.join("config.json")),
            Some(&root.join("cap")),
        );
        if case == "constructor" {
            assert!(init.is_err());
        } else {
            init.unwrap();
            if case == "identity" {
                fs::rename(root.join("project"), root.join("old")).unwrap();
                symlink(root.join("outside"), root.join("project")).unwrap();
            }
            let call = &record["call"];
            let args = serde_json::from_value(call["args"].clone()).unwrap();
            let kwargs = serde_json::from_value(call["kwargs"].clone()).unwrap();
            assert!(
                m.call(call["method"].as_str().unwrap(), args, kwargs)
                    .is_err()
            );
        }
        let root_text = root.to_str().unwrap();
        let mut reply = json!(m.last_reply);
        // Earlier records predate the additive exception ancestry field.
        reply["error"].as_object_mut().unwrap().remove("mro");
        let actual = reply.to_string().replace(root_text, "{ROOT}");
        assert_eq!(actual, record["reply"].to_string(), "{case}");
        assert_eq!(fs::read_dir(root.join("outside")).unwrap().count(), 0);
    }
    let (_temp, root, cli) = setup(Some(""));
    let error = ProductionManager::start(&root.join("absent"), &root)
        .err()
        .unwrap();
    assert_eq!(error.kind(), std::io::ErrorKind::NotFound);
    let faults = r#"[["read line\necho launcher >&2\nexit 23\n","eof"],["read line\nexit 0\n","eof"],["read line\necho garbage\n","malformed"],["read x\necho '{\"events\":[]}'\n","malformed"],["read line\nexec 1>&-\nwhile :; do :; done\n","eof"],["read x\necho '{\"value\":null,\"error\":null,\"events\":[]}'\nexit 23\n","child"]]"#;
    let faults: Vec<(String, Failure)> = serde_json::from_str(faults).unwrap();
    for (body, kind) in faults {
        fs::write(&cli, format!("#!/bin/sh\n{body}")).unwrap();
        let mut m = ProductionManager::start(&cli, &root).unwrap();
        let reply = m.request(json!({"op":"import"}));
        let e = if kind == Failure::Child {
            reply.unwrap();
            m.finish().unwrap_err()
        } else {
            reply.unwrap_err()
        };
        assert_eq!(e.kind, kind);
        let mut typed = ProductionManager::start(&cli, &root).unwrap();
        let error = typed
            .call("status", vec![], Default::default())
            .unwrap_err();
        assert_eq!(error.class, "RuntimeError");
        assert_eq!(error.message, e.message);
        if body.contains("launcher") {
            assert_eq!(e.stderr.unwrap().unwrap().unwrap(), b"launcher\n");
            assert_eq!(e.status.unwrap().code(), Some(23));
        }
    }
    fs::write(&cli, "#!/bin/sh\nread line\nexec 0<&-\necho '{\"value\":null,\"error\":null,\"events\":[]}'\nwhile :; do :; done\n").unwrap();
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    m.request(json!({"op":"import"})).unwrap();
    assert_eq!(
        m.request(json!("x".repeat(1000000))).unwrap_err().kind,
        Failure::Io
    );
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    m.import().unwrap();
    let error = m
        .call(
            "status",
            vec![json!("x".repeat(1000000))],
            Default::default(),
        )
        .unwrap_err();
    assert_eq!(error.class, "RuntimeError");
    assert!(error.message.contains("Broken pipe"));
    let mut host = handoff_packet::mir_cli::bootstrap::ProductionHost::default();
    assert_eq!(
        host.import_capabilities(&root.join("absent"), &root, Output::Console)
            .err()
            .unwrap()
            .class,
        "FileNotFoundError"
    );
    fs::write(&cli, "#!/bin/sh\nread x\necho '{\"value\":null,\"error\":{\"class\":\"OddProviderError\",\"message\":\"refused\"},\"events\":[]}'\nexit 23\n").unwrap();
    let mut m = ProductionManager::start(&cli, &root).unwrap();
    let error = m.call("status", vec![], Default::default()).unwrap_err();
    assert_eq!(
        (error.class.as_str(), error.message.as_str()),
        ("OddProviderError", "refused")
    );
}

#[test]
fn output_boundary_child() {
    use std::io::Write;
    let Ok(data) = std::env::var("Y_E17B2A_RECORD") else {
        return;
    };
    let r: Value = serde_json::from_str(&data).unwrap();
    let root = std::env::current_dir().unwrap();
    std::io::stdout().write_all(b"<boundary>").unwrap();
    std::io::stdout().flush().unwrap();
    std::io::stderr().write_all(b"<boundary>").unwrap();
    let mode = r["mode"].as_str().unwrap();
    let output = match if mode == "import" {
        r["case"].as_str().unwrap()
    } else {
        mode
    } {
        "activate" => Output::Activate,
        "finalize" => Output::Finalize,
        _ => Output::Console,
    };
    let mut m = ProductionManager::start_with_output(&root.join("mir-cli"), &root, output).unwrap();
    m.request(json!({"op":"import"})).unwrap();
    let mut start = std::time::Instant::now();
    let mut captured = Vec::new();
    if mode != "import" {
        let init = m.request(json!({"op":"initialize"})).unwrap();
        for event in init.events {
            match event {
                Event::Stdout(b) | Event::Stderr(b) => captured.extend(b),
            }
        }
        start = std::time::Instant::now();
        let reply = m
            .request(json!({"op":"call","method":if mode=="finalize" {"finalize"} else {"sync"}}))
            .unwrap();
        for event in reply.events {
            match event {
                Event::Stdout(b) | Event::Stderr(b) => captured.extend(b),
            }
        }
        let error = reply.error.unwrap();
        assert_eq!(error.class, "CapabilityError");
        let error = format!("ERROR: {}\n", error.message);
        if mode == "activate" {
            captured.extend(error.as_bytes());
        } else {
            eprint!("{error}");
        }
    }
    m.finish().unwrap();
    assert!(start.elapsed().as_secs_f64() < 1.0);
    let value = if mode == "import" {
        Value::Null
    } else if mode == "console" {
        json!(1)
    } else if r["closing"] == true {
        json!(["failed", {"reason_wtf8":captured.strip_suffix(b"\n").unwrap_or(&captured)}])
    } else {
        json!(["failed", {"reason":std::str::from_utf8(&captured).unwrap().trim()}])
    };
    fs::write(root.join("result.json"), value.to_string()).unwrap();
    std::process::exit(0);
}

#[test]
fn pinned_output_semantics() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e17b2a.json")).unwrap();
    check_output_records(records);
}

#[test]
fn retained_stdout_matches_pinned_python() {
    closing_output_records("retained-stdout");
}

#[test]
fn captured_surrogate_matches_pinned_python() {
    closing_output_records("surrogate");
}

fn closing_output_records(case: &str) {
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/y-e17b2ac.json")).unwrap();
    check_output_records(records.into_iter().filter(|r| r["case"] == case).collect());
}

fn check_output_records(records: Vec<Value>) {
    for r in records {
        let source = r["source"].as_str().unwrap().replace(
            "from mir.core.capabilities.manager import CapabilityError",
            "class CapabilityError(RuntimeError): pass",
        );
        let source = source.replace(
            "def __init__(self,*a,**kw): pass",
            "def __init__(self,*a,**kw): self.held=os.dup(1); __import__('threading').Thread(target=lambda: __import__('time').sleep(2)).start()",
        );
        let (_temp, root, _cli) = setup(Some(&source));
        let out = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "output_boundary_child", "--nocapture"])
            .current_dir(&root)
            .env_clear()
            .env("HOME", &root)
            .env("Y_E17B2A_RECORD", r.to_string())
            .output()
            .unwrap();
        assert!(out.status.success(), "{:?}", out);
        let suffix = |b: &[u8]| {
            b.windows(10)
                .position(|s| s == b"<boundary>")
                .map(|i| b[i + 10..].to_vec())
                .unwrap()
        };
        let value: Value =
            serde_json::from_slice(&fs::read(root.join("result.json")).unwrap()).unwrap();
        let actual =
            json!({"stdout":suffix(&out.stdout),"stderr":suffix(&out.stderr),"value":value});
        let expected = json!({"stdout":r["stdout"],"stderr":r["stderr"],"value":r["value"]});
        assert_eq!(actual, expected, "{}/{}", r["mode"], r["case"]);
    }
}

#[test]
fn owned_provider_classes() {
    check_provider_classes(None);
}

#[test]
fn provider_subclass_caught() {
    check_provider_classes(Some("subclass"));
}

#[test]
fn provider_same_name_propagated() {
    check_provider_classes(Some("same-name"));
}

fn check_provider_classes(case: Option<&str>) {
    use handoff_packet::mir_cli::bootstrap::{CapabilityOutput, ProductionHost};
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/y-e17b2b1a.json")).unwrap();
    let mut mismatches = Vec::new();
    for r in records
        .into_iter()
        .filter(|r| case.is_none_or(|c| r["case"] == c))
    {
        let source = format!(
            "import os\n__import__('pathlib').Path('pid').write_text(str(os.getpid()))\nclass CapabilityError(RuntimeError): pass\nclass CapabilityConfigError(ValueError): pass\nCapabilityConfigError.__module__ = 'mir.core.capabilities.config'\n{}",
            r["source"].as_str().unwrap()
        );
        let (_temp, root, cli) = setup(Some(&source));
        let mut host = ProductionHost::default();
        let actual = match host.import_capabilities(&cli, &root, Output::Console) {
            Err(e) => json!({"class":e.class,"message":e.message}),
            Ok(_) => {
                assert_eq!(fs::read_to_string(root.join("trace")).unwrap(), "import\n");
                let m = host
                    .import_capabilities(&cli, &root, Output::Console)
                    .unwrap();
                let args = vec![
                    "status".into(),
                    "--project-root".into(),
                    root.display().to_string(),
                    "--json".into(),
                ];
                match CapabilityOutput::run(&args, m) {
                    Ok(out) => {
                        assert_eq!(
                            out.stdout.as_bytes(),
                            serde_json::from_value::<Vec<u8>>(r["stdout"].clone()).unwrap()
                        );
                        assert_eq!(
                            out.stderr.as_bytes(),
                            serde_json::from_value::<Vec<u8>>(r["stderr"].clone()).unwrap()
                        );
                        json!({"code":out.code})
                    }
                    Err(e) => json!({"class":e.class,"message":e.message}),
                }
            }
        };
        let pid = fs::read_to_string(root.join("pid")).unwrap();
        assert!(
            !std::process::Command::new("/bin/kill")
                .args(["-0", &pid])
                .output()
                .unwrap()
                .status
                .success()
        );
        let expected = r.get("result").cloned().unwrap_or_else(|| {
            assert_eq!(r["reference_exit"], 23);
            json!({"class":"RuntimeError","message":"manager reply EOF"})
        });
        if actual != expected {
            mismatches.push(json!([r["stage"], actual, expected]));
        }
        assert_eq!(
            fs::read_to_string(root.join("trace")).unwrap(),
            r["trace"].as_str().unwrap()
        );
    }
    assert!(mismatches.is_empty(), "{mismatches:?}");
}
