use handoff_packet::mir_cli::bootstrap_adoption::{self, Host};
use serde_json::{Value, json};
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    process::Command,
    time::{Duration, Instant},
};

fn records() -> Vec<Value> {
    let text = if cfg!(windows) {
        fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/y-e14b-windows.json"
        ))
        .expect("capture on Windows first: generate_y_e14b.py")
    } else {
        include_str!("fixtures/y-e14b.json").to_owned()
    };
    serde_json::from_str(&text).unwrap()
}

#[test]
fn parser_regressions() {
    let root = tempfile::tempdir().unwrap();
    let mut failures = Vec::new();
    for r in &records()[..2] {
        let argv: Vec<_> = r["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        let actual = bootstrap_adoption::parse(&argv, root.path());
        if actual[0]["error"][1]
            .as_str()
            .and_then(|v| v.parse::<i64>().ok())
            != r["exit"].as_i64()
            || actual[1] != r["stdout"]
            || actual[2] != r["stderr"]
        {
            failures.push(format!("{argv:?}: {actual}"));
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

fn evaluator_target(os: &str, arch: &str) -> Option<String> {
    handoff_packet::mir_core::capabilities::native::host_target(
        match os {
            "macos" => "Darwin",
            "linux" => "Linux",
            "windows" => "Windows",
            _ => "",
        },
        arch,
    )
}

#[test]
fn evaluator_worker_host_target() {
    assert_eq!(
        evaluator_target("windows", "x86_64").as_deref(),
        Some("x86_64-pc-windows-msvc")
    );
}

#[test]
fn remote_evaluator() {
    if let Ok(mode) = std::env::var("E14B_WORKER") {
        let root = std::env::current_dir().unwrap();
        let target = evaluator_target(std::env::consts::OS, std::env::consts::ARCH).unwrap();
        let pin = json!({"url":std::env::var("E14B_URL").unwrap(), "size":20,
            "sha256":"e75a835d98bf762a52bd437cea5d6c93ffceb5019914975c6918df6f9f7e746d"});
        let lock = json!({"plugins":{"test":{}},"native_artifacts":{"bootstrap-gate":{
            "plugin":"test","install_path":"bin/bootstrap-gate","targets":{target:pin}}}});
        let source = root.join("source");
        fs::create_dir_all(source.join(".mir")).unwrap();
        fs::write(source.join(".mir/capability-lock.json"), lock.to_string()).unwrap();
        let result = bootstrap_adoption::LocalHost.install_evaluator(&root, &source, None);
        let installed = fs::read_to_string(root.join(".mir/bin/bootstrap-gate")).ok();
        let r = records().into_iter().find(|r| r["mode"] == mode).unwrap();
        assert_eq!(json!(result), r["result"]);
        assert_eq!(json!(installed), r["installed"]);
        assert!(!root.join(".mir/bin/bootstrap-gate.exe").exists());
        if cfg!(windows) {
            assert!(result.is_none());
            assert!(installed.is_none());
        }
        return;
    }
    let mut failures = Vec::new();
    for mode in [
        "http-ok",
        "http-error",
        "http-disconnect",
        "http-oversize",
        "https-refusal",
        "proxy-refusal",
    ] {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let scheme = if mode == "https-refusal" {
            "https"
        } else {
            "http"
        };
        let url = format!("{scheme}://{}/artifact", listener.local_addr().unwrap());
        let server = std::thread::spawn(move || {
            let start = Instant::now();
            while start.elapsed() < Duration::from_secs(3) {
                if let Ok((mut stream, _)) = listener.accept() {
                    stream
                        .set_read_timeout(Some(Duration::from_secs(2)))
                        .unwrap();
                    let mut bytes = Vec::new();
                    while !bytes.ends_with(b"\r\n\r\n") {
                        let mut b = [0];
                        stream.read_exact(&mut b).unwrap();
                        bytes.push(b[0]);
                    }
                    assert!(bytes.starts_with(b"GET /artifact HTTP/1.1\r\n"));
                    assert!(!bytes.windows(15).any(|w| w == b"Content-Length:"));
                    if mode == "http-disconnect" {
                        return true;
                    }
                    let status = if mode == "http-error" {
                        "404 Not Found"
                    } else {
                        "200 OK"
                    };
                    let body = if mode == "http-oversize" {
                        "synthetic evaluator\nx"
                    } else {
                        "synthetic evaluator\n"
                    };
                    write!(stream, "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
                    return true;
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            false
        });
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args(["--exact", "remote_evaluator", "--nocapture"])
            .env_clear()
            .env("HOME", &root)
            .env("USERPROFILE", &root)
            .env(
                "E14B_WORKER",
                if mode == "proxy-refusal" && !cfg!(windows) {
                    "https-refusal"
                } else {
                    mode
                },
            )
            .env("E14B_URL", url)
            .current_dir(&root);
        for key in ["SystemRoot", "WINDIR"] {
            if let Some(value) = std::env::var_os(key) {
                command.env(key, value);
            }
        }
        if mode == "proxy-refusal" {
            command.env("HTTP_PROXY", "http://127.0.0.1:1");
        }
        let out = command.output().unwrap();
        let contacted = server.join().unwrap();
        let stderr = String::from_utf8_lossy(&out.stderr);
        if cfg!(windows) {
            let record = records().into_iter().find(|r| r["mode"] == mode).unwrap();
            assert_eq!(record["contacted"], false);
            assert_eq!(record["stderr"], "");
            assert_eq!(json!(contacted), record["contacted"]);
            assert_eq!(json!(stderr), record["stderr"]);
        }
        let refusal = if cfg!(windows) {
            ""
        } else if mode == "proxy-refusal" {
            "UnsupportedProtocol: Environment proxy embedding transport is not supported\n"
        } else {
            "UnsupportedProtocol: HTTPS embedding transport is not supported\n"
        };
        if !out.status.success()
            || contacted != (!cfg!(windows) && mode.starts_with("http-"))
            || ((cfg!(windows) || mode.ends_with("refusal")) && stderr != refusal)
        {
            failures.push(format!(
                "{mode}: contacted={contacted} stdout={} stderr={stderr}",
                String::from_utf8_lossy(&out.stdout)
            ));
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
