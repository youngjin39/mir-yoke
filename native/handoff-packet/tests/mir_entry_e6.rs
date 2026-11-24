use serde_json::Value;
use std::{
    fs,
    io::{BufRead, Read, Write},
    net::TcpListener,
    process::Command,
    thread,
};

#[test]
fn context_embedding_provider_binding() {
    provider_binding(None);
}
#[test]
fn no_body_204_keep_alive() {
    provider_binding(Some("required-204"));
}
#[test]
fn no_body_304_keep_alive() {
    provider_binding(Some("required-304"));
}
#[test]
#[should_panic(expected = "missing E6 reference")]
fn missing_record_fails_explicitly() {
    records("s09-missing-record-do-not-create");
}
fn records(name: &str) -> Vec<Value> {
    let suffix = if cfg!(windows) { "-windows" } else { "" };
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join(format!("tests/fixtures/{name}{suffix}.json"));
    let text = fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "missing E6 reference {}: {e}; run generate_y_e6.py on this platform",
            path.display()
        )
    });
    serde_json::from_str(&text).unwrap()
}
fn provider_binding(only: Option<&str>) {
    let mut records = records("y-e6");
    for (mode, error) in [
        ("tls", "HTTPS embedding transport is not supported"),
        (
            "proxy",
            "Environment proxy embedding transport is not supported",
        ),
    ] {
        let mut r = records
            .iter()
            .find(|r| r["mode"] == "required-shape")
            .unwrap()
            .clone();
        r["mode"] = mode.into();
        r["native_error"] = error.into();
        records.push(r);
    }
    for r in records {
        if only.is_some_and(|mode| r["mode"] != mode) {
            continue;
        }
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        fs::create_dir(root.join("notes")).unwrap();
        fs::write(
            root.join("notes/a.md"),
            if cfg!(windows) {
                "Synthetic archive document.\r\n"
            } else {
                "Synthetic archive document.\n"
            },
        )
        .unwrap();
        let c = handoff_packet::mir_core::memory::store::connect(&root.join("memory.db"), None)
            .unwrap();
        handoff_packet::mir_core::memory::store::apply_migrations(&c.conn).unwrap();
        drop(c);
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let url = format!("http://{}/v1/", listener.local_addr().unwrap());
        let mut config = r["config"].as_str().unwrap().replace("@URL@", &url);
        if r["mode"] == "tls" {
            config = config.replace("http://", "https://");
        }
        let listener = (!matches!(
            r["mode"].as_str().unwrap(),
            "required-refused" | "tls" | "proxy"
        ))
        .then_some(listener);
        let run = |argv: Vec<&str>| {
            let mut cmd = Command::new(env!("CARGO_BIN_EXE_mir"));
            cmd.args(argv)
                .env_clear()
                .envs(
                    ["SystemRoot", "WINDIR"]
                        .into_iter()
                        .filter(|_| cfg!(windows))
                        .filter_map(|key| std::env::var_os(key).map(|value| (key, value))),
                )
                .env("HOME", &root)
                .env("USERPROFILE", &root)
                .env("PYTHONIOENCODING", "utf-8")
                .env("HTTP_PROXY", "http://127.0.0.1:1")
                .env("NO_PROXY", if r["mode"] == "proxy" { "" } else { "*" })
                // Exercise the retired switch when the parent runner sets it.
                .envs(std::env::var_os("MIR_E6_DIAG").map(|value| ("MIR_E6_DIAG", value)))
                .current_dir(&root);
            if r["mode"] == "proxy" {
                cmd.env("HTTP_PROXY", "http://127.0.0.1:1");
            }
            if r["mode"] != "no-key" {
                cmd.env("SYNTHETIC_KEY", "fake-only");
            }
            bounded_output(&mut cmd)
        };
        if r["mode"].as_str().unwrap().starts_with("reindex") {
            fs::write(
                root.join("harness_a.toml"),
                config
                    .replace("enabled=true", "enabled=false")
                    .replace("fingerprint=\"synthetic-v1\"", "fingerprint=\"\""),
            )
            .unwrap();
            assert!(
                run(vec!["context", "sync", "--db", "memory.db"])
                    .status
                    .success()
            );
        }
        fs::write(root.join("harness_a.toml"), config).unwrap();
        let body = r["body"].as_str().unwrap().to_owned();
        let status = r["status"].as_u64().unwrap();
        let mode = r["mode"].as_str().unwrap().to_owned();
        let (cancel, cancelled) = std::sync::mpsc::channel();
        let server = thread::spawn(move || {
            let listener = listener?;
            loop {
                match accept_request(&listener, &cancelled) {
                    Ok((mut stream, _)) => {
                        stream.set_nonblocking(false).unwrap();
                        stream.set_nodelay(true).unwrap();
                        stream
                            .set_read_timeout(Some(std::time::Duration::from_secs(2)))
                            .unwrap();
                        let mut bytes = Vec::new();
                        let mut reader = std::io::BufReader::new(&mut stream);
                        while !bytes.ends_with(b"\r\n\r\n") {
                            assert_ne!(reader.read_until(b'\n', &mut bytes).unwrap(), 0);
                        }
                        let header = String::from_utf8(bytes).unwrap();
                        let size: usize = header
                            .lines()
                            .find_map(|l| {
                                l.to_lowercase()
                                    .strip_prefix("content-length:")
                                    .map(|s| s.trim().parse().unwrap())
                            })
                            .unwrap();
                        let mut input = vec![0; size];
                        reader.read_exact(&mut input).unwrap();
                        drop(reader);
                        if mode == "required-timeout" {
                            hold_socket(stream, &cancelled, std::time::Duration::ZERO);
                            return Some((header, String::from_utf8(input).unwrap()));
                        }
                        if mode == "required-disconnect" {
                            return Some((header, String::from_utf8(input).unwrap()));
                        }
                        if matches!(mode.as_str(), "required-204" | "required-304") {
                            let reason = if status == 204 {
                                "No Content"
                            } else {
                                "Not Modified"
                            };
                            stream.write_all(format!(
                                "HTTP/1.1 {status} {reason}\r\nConnection: keep-alive\r\n\r\n"
                            ).as_bytes())
                            .unwrap();
                            hold_socket(stream, &cancelled, std::time::Duration::from_secs(3));
                            return Some((header, String::from_utf8(input).unwrap()));
                        } else if mode == "required-garbage" {
                            stream.write_all(b"garbage\r\n\r\n").unwrap();
                        } else if mode == "required-short" {
                            stream
                                .write_all(
                                    format!(
                                        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{body}",
                                        body.len() + 1
                                    )
                                    .as_bytes(),
                                )
                                .unwrap();
                        } else if mode == "chunked" {
                            stream.write_all(format!("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n{:x};fake=yes\r\n{body}\r\n0\r\nX-Fake: yes\r\n\r\n", body.len()).as_bytes()).unwrap();
                        } else if mode == "close" {
                            stream
                                .write_all(format!("HTTP/1.1 200 OK\r\n\r\n{body}").as_bytes())
                                .unwrap();
                        } else if mode == "required-gzip" {
                            stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n").unwrap();
                        } else {
                            stream.write_all(format!("HTTP/1.1 {status} {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", if status == 200 { "OK" } else { "Service Unavailable" }, body.len()).as_bytes()).unwrap();
                        }
                        return Some((header, String::from_utf8(input).unwrap()));
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::Interrupted => return None,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                    Err(e) => panic!("accept failed: {e:?}"),
                }
            }
        });
        let out = run(r["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect());
        let _ = cancel.send(());
        let request = server.join().unwrap();
        if r["native_error"].is_string() || r["mode"] == "required-gzip" {
            assert_eq!(out.status.code(), Some(1));
            assert!(
                String::from_utf8_lossy(&out.stdout).contains(
                    r["native_error"]
                        .as_str()
                        .unwrap_or("Content-Encoding gzip is not supported")
                ),
                "{out:?}"
            );
            continue;
        }
        assert_eq!(
            out.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{}: {:?}",
            r["mode"],
            out
        );
        let mut expected_stdout = r["stdout"].as_str().unwrap().to_owned();
        if cfg!(unix) && r["mode"] == "required-refused" {
            // Independent closed loopback endpoint, not the product's socket/error.
            let probe = TcpListener::bind("127.0.0.1:0").unwrap();
            let address = probe.local_addr().unwrap();
            drop(probe);
            let error =
                std::net::TcpStream::connect_timeout(&address, std::time::Duration::from_secs(1))
                    .unwrap_err();
            assert_eq!(error.kind(), std::io::ErrorKind::ConnectionRefused);
            let errno = error
                .raw_os_error()
                .expect("refused probe must have OS errno");
            let suffix = expected_stdout
                .strip_prefix("  [failed] a.md: insert: [Errno 61]")
                .expect("pinned Darwin refused errno slot");
            expected_stdout = format!("  [failed] a.md: insert: [Errno {errno}]{suffix}");
        }
        assert_eq!(
            String::from_utf8(out.stdout)
                .unwrap()
                .replace(url.trim_end_matches('/'), "@URLBASE@")
                .as_bytes(),
            expected_stdout.as_bytes(),
            "{}",
            r["mode"]
        );
        assert_eq!(
            out.stderr,
            r["stderr"].as_str().unwrap().as_bytes(),
            "{}",
            r["mode"]
        );
        if r["mode"] == "required-refused" {
            assert!(request.is_none());
            continue;
        }
        let (header, body) = request.expect("provider must send a request");
        let expected = &r["requests"][0];
        assert!(header.starts_with(&format!(
            "POST {} HTTP/1.1",
            expected["path"].as_str().unwrap()
        )));
        let auth = header.lines().find_map(|s| {
            s.to_lowercase()
                .starts_with("authorization:")
                .then(|| s.split_once(':').unwrap().1.trim())
        });
        assert_eq!(auth, expected["auth"].as_str());
        assert_eq!(body, expected["raw_body"].as_str().unwrap());
        let header = header.to_ascii_lowercase();
        for (name, value) in expected["headers"].as_object().unwrap() {
            let value = value.as_str().unwrap().replace(
                "@PORT@",
                url.split(':').nth(2).unwrap().split('/').next().unwrap(),
            );
            assert!(
                header.contains(&format!("{name}: {}\r\n", value.to_ascii_lowercase())),
                "{header}"
            );
        }
        assert!(header.contains("accept-encoding: identity\r\n"));
        assert!(header.contains("user-agent: mir-native\r\n"));
        let db = handoff_packet::mir_core::memory::store::connect(
            &root.join("memory.db"),
            handoff_packet::mir_core::memory::store::ConnectOptions {
                timeout: None,
                vec_loading: handoff_packet::mir_core::memory::store::VecLoading::Bundled,
            },
        )
        .unwrap();
        for (i, table) in [
            "external_documents",
            "external_chunks",
            "external_chunks_vec",
        ]
        .iter()
        .enumerate()
        {
            let count: i64 = db
                .conn
                .query_row(&format!("SELECT count(*) FROM {table}"), [], |r| r.get(0))
                .unwrap();
            assert_eq!(count, r["counts"][i], "{} {table}", r["mode"]);
        }
    }
}

// The unit oracle checks the original host/pattern pair. For the CLI boundary,
// move that host into NO_PROXY so even a broken guard can only dial loopback.
#[test]
fn idna_refusal_cli() {
    let records = records("y-e6-proxy");
    let wire = self::records("y-e6");
    let config = wire.iter().find(|r| r["mode"] == "required-shape").unwrap()["config"]
        .as_str()
        .unwrap()
        .replace("@URL@", "http://127.0.0.1:1/v1/");
    for r in records.iter().filter(|r| r["native_open"] == true) {
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        fs::create_dir(root.join("notes")).unwrap();
        fs::write(
            root.join("notes/a.md"),
            if cfg!(windows) {
                "Synthetic archive document.\r\n"
            } else {
                "Synthetic archive document.\n"
            },
        )
        .unwrap();
        fs::write(root.join("harness_a.toml"), &config).unwrap();
        let c = handoff_packet::mir_core::memory::store::connect(&root.join("memory.db"), None)
            .unwrap();
        handoff_packet::mir_core::memory::store::apply_migrations(&c.conn).unwrap();
        drop(c);
        let out = Command::new(env!("CARGO_BIN_EXE_mir"))
            .args(["context", "sync", "--db", "memory.db"])
            .env_clear()
            .envs(
                ["SystemRoot", "WINDIR"]
                    .into_iter()
                    .filter(|_| cfg!(windows))
                    .filter_map(|key| std::env::var_os(key).map(|value| (key, value))),
            )
            .env("HOME", &root)
            .env("USERPROFILE", &root)
            .env("PYTHONIOENCODING", "utf-8")
            .env("HTTP_PROXY", "http://127.0.0.1:1")
            .env(
                "NO_PROXY",
                format!(
                    "{},{}",
                    r["pattern"].as_str().unwrap(),
                    r["host"].as_str().unwrap()
                ),
            )
            .env("SYNTHETIC_KEY", "fake-only")
            .current_dir(&root)
            .output()
            .unwrap();
        assert_eq!(
            out.status.code(),
            Some(r["native_exit"].as_i64().unwrap() as i32),
            "{r}: {out:?}"
        );
        assert!(
            String::from_utf8_lossy(&out.stdout).contains(r["native_message"].as_str().unwrap()),
            "{r}: {out:?}"
        );
        assert!(out.stderr.is_empty(), "{r}: {out:?}");
    }
}

fn accept_request(
    listener: &TcpListener,
    cancelled: &std::sync::mpsc::Receiver<()>,
) -> std::io::Result<(std::net::TcpStream, std::net::SocketAddr)> {
    let result = listener.accept();
    if result
        .as_ref()
        .is_err_and(|e| e.kind() == std::io::ErrorKind::WouldBlock)
    {
        return match cancelled.recv_timeout(std::time::Duration::from_millis(5)) {
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => result,
            _ => Err(std::io::Error::new(
                std::io::ErrorKind::Interrupted,
                "child completed",
            )),
        };
    }
    result
}

// The server owns its socket until the client lifecycle ends.
fn hold_socket(
    stream: std::net::TcpStream,
    completed: &std::sync::mpsc::Receiver<()>,
    minimum: std::time::Duration,
) {
    let started = std::time::Instant::now();
    let _ = completed.recv();
    thread::sleep(minimum.saturating_sub(started.elapsed()));
    drop(stream);
}

#[test]
fn socket_hold_waits_for_client_completion() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let mut client = std::net::TcpStream::connect(listener.local_addr().unwrap()).unwrap();
    let (socket, _) = listener.accept().unwrap();
    let (complete, completed) = std::sync::mpsc::channel();
    let server = thread::spawn(move || hold_socket(socket, &completed, std::time::Duration::ZERO));
    // A delayed client must see its own read timeout, never a server timer's EOF.
    thread::sleep(std::time::Duration::from_millis(3100));
    client
        .set_read_timeout(Some(std::time::Duration::from_millis(20)))
        .unwrap();
    let observed = client.read(&mut [0]);
    complete.send(()).ok();
    server.join().unwrap();
    assert!(
        observed.as_ref().is_err_and(|e| matches!(
            e.kind(),
            std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
        )),
        "{observed:?}"
    );
}

fn bounded_output(command: &mut Command) -> std::process::Output {
    let stdout = tempfile::NamedTempFile::new().unwrap();
    let mut child = command
        .stdin(std::process::Stdio::null())
        .stdout(stdout.reopen().unwrap())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    let mut stderr = child.stderr.take().unwrap();
    let reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        stderr.read_to_end(&mut bytes).unwrap();
        bytes
    });
    let started = std::time::Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if started.elapsed() > std::time::Duration::from_secs(180) {
            child.kill().unwrap();
            child.wait().unwrap();
            reader.join().unwrap();
            panic!("synthetic child exceeded 180s watchdog");
        }
        thread::sleep(std::time::Duration::from_millis(10));
    };
    std::process::Output {
        status,
        stdout: fs::read(stdout.path()).unwrap(),
        stderr: reader.join().unwrap(),
    }
}

#[test]
fn delayed_request_and_no_request_shutdown() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let address = listener.local_addr().unwrap();
    let (cancel, cancelled) = std::sync::mpsc::channel();
    let server = thread::spawn(move || {
        loop {
            match accept_request(&listener, &cancelled) {
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                result => break result,
            }
        }
    });
    thread::sleep(std::time::Duration::from_secs(4 + 1));
    let client = std::net::TcpStream::connect(address);
    let received = server.join().unwrap();
    assert!(
        client.is_ok() && received.is_ok(),
        "delayed child lost listener: {client:?} {received:?}"
    );
    drop(cancel);
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let (cancel, cancelled) = std::sync::mpsc::channel();
    cancel.send(()).unwrap();
    let started = std::time::Instant::now();
    assert_eq!(
        accept_request(&listener, &cancelled).unwrap_err().kind(),
        std::io::ErrorKind::Interrupted
    );
    assert!(started.elapsed() < std::time::Duration::from_secs(1));
}
