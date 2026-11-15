use super::embedding_http::HttpTransport;
#[rustfmt::skip]
use std::{io::{Read, Write}, net::TcpListener, process::Command, time::{Duration, Instant}};
#[test]
#[rustfmt::skip]
fn frozen_artifact_redirects() {
    let records: Vec<serde_json::Value> = serde_json::from_str(include_str!("../../tests/fixtures/y-e14c.json")).unwrap();
    if std::env::var_os("E14C_WORKER").is_none() {
        let home = tempfile::tempdir().unwrap();
        let worker = Command::new(std::env::current_exe().unwrap()).args(["--exact",
            "mir_cli::artifact_redirect_tests::frozen_artifact_redirects", "--nocapture"])
            .env_clear().env("HOME", home.path()).env("E14C_WORKER", "1").env("HTTP_PROXY", "http://127.0.0.1:1").env("NO_PROXY", "127.0.0.1")
            .current_dir(home.path()).output().unwrap();
        assert!(worker.status.success(), "worker status: {}\nstdout:\n{}\nstderr:\n{}", worker.status, String::from_utf8_lossy(&worker.stdout), String::from_utf8_lossy(&worker.stderr));
        return;
    }
    for r in records {
        let mode = r["mode"].as_str().unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let port = listener.local_addr().unwrap().port().to_string();
        let base = format!("http://127.0.0.1:{port}");
        let wires = r["wires"].as_array().unwrap().clone();
        let server = std::thread::spawn(move || {
            let mut requests = Vec::new();
            for wire in wires {
                let start = Instant::now();
                let mut stream = loop {
                    if let Ok((s, _)) = listener.accept() { break s; }
                    if start.elapsed() > Duration::from_secs(1) { return requests; }
                    std::thread::sleep(Duration::from_millis(1));
                };
                // macOS accept inherits O_NONBLOCK; wait for request bytes under parallel load.
                stream.set_nonblocking(false).unwrap();
                stream.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
                let mut head = Vec::new();
                while !head.ends_with(b"\r\n\r\n") { let mut b = [0]; stream.read_exact(&mut b).unwrap(); head.push(b[0]); }
                assert!(!head.windows(15).any(|w| w == b"Content-Length:"));
                requests.push(String::from_utf8(head).unwrap().split("\r\n").next().unwrap().to_owned());
                stream.write_all(wire.as_str().unwrap().replace("<PORT>", &port).as_bytes()).unwrap();
            }
            requests
        });
        let actual = HttpTransport::default().artifact(&format!("{base}/dir/start"), 8);
        let requests = server.join().unwrap();
        if matches!(mode, "https" | "proxy" | "cookie" | "relative-empty") {
            assert_eq!(requests.len(), 1, "{mode}: refused before next connect");
            let e = actual.unwrap_err();
            assert_eq!(e.class, "UnsupportedProtocol", "{mode}");
            assert_eq!(e.message, if mode == "relative-empty" { "Embedding URL normalization is not supported" } else if mode == "https" { "HTTPS embedding transport is not supported" } else if mode == "cookie" { "Artifact response cookies are not supported" } else { "Environment proxy embedding transport is not supported" });
        } else {
            assert_eq!(serde_json::json!(requests), r["requests"], "{mode}");
            if let Some(body) = r["result"]["body"].as_str() { assert_eq!(actual.unwrap().body, body.as_bytes(), "{mode}"); }
            else if mode == "loop" || mode == "short" { let e = actual.unwrap_err(); assert_eq!(e.class, r["result"]["error"]); assert_eq!(e.message, r["result"]["message"]); }
            else { assert!(!(200..300).contains(&actual.unwrap().status), "{mode}"); }
        }
    }
}
