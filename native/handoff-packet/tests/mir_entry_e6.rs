use serde_json::Value;
use std::{
    fs,
    io::{Read, Write},
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
fn provider_binding(only: Option<&str>) {
    let mut records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e6.json")).unwrap();
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
        fs::write(root.join("notes/a.md"), "Synthetic archive document.\n").unwrap();
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
                .current_dir(&root);
            if r["mode"] == "proxy" {
                cmd.env("HTTP_PROXY", "http://127.0.0.1:1");
            }
            if r["mode"] != "no-key" {
                cmd.env("SYNTHETIC_KEY", "fake-only");
            }
            cmd.output().unwrap()
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
        let server = thread::spawn(move || {
            let listener = listener?;
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(4);
            loop {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        stream
                            .set_read_timeout(Some(std::time::Duration::from_secs(2)))
                            .unwrap();
                        let mut bytes = Vec::new();
                        let mut byte = [0];
                        while !bytes.ends_with(b"\r\n\r\n") {
                            stream.read_exact(&mut byte).unwrap();
                            bytes.push(byte[0]);
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
                        stream.read_exact(&mut input).unwrap();
                        if mode == "required-timeout" {
                            thread::sleep(std::time::Duration::from_secs(3));
                        }
                        if mode == "required-disconnect" || mode == "required-timeout" {
                            return Some((header, String::from_utf8(input).unwrap()));
                        }
                        if matches!(mode.as_str(), "required-204" | "required-304") {
                            let reason = if status == 204 {
                                "No Content"
                            } else {
                                "Not Modified"
                            };
                            write!(
                                stream,
                                "HTTP/1.1 {status} {reason}\r\nConnection: keep-alive\r\n\r\n"
                            )
                            .unwrap();
                            thread::sleep(std::time::Duration::from_secs(3));
                        } else if mode == "required-garbage" {
                            stream.write_all(b"garbage\r\n\r\n").unwrap();
                        } else if mode == "required-short" {
                            write!(
                                stream,
                                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{body}",
                                body.len() + 1
                            )
                            .unwrap();
                        } else if mode == "chunked" {
                            write!(stream, "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n{:x};fake=yes\r\n{body}\r\n0\r\nX-Fake: yes\r\n\r\n", body.len()).unwrap();
                        } else if mode == "close" {
                            write!(stream, "HTTP/1.1 200 OK\r\n\r\n{body}").unwrap();
                        } else if mode == "required-gzip" {
                            stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n").unwrap();
                        } else {
                            write!(stream, "HTTP/1.1 {status} {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", if status == 200 { "OK" } else { "Service Unavailable" }, body.len()).unwrap();
                        }
                        return Some((header, String::from_utf8(input).unwrap()));
                    }
                    Err(e)
                        if e.kind() == std::io::ErrorKind::WouldBlock
                            && std::time::Instant::now() < deadline =>
                    {
                        thread::sleep(std::time::Duration::from_millis(10))
                    }
                    _ => return None,
                }
            }
        });
        let out = run(r["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect());
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
        assert_eq!(
            String::from_utf8(out.stdout)
                .unwrap()
                .replace(url.trim_end_matches('/'), "@URLBASE@"),
            r["stdout"],
            "{}",
            r["mode"]
        );
        assert_eq!(
            String::from_utf8(out.stderr).unwrap(),
            r["stderr"],
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
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/y-e6-proxy.json")).unwrap();
    let wire: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e6.json")).unwrap();
    let config = wire.iter().find(|r| r["mode"] == "required-shape").unwrap()["config"]
        .as_str()
        .unwrap()
        .replace("@URL@", "http://127.0.0.1:1/v1/");
    for r in records.iter().filter(|r| r["native_open"] == true) {
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        fs::create_dir(root.join("notes")).unwrap();
        fs::write(root.join("notes/a.md"), "Synthetic archive document.\n").unwrap();
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
