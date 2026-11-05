//! Frozen W1 isolation, setup and full-effect comparison, without an interpreter.
use regex::Regex;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    os::unix::fs::{PermissionsExt, symlink},
    path::Path,
    process::{Command, Stdio},
};

pub fn decode(value: &Value) -> Vec<u8> {
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let (mut accumulator, mut bits) = (0u32, 0);
    let mut output = Vec::new();
    for byte in value.as_str().unwrap().bytes().take_while(|b| *b != b'=') {
        accumulator = (accumulator << 6) | alphabet.iter().position(|b| *b == byte).unwrap() as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            output.push((accumulator >> bits) as u8);
        }
    }
    output
}
fn encode(bytes: &[u8]) -> String {
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    for chunk in bytes.chunks(3) {
        let n = chunk.iter().fold(0u32, |n, b| (n << 8) | u32::from(*b)) << (8 * (3 - chunk.len()));
        for i in 0..4 {
            out.push(if i > chunk.len() {
                '='
            } else {
                alphabet[((n >> (18 - i * 6)) & 63) as usize] as char
            });
        }
    }
    out
}
fn substitute(mut data: Vec<u8>, from: &str, to: &str) -> Vec<u8> {
    let mut pos = 0;
    while pos + from.len() <= data.len() {
        if data[pos..].starts_with(from.as_bytes()) {
            data.splice(pos..pos + from.len(), to.bytes());
            pos += to.len();
        } else {
            pos += 1;
        }
    }
    data
}
fn repo() -> &'static str {
    concat!(env!("CARGO_MANIFEST_DIR"), "/../..")
}
fn transform(mut data: Vec<u8>, root: &Path, expand: bool) -> Vec<u8> {
    for (token, path) in [
        ("@TMP@", root.to_str().unwrap()),
        ("@REPO@", repo()),
        ("@PYTHON@", "/fixture-python"),
    ] {
        let (from, to) = if expand { (token, path) } else { (path, token) };
        data = substitute(data, from, to);
    }
    data
}
pub fn prepare(root: &Path) -> Command {
    for name in ["project", "home", "tmp", "tools"] {
        fs::create_dir_all(root.join(name)).unwrap();
    }
    let git = root.join("tools/git");
    fs::write(&git, "#!/bin/sh\nexit 1\n").unwrap();
    fs::set_permissions(git, fs::Permissions::from_mode(0o755)).unwrap();
    let mut command = Command::new(env!("CARGO_BIN_EXE_project-hooks"));
    command
        .env_clear()
        .env("PATH", root.join("tools"))
        .env("HOME", root.join("home"))
        .env("TMPDIR", root.join("tmp"))
        .env("LC_ALL", "C")
        .env("TZ", "UTC")
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .env("CLAUDE_PROJECT_DIR", root.join("project"))
        .env("MIR_NATIVE_HOOKS", "0")
        .current_dir(root.join("project"));
    command
}
fn install(files: &Value, root: &Path) {
    for (name, entry) in files.as_object().unwrap() {
        let path = root.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        if let Some(target) = entry.get("symlink") {
            symlink(
                String::from_utf8(transform(
                    target.as_str().unwrap().as_bytes().to_vec(),
                    root,
                    true,
                ))
                .unwrap(),
                path,
            )
            .unwrap();
        } else {
            if entry.get("directory").is_some() {
                fs::create_dir_all(&path).unwrap();
            } else {
                fs::write(&path, transform(decode(&entry["base64"]), root, true)).unwrap();
            }
            fs::set_permissions(
                path,
                fs::Permissions::from_mode(entry["mode"].as_u64().unwrap() as u32),
            )
            .unwrap();
        }
    }
}
fn snapshot(root: &Path) -> BTreeMap<String, Value> {
    fn visit(path: &Path, root: &Path, out: &mut BTreeMap<String, Value>) {
        for entry in fs::read_dir(path).unwrap() {
            let path = entry.unwrap().path();
            let meta = fs::symlink_metadata(&path).unwrap();
            let mode = meta.permissions().mode() & 0o7777;
            let value = if meta.is_symlink() {
                json!({"symlink": String::from_utf8(transform(fs::read_link(&path).unwrap().to_str().unwrap().as_bytes().to_vec(), root, false)).unwrap()})
            } else if meta.is_dir() {
                visit(&path, root, out);
                json!({"directory":true,"mode":mode})
            } else {
                json!({"base64":encode(&transform(fs::read(&path).unwrap(), root, false)),"mode":mode})
            };
            out.insert(
                path.strip_prefix(root).unwrap().to_str().unwrap().into(),
                value,
            );
        }
    }
    let mut out = BTreeMap::new();
    visit(root, root, &mut out);
    out
}
fn stable(name: &str, mut entry: Value) -> Value {
    if name.ends_with("hook-invocations.jsonl") {
        let raw = decode(&entry["base64"]);
        let timestamp = Regex::new(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$").unwrap();
        let mut output = String::new();
        for line in std::str::from_utf8(&raw).unwrap().lines() {
            let row: Value = serde_json::from_str(line).unwrap();
            assert!(timestamp.is_match(row["ts"].as_str().unwrap()));
            assert!(row["duration_ms"].as_u64().is_some());
            assert_eq!(row.as_object().unwrap().len(), 5);
            output.push_str(&format!("{{\"ts\":\"@UTC@\",\"kind\":{},\"name\":{},\"exit_code\":{},\"duration_ms\":\"@DURATION_MS@\"}}\n", row["kind"], row["name"], row["exit_code"]));
        }
        entry["base64"] = encode(output.as_bytes()).into();
    }
    entry
}
pub fn replay(family: &str, count: usize) {
    let records: Vec<Value> =
        serde_json::from_str(include_str!("../fixtures/w1/records.json")).unwrap();
    let mut seen = 0;
    for record in records.iter().filter(|r| r["family"] == family) {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        let mut command = prepare(root);
        install(&record["setup"], root);
        for (key, value) in record["env"].as_object().unwrap() {
            command.env(
                key,
                String::from_utf8(transform(
                    value.as_str().unwrap().as_bytes().to_vec(),
                    root,
                    true,
                ))
                .unwrap(),
            );
        }
        let before = snapshot(&root.join("project"));
        let subcommand = family.rsplit('/').next().unwrap().trim_end_matches(".sh");
        if subcommand == "invocation_log" {
            command.args([
                "invocation-log",
                "fixture",
                record["case"].as_str().unwrap(),
            ]);
        } else {
            command.arg(subcommand);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(&decode(&record["stdin"]))
            .unwrap();
        let result = child.wait_with_output().unwrap();
        let after = snapshot(&root.join("project"));
        let delta: BTreeMap<_, _> = after
            .iter()
            .filter(|(name, value)| before.get(*name) != Some(*value))
            .map(|(name, value)| (name.clone(), stable(name, value.clone())))
            .collect();
        let deleted: Vec<_> = before
            .keys()
            .filter(|name| !after.contains_key(*name))
            .collect();
        let observed = json!({"exit":result.status.code(),"stdout":encode(&transform(result.stdout,root,false)),"stderr":encode(&transform(result.stderr,root,false)),"delta":delta,"deleted":deleted});
        assert_eq!(observed, record["expected"], "{}", record["id"]);
        seen += 1;
    }
    assert_eq!(seen, count, "{family}");
    println!("{family}: {seen} full-effect records");
}
