use handoff_packet::mir_core::memory::{external_store::*, store, vector_index};
use serde_json::Value;
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    process::Command,
    thread,
    time::Duration,
};

#[test]
fn frozen_pull_console_provider() {
    pull();
}
#[test]
#[should_panic(expected = "missing E8 reference")]
fn missing_record_fails_explicitly() {
    records("s10-missing-record-do-not-create");
}
fn records(name: &str) -> Vec<Value> {
    let suffix = if cfg!(windows) { "-windows" } else { "" };
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join(format!("tests/fixtures/{name}{suffix}.json"));
    let text = fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "missing E8 reference {}: {e}; run generate_y_e8.py on this platform",
            path.display()
        )
    });
    serde_json::from_str(&text).unwrap()
}
fn pull() {
    let records = records("y-e8");
    for r in records {
        let mode = r["mode"].as_str().unwrap();
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        fs::create_dir(root.join("notes")).unwrap();
        for (i, doc) in r["docs"].as_array().unwrap().iter().enumerate() {
            // Match the generator's Python text-mode write before indexing bytes.
            let doc = doc.as_str().unwrap();
            let bytes = if cfg!(windows) {
                doc.replace('\n', "\r\n")
            } else {
                doc.to_owned()
            };
            fs::write(root.join(format!("notes/{i}.md")), bytes).unwrap();
        }
        let c = store::connect(
            &root.join("memory.db"),
            store::ConnectOptions {
                timeout: None,
                vec_loading: store::VecLoading::Bundled,
            },
        )
        .unwrap();
        store::apply_migrations(&c.conn).unwrap();
        let clock = || "2026-11-15T00:00:00Z".into();
        let es = ExternalStore::new(&c, &clock).unwrap();
        if mode != "no-archives" {
            let aid = es
                .register(&Registration {
                    slug: "notes".into(),
                    root_path: root.join("notes").to_str().unwrap().into(),
                    mode: "indexed".into(),
                    owner: "synthetic".into(),
                    glob_include: vec![],
                    glob_exclude: vec![],
                    historical_glob: vec![],
                    chunk_size: 800,
                    chunk_overlap: 100,
                })
                .unwrap();
            es.scan(aid, None).unwrap();
            for i in 0..3 {
                let mut v = vec![0.0; 1024];
                v[if mode == "ties" { 0 } else { 2 - i }] = 1.0;
                if mode != "no-vectors" {
                    vector_index::upsert_vector(
                        &c.conn,
                        i as i64 + 1,
                        &v,
                        1024,
                        "external_chunks_vec",
                    )
                    .unwrap();
                }
            }
            c.conn
                .execute(
                    "INSERT OR REPLACE INTO external_store_meta(key,value) VALUES (?,?)",
                    [
                        EMBEDDING_FINGERPRINT_KEY,
                        if mode == "mismatch" {
                            "wrong"
                        } else {
                            "synthetic-v1"
                        },
                    ],
                )
                .unwrap();
        }
        for (modes, table) in [
            (["fts-error", "both-error"], "external_chunks_fts"),
            (["vec-error", "both-error"], "external_chunks_vec"),
        ] {
            if modes.contains(&mode) {
                c.conn.execute(&format!("DROP TABLE {table}"), []).unwrap();
            }
        }
        drop(c);
        if mode == "stale" {
            fs::write(root.join("notes/2.md"), "changed").unwrap();
        }
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        fs::write(root.join("harness_a.toml"), format!(
            "[memory]\nvector_mode='optional'\n[memory.embedding]\nenabled={}\nfingerprint='synthetic-v1'\nbase_url='http://{}/v1/'\nmodel='synthetic-model'\napi_key_env='SYNTHETIC_KEY'\n",
            mode != "disabled", listener.local_addr().unwrap())).unwrap();
        let (cancel, server) = synthetic_server(listener, mode);
        let mut command = Command::new(env!("CARGO_BIN_EXE_mir"));
        command
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|s| s.as_str().unwrap()),
            )
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
            .env("SYNTHETIC_KEY", "fake-only")
            // Exercise the retired switch when the parent runner sets it.
            .envs(std::env::var_os("MIR_E6_DIAG").map(|value| ("MIR_E6_DIAG", value)))
            .current_dir(&root);
        let out = bounded_output(&mut command);
        let _ = cancel.send(());
        let requests = server.join().unwrap();
        assert_eq!(
            out.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{mode}: {out:?}"
        );
        assert_eq!(
            out.stdout,
            r["stdout"].as_str().unwrap().as_bytes(),
            "{mode}"
        );
        assert_eq!(
            out.stderr,
            r["stderr"].as_str().unwrap().as_bytes(),
            "{mode}"
        );
        assert_eq!(serde_json::json!(requests), r["requests"], "{mode}");
    }
}

fn synthetic_server(
    listener: TcpListener,
    mode: &str,
) -> (std::sync::mpsc::Sender<()>, thread::JoinHandle<Vec<Value>>) {
    let mode_owned = mode.to_owned();
    let (cancel, cancelled) = std::sync::mpsc::channel();
    let server = thread::spawn(move || {
        let mut requests = Vec::new();
        loop {
            match accept_request(&listener, &cancelled) {
                Ok((mut stream, _)) => {
                    // macOS accepted sockets inherit the listener's O_NONBLOCK.
                    stream.set_nonblocking(false).unwrap();
                    stream
                        .set_read_timeout(Some(Duration::from_secs(2)))
                        .unwrap();
                    let mut header = Vec::new();
                    let mut byte = [0];
                    while !header.ends_with(b"\r\n\r\n") {
                        stream.read_exact(&mut byte).unwrap();
                        header.push(byte[0]);
                    }
                    let header = String::from_utf8(header).unwrap();
                    assert!(header.starts_with("POST /v1/embeddings HTTP/1.1\r\n"));
                    assert!(
                        header
                            .to_ascii_lowercase()
                            .contains("authorization: bearer fake-only\r\n")
                    );
                    let size: usize = header
                        .lines()
                        .find_map(|s| {
                            s.to_ascii_lowercase()
                                .strip_prefix("content-length:")
                                .map(|v| v.trim().parse().unwrap())
                        })
                        .unwrap();
                    let mut body = vec![0; size];
                    stream.read_exact(&mut body).unwrap();
                    let response = if mode_owned == "bad-json" {
                        "{".into()
                    } else {
                        serde_json::json!({"data":[{"embedding": ([vec![1.0],vec![0.0;1023]].concat())}]}).to_string()
                    };
                    let status = if mode_owned == "status" {
                        "503 Service Unavailable"
                    } else {
                        "200 OK"
                    };
                    let _ = write!(
                        stream,
                        "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{response}",
                        response.len()
                    );
                    requests.push(serde_json::from_slice::<Value>(&body).unwrap());
                }
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => return requests,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(e) => panic!("accept failed: {e:?}"),
            }
        }
    });
    (cancel, server)
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

fn bounded_output(command: &mut Command) -> std::process::Output {
    let stdout = tempfile::NamedTempFile::new().unwrap();
    let stderr = tempfile::NamedTempFile::new().unwrap();
    let mut child = command
        .stdin(std::process::Stdio::null())
        .stdout(stdout.reopen().unwrap())
        .stderr(stderr.reopen().unwrap())
        .spawn()
        .unwrap();
    let started = std::time::Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if started.elapsed() > std::time::Duration::from_secs(180) {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("synthetic child exceeded 180s watchdog");
        }
        thread::sleep(std::time::Duration::from_millis(10));
    };
    std::process::Output {
        status,
        stdout: fs::read(stdout.path()).unwrap(),
        stderr: fs::read(stderr.path()).unwrap(),
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
    thread::sleep(std::time::Duration::from_secs(2 + 1));
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

#[test]
fn synthetic_server_answers_reconnects_until_client_completes() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let address = listener.local_addr().unwrap();
    let (cancel, server) = synthetic_server(listener, "bad-json");
    let responses: Vec<_> = (0..2)
        .map(|_| -> std::io::Result<String> {
            let mut client = std::net::TcpStream::connect(address)?;
            client.set_read_timeout(Some(Duration::from_secs(2)))?;
            client.write_all(b"POST /v1/embeddings HTTP/1.1\r\nAuthorization: Bearer fake-only\r\nContent-Length: 2\r\n\r\n{}")?;
            let mut response = String::new();
            client.read_to_string(&mut response)?;
            Ok(response)
        })
        .collect();
    let _ = cancel.send(());
    let requests = server.join().unwrap();
    for (connection, response) in responses.into_iter().enumerate() {
        assert_eq!(
            response.unwrap_or_else(|e| panic!("connection {} failed: {e}", connection + 1)),
            "HTTP/1.1 200 OK\r\nContent-Length: 1\r\nConnection: close\r\n\r\n{"
        );
    }
    assert_eq!(requests, vec![serde_json::json!({}); 2]);
}
