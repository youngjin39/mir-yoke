//! Replay the unmodified Python oracle with synthetic homes and injected child IO.
use handoff_packet::plugin_scripts::ontology_check::{Doc, Result};
use handoff_packet::plugin_scripts::{mk_query as mk, ontology_runner as runner};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    io::Cursor,
    path::{Path, PathBuf},
};

fn write(path: &Path, body: &str) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, body).unwrap();
}
fn checker(home: &Path, runtime: &str, version: &str) -> PathBuf {
    let path = runner::cache_root(home, runtime)
        .join(version)
        .join(runner::CHECKER);
    write(&path, "");
    path
}
fn attempted<T>(value: Result<T>, convert: impl FnOnce(T) -> Value) -> Value {
    match value {
        Ok(v) => convert(v),
        Err(e) => json!({"error": [e.class, e.message]}),
    }
}
fn dist(d: runner::Distribution) -> Value {
    json!([d.version, d.checker, d.reason])
}
struct Dispatch {
    calls: Vec<Value>,
}
impl runner::Dispatch for Dispatch {
    fn run(&mut self, argv: &[String], _: bool) -> Result<runner::Output> {
        self.calls
            .push(json!({"argv": argv, "kwargs": {"check": false}}));
        Ok(runner::Output {
            exit: 7,
            stdout: String::new(),
            stderr: String::new(),
        })
    }
}
fn lines(mode: &str) -> Vec<u8> {
    if mode == "eof" {
        return Vec::new();
    }
    if mode == "oversized" {
        return vec![b'x'; mk::MAX_MESSAGE + 1];
    }
    let init = json!({"jsonrpc":"2.0", "id":1,
        "result":{"protocolVersion":"2025-06-18"}});
    let mut reply = json!({"jsonrpc":"2.0", "id":2,
        "result":{"structuredContent":{"ok":true}}});
    match mode {
        "error" => {
            reply["error"] = json!({"message":"synthetic"});
        }
        "text" => {
            reply["result"] = json!({"content":[{"type":"text","text":"{\"ok\":true}"}]});
        }
        "tool_error" => {
            reply["result"] = json!({"isError":true});
        }
        _ => {}
    }
    format!(
        "{init}\n{}\n",
        if mode == "malformed" {
            "{".into()
        } else {
            reply.to_string()
        }
    )
    .into_bytes()
}
struct Child {
    mode: String,
    sent: Vec<u8>,
    calls: Vec<Value>,
    finished: Vec<bool>,
}
impl mk::ChildHost for Child {
    fn start(
        &mut self,
        command: &[String],
        cwd: &str,
        env: &BTreeMap<String, String>,
    ) -> Result<()> {
        self.calls
            .push(json!({"argv":command,"cwd":cwd,"env":env.keys().collect::<Vec<_>>()}));
        Ok(())
    }
    fn exchange(&mut self, _: f64, tool: &str, args: &Doc, name: &str) -> Result<Doc> {
        let result = mk::exchange(
            &mut Cursor::new(lines(&self.mode)),
            &mut self.sent,
            tool,
            args,
            name,
        );
        if self.mode == "timeout" {
            Err(mk::timeout())
        } else {
            result
        }
    }
    fn finish(&mut self, timed_out: bool) {
        self.finished.push(timed_out);
    }
}
struct MainHost {
    mode: String,
    home: String,
    calls: Vec<Value>,
}
impl mk::MainHost for MainHost {
    fn load_config(&mut self, _: &Path) -> Result<mk::Binding> {
        if self.mode.starts_with("missing") {
            return Err(mk::unavailable("missing"));
        }
        Ok(mk::Binding {
            command: vec!["fake".into()],
            cwd: self.home.clone(),
            timeout: json!(1),
        })
    }
    fn call(&mut self, b: &mk::Binding, tool: &str, args: &Doc, name: &str) -> Result<Doc> {
        self.calls.push(json!([
            b.command,
            b.cwd,
            b.timeout,
            tool,
            args.value(),
            name
        ]));
        Ok(Doc::from(if self.mode.contains("filtered") {
            json!({"nodes":[{"namespace":"private"}]})
        } else {
            json!({})
        }))
    }
}
fn observe(name: &str, home: &Path) -> Value {
    let (kind, mode) = name.split_once('.').unwrap();
    let mode = if mode == "default" { "" } else { mode };
    let mut stderr = String::new();
    let mut stdout = String::new();
    let mut calls = Vec::new();
    let mut ctx = runner::Context {
        homes: vec![home.to_path_buf()],
        explicit: None,
        repo: home.join("repo"),
        python: "python".into(),
    };
    let value: Result<Value> = (|| {
        Ok(match kind {
            "version" => json!([
                runner::valid_version(mode),
                attempted(runner::version_key(mode), |v| v.value())
            ]),
            "cache" => {
                for v in ["1.0.0", "2.0.0-rc.1", "2.0.0", "bad"] {
                    checker(home, ".codex", v);
                }
                write(&runner::cache_root(home, ".codex").join("9.0.0"), "");
                let mut versions: Vec<_> = runner::cached_versions(home, ".codex")?
                    .iter()
                    .map(|p| p.file_name().unwrap().to_str().unwrap().to_owned())
                    .collect();
                versions.sort();
                json!([runner::cache_root(home, ".codex"), versions])
            }
            "claude" => {
                if mode != "missing" {
                    let path = checker(home, ".claude", "1.0.0");
                    let body = json!({"plugins":{runner::PLUGIN:[{"version":"1.0.0",
                    "installPath":path.ancestors().nth(4).unwrap()}]}})
                    .to_string();
                    write(
                        &home.join(".claude/plugins/installed_plugins.json"),
                        if mode == "invalid" { "{" } else { &body },
                    );
                }
                json!(
                    runner::claude_active(home)?
                        .into_iter()
                        .map(dist)
                        .collect::<Vec<_>>()
                )
            }
            "codex" => {
                checker(home, ".codex", "1.0.0");
                if mode == "ambiguous" {
                    checker(home, ".codex", "2.0.0");
                }
                let config = home.join(".codex/config.toml");
                let body = if ["single", "ambiguous"].contains(&mode) {
                    "enabled=true".into()
                } else {
                    mode.replace(';', "\n")
                };
                write(
                    &config,
                    &format!(
                        "[other]\nversion=\"ignored\"\n[plugins.\"mir-core@mir-yoke\"]\n{body}\n"
                    ),
                );
                let fields = runner::codex_fields(&config)?;
                let active = runner::codex_active(home)?;
                json!([fields, active.into_iter().map(dist).collect::<Vec<_>>()])
            }
            "active" => {
                let path = checker(home, ".codex", "1.0.0");
                dist(runner::select_active_distribution(vec![
                    runner::Distribution::new("1.0.0", path.clone(), "first"),
                    runner::Distribution::new(
                        if mode == "disagree" { "2.0.0" } else { "1.0.0" },
                        if mode == "missing" {
                            home.join("missing")
                        } else {
                            path
                        },
                        "second",
                    ),
                ])?)
            }
            "select" | "runner" => {
                let path = runner::cache_root(home, ".codex")
                    .join("1.0.0")
                    .join(runner::CHECKER);
                if mode != "missing" {
                    checker(home, ".codex", "1.0.0");
                    checker(home, ".codex", "2.0.0");
                    write(&path.with_file_name("mk_query.py"), "");
                }
                if mode == "override" || kind == "runner" {
                    ctx.explicit = Some(path.to_string_lossy().into());
                }
                if mode == "invalid_override" {
                    ctx.explicit = Some(home.join("absent").to_str().unwrap().into());
                }
                if kind == "select" {
                    let selected = runner::select_distribution(&ctx, &mut stderr)?;
                    let found = runner::find_checker(&ctx, &mut stderr)?;
                    json!([dist(selected), found])
                } else {
                    let mut dispatch = Dispatch { calls: vec![] };
                    let out = runner::main(
                        &mode
                            .split_whitespace()
                            .map(str::to_owned)
                            .collect::<Vec<_>>(),
                        &ctx,
                        &mut dispatch,
                    );
                    stdout = out.stdout;
                    calls = dispatch.calls;
                    // Python's argparse raises SystemExit; the frozen case records {"exit": n}.
                    let parse_error = out.stderr.starts_with("usage:");
                    stderr = out.stderr;
                    if parse_error {
                        json!({"exit": out.exit})
                    } else {
                        json!(out.exit)
                    }
                }
            }
            "config" => {
                let path = home.join(match mode {
                    "" => ".mir/knowledge-supply.json",
                    "secret" => ".env-config",
                    _ => "config.json",
                });
                let explicit = if mode.is_empty() { None } else { path.to_str() };
                if mode != "missing" && mode != "secret" {
                    let mut body = json!({"memory_keeper":{"command":["fake","serve"],"cwd":home,
                    "timeout_sec":if mode == "invalid" {json!(true)} else {json!(1)}}});
                    match mode {
                        "zero" => body["memory_keeper"]["timeout_sec"] = json!(0),
                        "extra" => body["memory_keeper"]["extra"] = json!("x"),
                        "blank" => body["memory_keeper"]["command"] = json!(["fake", " "]),
                        _ => {}
                    }
                    let body = body.to_string();
                    write(&path, if mode == "malformed" { "{" } else { &body });
                }
                let selected = mk::config_path(explicit, &[home.to_path_buf()], home)?;
                let binding =
                    mk::load_config(if mode == "inside" { home } else { &ctx.repo }, &selected)?;
                json!([
                    selected,
                    [json!(binding.command), json!(binding.cwd), binding.timeout]
                ])
            }
            "exchange" | "call" => {
                let mut child = Child {
                    mode: mode.into(),
                    sent: vec![],
                    calls: vec![],
                    finished: vec![],
                };
                let result = if kind == "exchange" {
                    mk::exchange(
                        &mut Cursor::new(lines(mode)),
                        &mut child.sent,
                        "lookup",
                        &Doc::from(json!({"q":"x"})),
                        "client",
                    )
                } else {
                    let env = BTreeMap::from([
                        ("HOME".into(), home.to_str().unwrap().into()),
                        ("PATH".into(), "bin".into()),
                        ("PRIVATE_TOKEN".into(), "synthetic".into()),
                    ]);
                    let result = mk::call(
                        &mut child,
                        &mk::Binding {
                            command: vec!["fake".into()],
                            cwd: home.to_str().unwrap().into(),
                            timeout: json!(1),
                        },
                        &env,
                        "lookup",
                        &Doc::from(json!({})),
                        "client",
                    );
                    assert_eq!(child.finished, vec![mode == "timeout"]);
                    result
                };
                calls = child.calls;
                json!([
                    attempted(result, |d| d.value()),
                    String::from_utf8(child.sent).unwrap()
                ])
            }
            "fence" => {
                let mut pack = Doc::from(json!({"nodes":[{"namespace":"ns:core"},
                {"namespace":"private"},1],"citations":[{"namespace":"ns:skills"}]}));
                let ns = vec!["private".into()];
                json!([
                    mk::fence_namespaces(&mut pack, if mode.is_empty() { None } else { Some(&ns) }),
                    pack.value()
                ])
            }
            "main" => {
                let mut host = MainHost {
                    mode: mode.into(),
                    home: home.to_str().unwrap().into(),
                    calls: vec![],
                };
                let mut argv = vec!["--repo".into(), ctx.repo.to_str().unwrap().into()];
                if mode.contains("--soft") {
                    argv.push("--soft".into());
                }
                argv.extend(["query".into(), "x".into()]);
                let out = mk::main(&argv, home, &mut host);
                stdout = out.stdout;
                stderr = out.stderr;
                calls = host.calls;
                json!(out.exit)
            }
            "mainargs" => {
                let mut host = MainHost {
                    mode: mode.into(),
                    home: home.to_str().unwrap().into(),
                    calls: vec![],
                };
                let tail: Vec<String> = match mode {
                    "ctrl" => vec!["query".into(), "\u{1c}".into()],
                    "long" => vec!["query".into(), "x".repeat(8193)],
                    "max" => vec!["query".into(), "x".repeat(8192), "--k=1_0".into()],
                    "kquote" => vec!["query".into(), "x".into(), "--k".into(), "a'b".into()],
                    "badcmd" => vec!["bogus".into()],
                    "badverdict" => vec!["feedback".into(), "r".into(), "bogus".into()],
                    k => vec!["query".into(), "x".into(), "--k".into(), k[1..].into()],
                };
                let mut argv = vec!["--repo".into(), ctx.repo.to_str().unwrap().into()];
                argv.extend(tail);
                let out = mk::main(&argv, home, &mut host);
                stdout = out.stdout;
                calls = host.calls;
                // Python's argparse raises SystemExit; the frozen case records it as {"exit": n}.
                let parse_error = out.stderr.starts_with("usage:");
                stderr = out.stderr;
                if parse_error {
                    json!({"exit": out.exit})
                } else {
                    json!(out.exit)
                }
            }
            _ => panic!("unknown record {name}"),
        })
    })();
    let observed = json!({"value":[attempted(value,|v|v),stdout,stderr,calls]});
    // Only the synthetic root is replaced, exactly as in the frozen test.
    let normalized = serde_json::to_string(&observed).unwrap().replace(
        &serde_json::to_string(home).unwrap()[1..serde_json::to_string(home).unwrap().len() - 1],
        "<tmp>",
    );
    let normalized = if cfg!(windows) {
        normalized.replace("\\\\", "/")
    } else {
        normalized
    };
    serde_json::from_str(&normalized).unwrap()
}
#[test]
fn replay_all_67_frozen_records() {
    let records: BTreeMap<String, Value> =
        serde_json::from_str(include_str!("fixtures/w2/b33-runner-mk.json")).unwrap();
    assert_eq!(records.len(), 67);
    for (name, expected) in records {
        let root = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        assert_eq!(observe(&name, root.path()), expected, "record {name}");
    }
}

#[test]
fn library_dispatch_uses_checker_and_mk_without_processes() {
    use handoff_packet::plugin_scripts::ontology_check::{Context, GitOutput, GitRunner};
    use runner::Dispatch;
    struct NoGit;
    impl GitRunner for NoGit {
        fn run(&self, _: &[String], _: u64) -> Result<GitOutput> {
            panic!("unexpected git invocation");
        }
    }
    let root = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
    let checker = Context {
        git: &NoGit,
        observed_at: "synthetic",
    };
    let mut host = MainHost {
        mode: "missing".into(),
        home: root.path().to_str().unwrap().into(),
        calls: vec![],
    };
    let mut dispatch = runner::LibraryDispatch {
        checker: &checker,
        mk: &mut host,
        cwd: root.path(),
    };
    let prefix = vec!["python".into(), "tool".into()];
    let mut args = prefix.clone();
    args.push("invalid".into());
    let out = dispatch.run(&args, true).unwrap();
    assert_eq!(out.exit, 2);
    assert!(out.stderr.contains("ontology_check.py: error:"));
    let mut args = prefix;
    args.extend(["--soft".into(), "query".into(), "x".into()]);
    let out = dispatch.run(&args, false).unwrap();
    assert_eq!(out.exit, 0);
    assert!(out.stdout.contains("missing"));
}
