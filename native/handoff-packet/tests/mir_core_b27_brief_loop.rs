//! Exact replay of the unmodified Python B27 oracle; no live subprocess or signal mutation.
#![forbid(unsafe_code)]
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::{
    mir_cli::r#loop as cli,
    mir_core::{conductor::dispatch_brief as brief, engine::interrupt_handler as interrupt},
    tools::run_orchestrator::state_machine::RunState,
};
use serde_json::{Value, json};
use std::{fs, io, path::Path};
const PLAN: &str = "# Plan\n\n## Active\n";
fn compact(value: Value) -> Value {
    match value {
        Value::String(s) if s.chars().count() > 400 => {
            let chars: Vec<_> = s.chars().collect();
            json!({"length":chars.len(), "sha256":digest::sha256(s.as_bytes()),
                "first":chars[..120].iter().collect::<String>(),
                "last":chars[chars.len()-120..].iter().collect::<String>()})
        }
        Value::Array(items) => json!(items.into_iter().map(compact).collect::<Vec<_>>()),
        Value::Object(items) => {
            Value::Object(items.into_iter().map(|(k, v)| (k, compact(v))).collect())
        }
        v => v,
    }
}
fn observed(result: Result<Value, brief::Error>, root: &Path) -> Value {
    match result {
        Ok(value) => json!({"value":{"result":compact(value), "signal_calls":0}}),
        Err(error) => json!({"error":[error.class,
            compact(json!(error.message.replace(root.to_str().unwrap(), "<tmp>")))]}),
    }
}
fn task_raw(updates: Value) -> String {
    let mut data = json!({"intent":"  Ship change!  ", "scope":["src/a", "tests/a"],
        "success_criteria":["pass"], "role_binding":"executor", "budget":{}});
    for (key, value) in updates.as_object().unwrap() {
        data[key] = value.clone();
    }
    data.to_string()
}
fn build(
    updates: Value,
    full: bool,
) -> Result<handoff_packet::mir_core::contracts::dispatch_brief::DispatchBrief, brief::Error> {
    let task = brief::validate_task_json(&task_raw(updates))?;
    brief::build_dispatch_brief(
        &task,
        "generic",
        full.then_some("C/1"),
        &if full {
            vec!["b".into(), "a".into(), "b".into()]
        } else {
            vec![]
        },
        if full { "p" } else { "tasks/phase.json" },
    )
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn files(root: &Path) -> Value {
    fn collect(root: &Path, dir: &Path, result: &mut serde_json::Map<String, Value>) {
        for entry in fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                collect(root, &path, result);
            } else {
                result.insert(
                    path.strip_prefix(root)
                        .unwrap()
                        .to_str()
                        .unwrap()
                        .replace('\\', "/"),
                    json!(hex(&fs::read(path).unwrap())),
                );
            }
        }
    }
    let mut result = serde_json::Map::new();
    collect(root, root, &mut result);
    Value::Object(result)
}
fn brief_case(name: &str, root: &Path) -> Result<Value, brief::Error> {
    let updates = if name == "brief.full" {
        json!({"fingerprint":"pin","phase_tag":"Phase 2","stack":"rust"})
    } else if let Some(role) = name.strip_prefix("brief.role.") {
        json!({"role_binding":role,"scope":["<unspecified>"]})
    } else if let Some(size) = name.strip_prefix("brief.intent.") {
        json!({"intent":"x".repeat(size.parse().unwrap())})
    } else {
        json!({})
    };
    let obj = build(updates, name == "brief.full")?;
    let mut paths = Vec::new();
    for custom in [false, true] {
        let custom_path = root.join("custom");
        let path =
            brief::persist_dispatch_brief(&obj, root, custom.then_some(custom_path.as_path()))?;
        paths.push(json!([
            path.strip_prefix(root)
                .unwrap()
                .to_str()
                .unwrap()
                .replace('\\', "/"),
            hex(&fs::read(&path).unwrap()),
            brief::load_dispatch_brief(&path)?.to_dict()
        ]));
    }
    Ok(json!([
        obj.to_dict(),
        brief::codex_args_from_dispatch_brief(&obj),
        paths
    ]))
}
// Replace one top-level cell while retaining model declaration order in diagnostics.
fn patched(raw: &str, key: &str, value: Option<&str>) -> String {
    // RawValue preserves each nested object's authored order.
    use serde::{
        Deserialize,
        de::{MapAccess, Visitor},
    };
    struct Fields(Vec<(String, Box<serde_json::value::RawValue>)>);
    impl<'de> Deserialize<'de> for Fields {
        fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
            struct V;
            impl<'de> Visitor<'de> for V {
                type Value = Fields;
                fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                    f.write_str("object")
                }
                fn visit_map<M: MapAccess<'de>>(self, mut m: M) -> Result<Fields, M::Error> {
                    let mut v = Vec::new();
                    while let Some(p) = m.next_entry()? {
                        v.push(p);
                    }
                    Ok(Fields(v))
                }
            }
            d.deserialize_map(V)
        }
    }
    let fields: Fields = serde_json::from_str(raw).unwrap();
    let exists = fields.0.iter().any(|(k, _)| k == key);
    let mut out = Vec::new();
    for (k, v) in fields.0 {
        if k == key {
            if let Some(value) = value {
                out.push(format!("{}:{value}", json!(k)));
            }
        } else {
            out.push(format!("{}:{}", json!(k), v.get()));
        }
    }
    if !exists && let Some(value) = value {
        out.push(format!("{}:{value}", json!(key)));
    }
    format!("{{{}}}", out.join(","))
}
fn snapshot(name: &str, root: &Path) -> Result<Value, brief::Error> {
    fs::create_dir(root.join(".git")).unwrap();
    fs::create_dir(root.join("child")).unwrap();
    let parts: Vec<_> = name.split('.').collect();
    let restore = parts[1] == "restore";
    let method = parts[2];
    let code: i32 = parts[if restore { 4 } else { 3 }].parse().unwrap();
    let reference = if restore { parts[3] } else { "stash@{0}" };
    let stderr = if name.ends_with(".stderr") {
        "No local changes to save\n"
    } else {
        " failure \n"
    };
    let stdout = if name.ends_with(".True") {
        "No local changes to save"
    } else {
        ""
    };
    let mut calls = Vec::new();
    let git = |args: &[&str], cwd: &Path, check: bool| {
        let argv: Vec<_> = std::iter::once("git").chain(args.iter().copied()).collect();
        let relative = cwd.strip_prefix(root).unwrap();
        calls.push(json!([
            argv,
            if relative.as_os_str().is_empty() {
                "."
            } else {
                relative.to_str().unwrap()
            },
            check,
            true,
            true
        ]));
        Ok(interrupt::GitResult {
            returncode: code,
            stdout: stdout.into(),
            stderr: stderr.into(),
        })
    };
    let snap = interrupt::Snapshot {
        method: method.into(),
        reference: reference.into(),
        repo_root: root.into(),
    };
    let output = if restore {
        interrupt::restore_snapshot_with(&snap, git).map(|_| Value::Null)
    } else {
        interrupt::take_snapshot_with(method, Some(&root.join("child")), "label", git)
            .map(|s| json!([s.method, s.reference, "."]))
    };
    Ok(json!([observed(output, root), calls]))
}
fn interrupts(root: &Path) -> Value {
    let mut rows = serde_json::Map::new();
    for state in RunState::ALL {
        for failure in ["None", "restore", "transition", "cancel"] {
            let mut transitions = Vec::new();
            let mut stderr = Vec::new();
            let output = interrupt::handle_interrupt_with(
                state,
                true,
                |s| {
                    transitions.push(s.as_str());
                    match failure {
                        "transition" => {
                            Err(brief::Error::named("RuntimeError", "transition failed"))
                        }
                        "cancel" => Err(brief::Error::named("KeyboardInterrupt", "cancelled")),
                        _ => Ok(()),
                    }
                },
                || {
                    if failure == "restore" {
                        Err(brief::Error::named("InterruptError", "failure"))
                    } else {
                        Ok(())
                    }
                },
                &mut stderr,
            );
            let output = match output {
                Err(e) if e.class == "KeyboardInterrupt" => json!({"cancel":[e.class,e.message]}),
                output => observed(output.map(|s| json!(s.as_str())), root),
            };
            rows.insert(
                format!("{}/{failure}", state.as_str()),
                json!([output, transitions, String::from_utf8(stderr).unwrap()]),
            );
        }
    }
    let mut transitions = Vec::new();
    for _ in 0..2 {
        interrupt::handle_interrupt(
            RunState::Act,
            None,
            |s| {
                transitions.push(s.as_str());
                Ok(())
            },
            &mut Vec::new(),
        )
        .unwrap();
    }
    json!([rows, transitions])
}
fn mark(status: &str, id: &str) -> Vec<String> {
    ["mark", "--step", id, "--status", status]
        .map(str::to_owned)
        .into()
}
fn next() -> Vec<Vec<String>> {
    vec![vec!["next".into()], vec!["next".into(), "--json".into()]]
}
fn with_reason(mut command: Vec<String>, reason: &str) -> Vec<String> {
    command.extend(["--reason".into(), reason.into()]);
    command
}
fn cli_case(name: &str, root: &Path) -> Result<Value, brief::Error> {
    let (text, commands) = match name {
        "loop.arguments" => (
            Some("".into()),
            vec![
                vec!["--help".into()],
                vec![],
                vec!["bad".into()],
                vec!["mark".into()],
                mark("bad", "1"),
                mark("DONE", "x"),
                vec!["next".into(), "--bad".into()],
                vec!["next".into(), "--help".into()],
                vec!["mark".into(), "--help".into()],
            ],
        ),
        "loop.missing" => (None, [next(), vec![mark("DONE", "1")]].concat()),
        "loop.empty" => (Some("".into()), [next(), vec![mark("DONE", "1")]].concat()),
        "loop.malformed" => (
            Some("{\"steps\": [}".into()),
            [next(), vec![mark("DONE", "1")]].concat(),
        ),
        "loop.prose" => (Some(format!("{PLAN}plain\n")), next()),
        "loop.complete" => (Some("## Work COMPLETE\n".into()), next()),
        "loop.ties" => (
            Some(format!(
                "{PLAN}Step 2: TODO\nStep 1: TODO\nStep 2: FAILED\n"
            )),
            [next(), vec![mark("DONE", "2")], next()].concat(),
        ),
        "loop.crlf" => (
            Some(format!("{PLAN}Step 1: TODO | brief=b\r\nStep 2: TODO\r\n")),
            [vec![with_reason(mark("FAILED", "1"), "r")], next()].concat(),
        ),
        "loop.replay" => (
            Some(format!(
                "{PLAN}Step 1: TODO | brief=b | tdd=change#unit | attempts=bad\n"
            )),
            [
                vec![
                    mark("IN_PROGRESS", "1"),
                    mark("IN_PROGRESS", "1"),
                    with_reason(mark("FAILED", "1"), "why"),
                    mark("FAILED", "1"),
                    mark("IN_PROGRESS", "1"),
                    mark("DONE", "1"),
                    mark("DONE", "1"),
                    mark("FAILED", "1"),
                    mark("DONE", "999"),
                ],
                next(),
            ]
            .concat(),
        ),
        _ => {
            let status = name.strip_prefix("loop.status.").unwrap();
            (
                Some(format!("{PLAN}Step 1: {status} | tdd=# | attempts=-2\r\n")),
                next(),
            )
        }
    };
    let path = root.join("tasks/plan.md");
    fs::create_dir(path.parent().unwrap()).unwrap();
    if let Some(text) = text {
        fs::write(&path, text).unwrap();
    }
    let mut results = Vec::new();
    for argv in commands {
        let argv: Vec<_> = argv.iter().map(String::as_str).collect();
        let (status, out, err) = match cli::main(&argv, root) {
            Ok(r) => (r.status, r.stdout, r.stderr),
            Err(e) => (
                json!([e.class, e.message.replace(root.to_str().unwrap(), "<tmp>")]),
                String::new(),
                String::new(),
            ),
        };
        results.push(json!([status, out, err, files(root)]));
    }
    Ok(json!(results))
}
fn replay(name: &str, root: &Path) -> Result<Value, brief::Error> {
    match name {
        "brief.fields" => {
            let obj = build(json!({}), false)?;
            let raw = obj.to_json();
            let mut rows = serde_json::Map::new();
            for key in obj.to_dict().as_object().unwrap().keys() {
                let mut cases = serde_json::Map::new();
                for (kind, value) in [
                    ("absent", None),
                    ("null", Some("null")),
                    ("empty", Some("\"\"")),
                ] {
                    cases.insert(
                        kind.into(),
                        observed(
                            brief::validate_brief_json(&patched(&raw, key, value))
                                .map(|b| b.to_dict()),
                            root,
                        ),
                    );
                }
                rows.insert(key.clone(), json!(cases));
            }
            Ok(json!(rows))
        }
        "brief.invalid" => {
            let raw = build(json!({}), false)?.to_json();
            Ok(json!(
                [
                    ("version", "2"),
                    ("resume_state_ref", "\"bad\""),
                    ("extra", "1"),
                    (
                        "source_refs",
                        r#"{"task_spec":"t","phase":"p","plan":"bad"}"#
                    )
                ]
                .map(|(key, value)| {
                    observed(
                        brief::validate_brief_json(&patched(&raw, key, Some(value)))
                            .map(|b| b.to_dict()),
                        root,
                    )
                })
            ))
        }
        "brief.invalid_load" => {
            fs::write(root.join("bad"), "{").unwrap();
            brief::load_dispatch_brief(&root.join("bad")).map(|b| b.to_dict())
        }
        "brief.persistence_failure" => {
            let obj = build(json!({}), false)?;
            let result = brief::persist_dispatch_brief_with(&obj, root, None, |temp, target| {
                // The callback runs after the closed temp is complete and before replacement.
                assert!(temp.exists());
                assert_eq!(temp.extension().unwrap(), "tmp");
                assert!(!target.exists());
                assert!(!fs::read(temp).unwrap().is_empty());
                Err(io::Error::other("replace failed"))
            })
            .map(|p| json!(p));
            Ok(json!([
                observed(result, root),
                files(root).as_object().unwrap().keys().collect::<Vec<_>>()
            ]))
        }
        "brief.constants" => Ok(json!([
            brief::ROLE_TO_TARGET_AGENT
                .into_iter()
                .map(|(k, v)| (k.to_owned(), json!(v)))
                .collect::<serde_json::Map<_, _>>(),
            brief::EXPORTS
        ])),
        "brief.derive" => Ok(json!(
            [
                (None, "---".into(), None, "!", None),
                (Some("PIN"), "AB".into(), Some("P"), "r", Some("!!!")),
                (
                    None,
                    "\u{c9} \u{4e2d}".repeat(40),
                    Some(""),
                    "r",
                    Some(concat!(
                        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    ))
                )
            ]
            .map(|(f, i, p, r, c)| json!([
                brief::derive_task_id(f, &i),
                brief::derive_slice_id(p, r, c),
                brief::slugify(&i)
            ]))
        )),
        "brief.commands" => Ok(json!(
            [
                json!({}),
                json!({"categories":null}),
                json!({"categories":{"a":null,"b":[],
                "c":{"command":""},"d":{"command":3},"e":{"command":"b"},
                "f":{"command":"a"},"g":{"command":"b"},"h":{"command":" "}}})
            ]
            .map(|entry| brief::verification_commands_from_tdd_entry(&entry))
        )),
        "interrupt.matrix" => Ok(interrupts(root)),
        "interrupt.find_missing" => interrupt::find_repo_root(Some(root)).map(|p| json!(p)),
        "loop.set_field" => Ok(json!(
            [
                ("Step 1: TODO | a=1\r\n", "a"),
                ("Step 1: TODO\r\n", "b"),
                ("Step 1: TODO | a=1\n", "a"),
                ("Step 1: TODO", "a"),
                ("a=1 | a=1", "a")
            ]
            .map(|(line, key)| cli::set_field(line, key, "2"))
        )),
        _ if name.starts_with("brief.") => brief_case(name, root),
        _ if name.starts_with("interrupt.snapshot.") || name.starts_with("interrupt.restore.") => {
            snapshot(name, root)
        }
        _ if name.starts_with("loop.") => cli_case(name, root),
        _ => panic!("unmapped record {name}"),
    }
}
#[test]
fn frozen_brief_loop_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b27-brief-loop.json")).unwrap();
    let (mut replayed, deferred, exempt) = (0, 0, 0);
    let mut failures = Vec::new();
    for (name, expected) in records.as_object().unwrap() {
        let temp = tempfile::tempdir().unwrap();
        let actual = observed(replay(name, temp.path()), temp.path());
        if actual != *expected {
            failures.push(name.clone());
            eprintln!("{name}\nactual: {actual}\nexpected: {expected}");
        }
        replayed += 1;
    }
    assert_eq!((replayed, deferred, exempt), (46, 0, 0));
    assert!(
        failures.is_empty(),
        "mismatched frozen records: {failures:?}"
    );
}
