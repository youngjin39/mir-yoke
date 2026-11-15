#![cfg(unix)]
use handoff_packet::mir_cli::{bootstrap as b, capability_manager::Output};
use serde_json::{Value, json};
use std::{fs, os::unix::fs::PermissionsExt, path::PathBuf, process::Command};
fn setup(source: &str) -> (tempfile::TempDir, PathBuf) {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().canonicalize().unwrap();
    fs::copy(env!("CARGO_BIN_EXE_mir"), root.join("mir")).unwrap();
    fs::create_dir(root.join(".mir")).unwrap();
    let package = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../src/mir");
    let script = format!(
        "import sys, pathlib, shutil, runpy\nr=pathlib.Path({})\nshutil.copytree({},r/'pkg/mir',dirs_exist_ok=True)\np=r/'pkg/mir/core/capabilities/manager.py'\np.write_text(p.read_text()+ '\\n' + {})\nsys.path.insert(0,str(r/'pkg'))\nsys.argv=['bridge',sys.argv[-1]]\nrunpy.run_module('mir.cli.capability_manager_bridge',run_name='__main__')\n",
        json!(root),
        json!(package),
        json!(format!(
            "import os\nfrom pathlib import Path\nPath('pid').write_text(str(os.getpid()))\n{source}"
        ))
    );
    fs::write(root.join("launch.py"), script).unwrap();
    let python = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.venv/bin/python");
    fs::write(
        root.join("python"),
        format!(
            "#!/bin/sh\nexec '{}' -I '{}' \"$@\"\n",
            python.display(),
            root.join("launch.py").display()
        ),
    )
    .unwrap();
    fs::set_permissions(root.join("python"), fs::Permissions::from_mode(0o755)).unwrap();
    (tmp, root)
}
fn reaped(root: &std::path::Path) {
    let pid = fs::read_to_string(root.join("pid")).unwrap();
    assert!(
        !Command::new("/bin/kill")
            .args(["-0", &pid])
            .output()
            .unwrap()
            .status
            .success()
    );
    assert!(!root.join(".mir/memory.db").exists());
}
#[test]
fn public_console_records() {
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/y-e17b2b1a.json")).unwrap();
    for r in records {
        let (_tmp, root) = setup(r["source"].as_str().unwrap());
        let out = Command::new(root.join("mir"))
            .args(["capability", "status", "--project-root", ".", "--json"])
            .env_clear()
            .env("HOME", &root)
            .env("PATH", &root)
            .current_dir(&root)
            .output()
            .unwrap();
        let (code, stderr) = if r["stage"] == "transport" {
            (1, b"RuntimeError: manager reply EOF\n".to_vec())
        } else if r["result"].get("class").is_some() {
            (1, {
                let public: Vec<Value> =
                    serde_json::from_str(include_str!("fixtures/y-e17b2b2.json")).unwrap();
                public
                    .iter()
                    .find(|p| {
                        p["mode"] == "console-exception"
                            && p["stage"] == r["stage"]
                            && p["case"] == r["case"]
                    })
                    .map(|p| p["line"].as_str().unwrap().to_owned())
                    .unwrap_or_else(|| {
                        format!(
                            "{}: {}\n",
                            r["result"]["class"].as_str().unwrap(),
                            r["result"]["message"].as_str().unwrap()
                        )
                    })
                    .into_bytes()
            })
        } else {
            (
                r["result"]["code"].as_i64().unwrap() as i32,
                serde_json::from_value::<Vec<u8>>(r["stderr"].clone()).unwrap(),
            )
        };
        assert_eq!(out.status.code(), Some(code), "{r}");
        assert_eq!(out.stderr, stderr, "{r}");
        assert_eq!(
            out.stdout,
            serde_json::from_value::<Vec<u8>>(r.get("stdout").cloned().unwrap_or(json!([])))
                .unwrap(),
            "{r}"
        );
        assert_eq!(
            fs::read_to_string(root.join("trace")).unwrap(),
            r["trace"].as_str().unwrap()
        );
        reaped(&root);
    }
}
#[test]
fn bootstrap_child() {
    let Ok(data) = std::env::var("Y_E17B2B2") else {
        return;
    };
    let r: Value = serde_json::from_str(&data).unwrap();
    let root = std::env::current_dir().unwrap();
    let mut host = b::ProductionHost::default();
    assert!(b::Host::capability_main(&mut host, &[]).is_err());
    host.import_capabilities(
        &root.join("mir"),
        &root,
        if r["mode"] == "activate" {
            Output::Activate
        } else {
            Output::Finalize
        },
    )
    .unwrap();
    let prior = json!({"status":"restart_required"});
    let result = if r["mode"] == "activate" {
        b::activate_capabilities(&root, "code_app", &mut host)
    } else {
        b::finalize_capabilities(&root, Some(&prior), &mut host)
    };
    let value = match result {
        Ok((s, v)) => json!([s, b::scalar_evidence(&v).unwrap()]),
        Err(e) => json!({"class":e.class,"message":e.message}),
    };
    fs::write(root.join("result.json"), value.to_string()).unwrap();
}
#[test]
fn bootstrap_production_capture() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e17b2a.json")).unwrap();
    for r in records
        .into_iter()
        .filter(|r| r["mode"] == "activate" || r["mode"] == "finalize")
    {
        let (_tmp, root) = setup(r["source"].as_str().unwrap());
        let out = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "bootstrap_child", "--nocapture", "--quiet"])
            .env_clear()
            .env("HOME", &root)
            .env("PATH", &root)
            .env("Y_E17B2B2", r.to_string())
            .current_dir(&root)
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        let actual: Value =
            serde_json::from_slice(&fs::read(root.join("result.json")).unwrap()).unwrap();
        assert_eq!(actual, r["value"], "{r}");
        assert_eq!(
            out.stderr,
            serde_json::from_value::<Vec<u8>>(r["stderr"].clone()).unwrap()
        );
        let mut stdout = b"\nrunning 1 test\n".to_vec();
        stdout.extend(serde_json::from_value::<Vec<u8>>(r["stdout"].clone()).unwrap());
        assert!(out.stdout.starts_with(&stdout), "{:?}", out.stdout);
        reaped(&root);
    }
}

#[test]
fn original_console_replays() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e17.json")).unwrap();
    for r in records.into_iter().filter(|r| r["mode"] == "console") {
        let source = format!(
            "class CapabilityManager:\n def __init__(self,*a,**kw): pass\n def status(self,*a,**kw): return dict(ready=True)\n def sync(self,*a,**kw):\n  if {} == 'console-error': raise CapabilityError('provider refused')\n  if {} == 'console-change': Path('.mir/capability-lock.json').write_text('{{}}')\n  return dict(ready=True)\n",
            r["case"], r["case"]
        );
        let (_tmp, root) = setup(&source);
        let args: Vec<_> = r["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        let out = Command::new(root.join("mir"))
            .arg("capability")
            .args(args)
            .env_clear()
            .env("HOME", &root)
            .env("PATH", &root)
            .current_dir(&root)
            .output()
            .unwrap();
        assert_eq!(
            out.status.code(),
            r["result"]["value"].as_i64().map(|v| v as i32)
        );
        assert_eq!(out.stdout, r["stdout"].as_str().unwrap().as_bytes());
        assert_eq!(out.stderr, r["stderr"].as_str().unwrap().as_bytes());
        assert_eq!(
            root.join(".mir/capability-lock.json").exists(),
            r["case"] == "console-change"
        );
        reaped(&root);
    }
}

#[test]
fn finalize_stderr_os_failure() {
    let source = "class CapabilityManager:\n def __init__(self,*a,**kw): pass\n def finalize(self,*a,**kw): raise CapabilityError('refused')\n";
    let (_tmp, root) = setup(source);
    let out = Command::new("/bin/sh")
        .args(["-c", "exec \"$@\" 2</dev/null", "sh"])
        .arg(std::env::current_exe().unwrap())
        .args(["--exact", "bootstrap_child", "--nocapture", "--quiet"])
        .env_clear()
        .env("HOME", &root)
        .env("PATH", &root)
        .env("Y_E17B2B2", r#"{"mode":"finalize"}"#)
        .current_dir(&root)
        .output()
        .unwrap();
    assert!(out.status.success());
    let result: Value =
        serde_json::from_slice(&fs::read(root.join("result.json")).unwrap()).unwrap();
    assert_eq!(result["class"], "OSError");
    assert_eq!(result["message"], "[Errno 9] Bad file descriptor");
    reaped(&root);
}
