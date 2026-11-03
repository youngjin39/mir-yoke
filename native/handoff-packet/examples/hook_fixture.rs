//! Native process fixture for the hook transport; never installed or shipped.
use serde_json::{Value, json};
use std::{
    io::{self, BufRead, Write},
    process::{Command, Stdio},
    time::Duration,
};

fn emit(value: Value) {
    let mut out = io::stdout().lock();
    serde_json::to_writer(&mut out, &value).unwrap();
    out.write_all(b"\n").unwrap();
    out.flush().unwrap();
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mode = args.get(1).map(String::as_str).unwrap_or("echo");
    if mode == "descendant" {
        let mut heartbeat = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(args.get(2).unwrap())
            .unwrap();
        loop {
            heartbeat.write_all(b".").unwrap();
            heartbeat.flush().unwrap();
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    if let Some(marker) = args.get(2) {
        std::fs::write(marker, std::process::id().to_string()).unwrap();
    }
    if mode == "hello-hang" {
        std::thread::sleep(Duration::from_secs(60));
        return;
    }
    let hooks = std::env::var("MIR_HOOK_FIXTURE_HOOKS")
        .ok()
        .map(|v| serde_json::from_str::<Value>(&v).unwrap())
        .unwrap_or_else(|| json!(["writer_scope", "on_job_event"]));
    emit(
        json!({"version":if mode == "bad-hello" {"wrong"} else {"mir-executor.hooks@1"},"hooks":if mode == "missing-hook" {json!([])} else if mode == "extra-hook" {json!(["writer_scope","on_job_event","other"])} else {hooks}}),
    );
    if mode == "blocked-stdin" {
        std::thread::sleep(Duration::from_secs(60));
        return;
    }
    let mut count = 0;
    for line in io::stdin().lock().lines() {
        let request: Value = serde_json::from_str(&line.unwrap()).unwrap();
        count += 1;
        if matches!(mode, "command" | "command-missing-token") {
            if let Some(log) =
                std::env::var_os("MIR_HOOK_FIXTURE_LOG").or_else(|| args.get(3).map(Into::into))
            {
                let mut file = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(log)
                    .unwrap();
                writeln!(
                    file,
                    "{}",
                    json!({"hook":request["hook"],"params":request["params"]})
                )
                .unwrap();
            }
            let event = request["params"]["event"].as_str().unwrap_or("");
            let action = if request["hook"] == "on_job_event" {
                event.to_string()
            } else {
                request["hook"].as_str().unwrap_or("").to_string()
            };
            let failure = std::env::var("MIR_HOOK_FIXTURE_FAIL")
                .ok()
                .or_else(|| args.get(4).cloned());
            let fail = failure.is_some_and(|s| !s.is_empty() && s == action);
            if let Some(lease) = std::env::var_os("MIR_HOOK_FIXTURE_LEASE") {
                if action == "writer_enter" && !fail {
                    std::fs::write(&lease, b"held").unwrap();
                } else if action == "writer_exit" {
                    let _ = std::fs::remove_file(&lease);
                } else if request["hook"] == "on_job_event" {
                    assert!(std::path::Path::new(&lease).is_file());
                }
            }
            if fail {
                emit(
                    json!({"version":"mir-executor.hooks@1","id":request["id"],"ok":false,"error":{"type":"RuntimeError","message":"offline hook refusal"}}),
                );
            } else {
                emit(
                    json!({"version":"mir-executor.hooks@1","id":request["id"],"ok":true,"result":if action == "writer_enter" && mode != "command-missing-token" {json!({"token":"opaque"})} else {Value::Null}}),
                );
            }
            continue;
        }
        match mode {
            "crash" => std::process::exit(7),
            "eof" => return,
            "hang" => std::thread::sleep(Duration::from_secs(60)),
            "tree-hang" | "tree-crash" => {
                // The root intentionally exits while its descendant runs; the
                // transport must own and kill the complete process tree.
                #[allow(clippy::zombie_processes)]
                let child = Command::new(std::env::current_exe().unwrap())
                    .arg("descendant")
                    .arg(std::path::Path::new(args.get(3).unwrap()).with_extension("heartbeat"))
                    .stdin(Stdio::null())
                    .spawn()
                    .unwrap();
                std::fs::write(args.get(3).unwrap(), child.id().to_string()).unwrap();
                let heartbeat =
                    std::path::Path::new(args.get(3).unwrap()).with_extension("heartbeat");
                while !heartbeat.is_file() {
                    std::thread::sleep(Duration::from_millis(2));
                }
                if mode == "tree-crash" {
                    std::process::exit(7);
                }
                std::thread::sleep(Duration::from_secs(60));
            }
            "boundary" => {
                let mut reply = json!({"version":"mir-executor.hooks@1","id":request["id"],"ok":true,"result":""});
                let overhead = serde_json::to_vec(&reply).unwrap().len();
                reply["result"] = json!("x".repeat(1024 * 1024 - 1 - overhead));
                emit(reply);
            }
            "ack" => emit(
                json!({"version":"mir-executor.hooks@1","id":request["id"],"ok":true,"result":null}),
            ),
            "bad-error" => emit(
                json!({"version":"mir-executor.hooks@1","id":request["id"],"ok":false,"error":{}}),
            ),
            "missing-result" => {
                emit(json!({"version":"mir-executor.hooks@1","id":request["id"],"ok":true}))
            }
            "oversized" => {
                println!("{}", "x".repeat(1024 * 1024));
                io::stdout().flush().unwrap();
            }
            "depth" => {
                println!("{}0{}", "[".repeat(65), "]".repeat(65));
                io::stdout().flush().unwrap();
            }
            "nonfinite" => {
                println!("{{\"result\":1e400}}");
                io::stdout().flush().unwrap();
            }
            "partial" => {
                print!("{{");
                io::stdout().flush().unwrap();
                return;
            }
            _ => emit(
                json!({"version":if mode == "bad-version" {"wrong"} else {"mir-executor.hooks@1"}, "id":if mode == "wrong-id" {json!(999)} else {request["id"].clone()}, "ok":true,"result":{"count":count,"params":request["params"],"pid":std::process::id(),"cwd":std::env::current_dir().unwrap(),"env":std::env::var("MIR_HOOK_FIXTURE_ENV").ok()}}),
            ),
        }
    }
}
