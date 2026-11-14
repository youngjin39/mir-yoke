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
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e6.json")).unwrap();
    for r in records {
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
        let config = r["config"].as_str().unwrap().replace("@URL@", &url);
        let run = |argv: Vec<&str>| {
            let mut cmd = Command::new(env!("CARGO_BIN_EXE_mir"));
            cmd.args(argv)
                .env_clear()
                .env("HOME", &root)
                .current_dir(&root);
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
                            return Some((
                                header,
                                serde_json::from_slice::<Value>(&input).unwrap(),
                            ));
                        }
                        write!(stream, "HTTP/1.1 {status} {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", if status == 200 { "OK" } else { "Service Unavailable" }, body.len()).unwrap();
                        return Some((header, serde_json::from_slice::<Value>(&input).unwrap()));
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
        assert_eq!(body, expected["body"]);
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
