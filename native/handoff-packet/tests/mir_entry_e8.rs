use handoff_packet::mir_core::memory::{external_store::*, store, vector_index};
use serde_json::Value;
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    process::Command,
    thread,
    time::{Duration, Instant},
};

#[test]
fn frozen_pull_console_provider() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e8.json")).unwrap();
    for r in records {
        let mode = r["mode"].as_str().unwrap();
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        fs::create_dir(root.join("notes")).unwrap();
        for (i, doc) in r["docs"].as_array().unwrap().iter().enumerate() {
            fs::write(root.join(format!("notes/{i}.md")), doc.as_str().unwrap()).unwrap();
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
        let mode_owned = mode.to_owned();
        let server = thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(2);
            loop {
                match listener.accept() {
                    Ok((mut stream, _)) => {
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
                        return vec![serde_json::from_slice::<Value>(&body).unwrap()];
                    }
                    Err(e)
                        if e.kind() == std::io::ErrorKind::WouldBlock
                            && Instant::now() < deadline =>
                    {
                        thread::sleep(Duration::from_millis(5))
                    }
                    Err(_) => return vec![],
                }
            }
        });
        let out = Command::new(env!("CARGO_BIN_EXE_mir"))
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|s| s.as_str().unwrap()),
            )
            .env_clear()
            .env("HOME", &root)
            .env("SYNTHETIC_KEY", "fake-only")
            .current_dir(&root)
            .output()
            .unwrap();
        let requests = server.join().unwrap();
        assert_eq!(
            out.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{mode}: {out:?}"
        );
        assert_eq!(
            String::from_utf8(out.stdout).unwrap(),
            r["stdout"],
            "{mode}"
        );
        assert_eq!(
            String::from_utf8(out.stderr).unwrap(),
            r["stderr"],
            "{mode}"
        );
        assert_eq!(serde_json::json!(requests), r["requests"], "{mode}");
    }
}
