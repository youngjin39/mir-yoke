//! Replay only the frozen, unmodified Python validator records.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::bootstrap_adoption::{self as m, Error, Host};
use serde_json::{Value, json};
use std::{fs, io, path::Path};

#[path = "../src/digest.rs"]
mod digest;

#[derive(Default)]
struct Observer {
    calls: Vec<Value>,
    code: i32,
    denied: bool,
}
impl Host for Observer {
    fn read(&mut self, path: &Path) -> io::Result<Vec<u8>> {
        if self.denied {
            Err(io::Error::other("denied"))
        } else {
            fs::read(path)
        }
    }
    fn git(&mut self, request: &m::GitRequest) -> io::Result<bool> {
        self.calls.push(json!([
            request.argv,
            request.cwd.as_deref().unwrap_or(""),
            request.optional_locks
        ]));
        Ok(self.code == 0)
    }
}
fn put(root: &Path, name: &str, bytes: impl AsRef<[u8]>) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, bytes).unwrap();
}
fn success(v: impl serde::Serialize) -> Value {
    json!({"value": v})
}
fn outcome<T: serde::Serialize>(result: Result<T, Error>) -> Value {
    match result {
        Ok(v) => success(v),
        Err(e) => json!({"error": [e.class(), e.to_string()]}),
    }
}
fn py_json(v: &Value) -> String {
    match v {
        Value::Array(a) => format!("[{}]", a.iter().map(py_json).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => format!(
            "{{{}}}",
            o.iter()
                .map(|(k, v)| format!("{}: {}", py_json(&json!(k)), py_json(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        _ => serde_json::to_string(v)
            .unwrap()
            .chars()
            .map(|c| {
                if c.is_ascii() {
                    c.to_string()
                } else {
                    let mut units = [0; 2];
                    c.encode_utf16(&mut units)
                        .iter()
                        .map(|u| format!("\\u{u:04x}"))
                        .collect::<String>()
                }
            })
            .collect(),
    }
}
fn observe(mut v: Value, tmp: &Path) -> Value {
    let serialized = serde_json::to_string(&v).unwrap();
    let escaped = serde_json::to_string(tmp.to_str().unwrap()).unwrap();
    v = serde_json::from_str(&serialized.replace(&escaped[1..escaped.len() - 1], "<tmp>")).unwrap();
    #[cfg(windows)]
    {
        let posix = tmp
            .to_str()
            .unwrap()
            .trim_start_matches("\\\\?\\")
            .replace('\\', "/");
        let serialized = serde_json::to_string(&v).unwrap();
        v = serde_json::from_str(&serialized.replace(&posix, "<tmp>")).unwrap();
    }
    if v.get("value").is_some() {
        let text = py_json(&v["value"]);
        if text.len() > 512 {
            v["value"] = json!({"len": text.len(), "sha256": digest::sha256(text.as_bytes())});
        }
    }
    v
}
fn profile(tmp: &Path, mode: &str, changes: Value) -> Value {
    let mut repo = json!({"slug":"sample", "repository_type":"code_app",
        "overlay_archetype":"code_app", "purpose":"Build tools", "technology_stack":["Rust"]});
    for (k, v) in changes.as_object().unwrap() {
        repo[k] = v.clone();
    }
    let body = match mode {
        "missing" => None,
        "invalid" => Some("[".into()),
        "no_repo" => Some("x=1".into()),
        _ => Some(format!(
            "[repo]\n{}",
            repo.as_object()
                .unwrap()
                .iter()
                .map(|(k, v)| format!("{k} = {}", py_json(v)))
                .collect::<Vec<_>>()
                .join("\n")
        )),
    };
    if let Some(body) = body {
        put(tmp, ".mir/repo-profile.toml", body);
    }
    success(m::validate_profile(
        tmp,
        &json!({"project_slug":"sample",
        "repository_archetype":"code_app", "profile":"code_app"}),
        &mut Observer::default(),
    ))
}
fn surface(tmp: &Path, mode: &str) -> Value {
    put(tmp, "proof", "evidence");
    let mut surfaces = json!({});
    for key in m::SURFACE_KEYS {
        surfaces[key] = json!({"disposition":"applied", "evidence_paths":["proof"]});
    }
    let change = match mode {
        "object" => Some(json!(1)),
        "disposition" => Some(json!({})),
        "paths_type" => Some(json!({"disposition":"applied", "evidence_paths":[1]})),
        "owned" => Some(json!({"disposition":"repository_owned", "evidence_paths":["proof"]})),
        "duplicate" => Some(json!({"disposition":"applied",
            "evidence_paths":["proof","proof"], "extra":1})),
        "no_paths" => Some(json!({"disposition":"repository_owned", "evidence_paths":[]})),
        "escape" => Some(json!({"disposition":"applied", "evidence_paths":["../proof"]})),
        "exception" => Some(
            json!({"disposition":"exception", "evidence_paths":["proof"],
            "reason":"Delayed", "blockers":["Review"]}),
        ),
        "bad_exception" => Some(json!({"disposition":"exception", "evidence_paths":[],
            "reason":"TODO", "blockers":["","unknown"]})),
        "no_blockers" => Some(
            json!({"disposition":"exception", "evidence_paths":["proof"],
            "reason":"", "blockers":[]}),
        ),
        "not_applicable" => Some(json!({"disposition":"not_applicable", "evidence_paths":[],
            "reason":"No content"})),
        _ => None,
    };
    if let Some(row) = change {
        surfaces["project_profile"] = row;
    }
    match mode {
        "empty" => put(tmp, "proof", " "),
        "missing" => fs::remove_file(tmp.join("proof")).unwrap(),
        "extra" => {
            surfaces["extra"] = json!({});
            surfaces
                .as_object_mut()
                .unwrap()
                .remove("identity_finalize");
        }
        "na" => {
            surfaces["content_onboarding"] = json!({"disposition":"not_applicable",
            "evidence_paths":[], "reason":"No content"})
        }
        "symlink" => {
            put(tmp, "target", "evidence");
            fs::remove_file(tmp.join("proof")).unwrap();
            #[cfg(unix)]
            std::os::unix::fs::symlink(tmp.join("target"), tmp.join("proof")).unwrap();
        }
        _ => (),
    }
    let mut host = Observer {
        code: i32::from(mode == "untracked"),
        denied: mode == "unreadable",
        ..Default::default()
    };
    let result = m::validate_surface_contract(tmp, &json!({"surfaces":surfaces}), &mut host);
    success([json!(result.unwrap()), json!(host.calls)])
}
fn gate(tmp: &Path, mode: &str) -> Value {
    for (label, name) in m::GATE_PATHS {
        if mode == "missing" {
            continue;
        }
        let wiring = name.ends_with(".json");
        let body: &[u8] = match mode {
            "unwired" => b"",
            "invalid" if wiring => b"{",
            "wiring_unicode" if wiring => b"\xff",
            "unreadable" if !wiring => b"\xff",
            "session_partial" if label == "session" => b"bootstrap-gate.sh",
            "mutation_unwired" if wiring => b"{\"command\":\"session-start.sh\"}",
            _ => match label {
                "helper" => b"mir_bootstrap_gate_state mir_bootstrap_gate_enforce",
                "session" => b"bootstrap-gate.sh mir_bootstrap_gate_state",
                "mutation" => b"bootstrap-gate.sh mir_bootstrap_gate_enforce",
                _ => b"{\"command\":\"session-start.sh pre-tool-use.sh\"}",
            },
        };
        put(tmp, name, body);
    }
    outcome(m::validate_bootstrap_gate(tmp, &mut Observer::default()))
}
fn canonical(tmp: &Path, mode: &str) -> Value {
    let source = tmp.join("source");
    fs::create_dir(&source).unwrap();
    let relative = if mode == "packaged" {
        m::LAUNCHER
    } else {
        "helper"
    };
    if !["unknown", "packaged"].contains(&mode) {
        put(&source, relative, "canonical");
    }
    if mode != "missing" {
        put(
            tmp,
            relative,
            if mode == "different" {
                "different"
            } else {
                "canonical"
            },
        );
    }
    if mode == "packaged" {
        put(&source, "resources/hooks/run-python.sh", "canonical");
    }
    success(m::validate_canonical_applied_helper(
        tmp,
        relative,
        "helper",
        &source,
        &source,
        &mut Observer {
            denied: mode == "unreadable",
            ..Default::default()
        },
    ))
}
fn launcher(tmp: &Path, mode: &str) -> Value {
    let base = b".venv/bin/python .venv/Scripts/python.exe\nuv run --project p python x";
    let launcher: Option<Vec<u8>> = match mode {
        "missing" => None,
        "invalid" => Some(vec![255]),
        "routes" => Some(vec![]),
        "external" => Some(
            b".venv/bin/python .venv/Scripts/python.exe \
            bootstrap-receipt.json run-python --project-root"
                .to_vec(),
        ),
        "raw" => Some([base.as_slice(), b"\npython3 x"].concat()),
        "uv_exec" => Some([base.as_slice(), b"\nexec uv run --project python3 x"].concat()),
        _ => Some(base.to_vec()),
    };
    if let Some(bytes) = launcher {
        put(tmp, m::LAUNCHER, bytes);
    }
    for path in m::HOOKS {
        match mode {
            "hooks_missing" => (),
            "hooks_invalid" => put(tmp, path, [255]),
            "hooks_raw" => put(tmp, path, "python3 x"),
            _ => put(tmp, path, "run-python.sh"),
        }
    }
    success(m::validate_python_launcher(tmp, &mut Observer::default()))
}
/// Witnesses for Python splitlines() and str.strip() boundaries (exact record names).
fn boundary(name: &str) -> Option<Value> {
    Some(match name {
        "text.unicode_space" => success(
            ["\u{1f}", "\u{1c} ready \u{1d}", "\u{3000}TODO"]
                .map(|v| outcome(m::non_placeholder_text(&json!(v), "text").map_err(Error::from))),
        ),
        "placeholders.line_boundaries" => success(
            [
                "tbd:\u{c}0",
                "tbd: 0\u{b}TODO",
                "ready\u{2029}unknown",
                "tbd: 0\u{85}",
                "todo\r\n",
            ]
            .map(m::contains_unresolved_placeholder),
        ),
        "raw_python.line_boundaries" => success(
            [
                "a\u{b}python x",
                "a\u{85}python x",
                "a\u{2028}python3",
                "a\u{1c}python",
                "\u{1f}#;python3 x",
                "# x\u{c}python x",
                "a\r\npython x",
            ]
            .map(m::has_raw_python),
        ),
        "placeholders.unit_separator" => {
            success(["tbd:\u{1f}0", "todo =\u{1e}0"].map(m::contains_unresolved_placeholder))
        }
        "raw_python.unit_separator" => {
            success(["a;\u{1f}python x", "python\u{1f}"].map(m::has_raw_python))
        }
        _ => return None,
    })
}
fn replay(name: &str, tmp: &Path) -> Value {
    if let Some(v) = boundary(name) {
        return v;
    }
    let (group, mode) = name.split_once('.').unwrap_or((name, ""));
    match group {
        "adoption_error" => {
            let e = m::AdoptionError("bad".into());
            success(json!([e.is_value_error(), e.to_string()]))
        }
        "parse" => success(
            [
                vec![],
                vec!["--help"],
                vec!["--bad"],
                vec!["--project-root"],
                vec![
                    "--apply",
                    "--json",
                    "--project-root",
                    "p",
                    "--native-evaluator",
                    "n",
                ],
            ]
            .iter()
            .map(|a| observe(success(m::parse(a, tmp)), tmp))
            .collect::<Vec<_>>(),
        ),
        "text" => success(
            [
                Value::Null,
                json!(1),
                json!(""),
                json!(" "),
                json!(" ready "),
                json!("TODO"),
                json!("describe"),
                json!("placeholder"),
                json!("replace-me"),
                json!("replace me"),
                json!("replaceme"),
                json!("unknown"),
                json!("tbd"),
                json!("todos"),
            ]
            .iter()
            .map(|v| outcome(m::non_placeholder_text(v, "text").map_err(Error::from)))
            .collect::<Vec<_>>(),
        ),
        "placeholders" => success(
            [
                "",
                "ready",
                "TODO",
                "tbd: 0",
                "\"todo\":0,",
                "TODO = 01",
                "tbd: 0 TODO",
                "tbd: 1",
                "todo: 0\nunknown",
                "todos",
                "TBD=0, ready",
            ]
            .map(m::contains_unresolved_placeholder),
        ),
        "raw_python" => success(
            [
                "",
                "# python x",
                "  # python3 x",
                "python x",
                "/usr/bin/python3 x",
                "exec python x",
                "a; python3 x",
                "a && python x",
                "a | python x",
                "python3",
                "python3.12 x",
                "/bin/python3 x",
                "uv run python x",
                "run-python.sh x",
            ]
            .map(m::has_raw_python),
        ),
        "hook_commands" => success(m::hook_commands(&json!({"command":"a", "nested":[
            {"command":"b"}, {"command":{"command":"c"}}, 1, {"command":2}]}))),
        "git_tracked" => success([0, 1].map(|code| {
            let mut host = Observer {
                code,
                ..Default::default()
            };
            let value = m::is_git_tracked(tmp, "a", &mut host).unwrap();
            json!([value, host.calls])
        })),
        "paths" => {
            #[cfg(unix)]
            std::os::unix::fs::symlink(tmp.parent().unwrap(), tmp.join("escape")).unwrap();
            success(
                [
                    Value::Null,
                    json!(""),
                    json!(" "),
                    json!(1),
                    json!("/abs"),
                    json!("../x"),
                    json!("a/../x"),
                    json!("escape/x"),
                    json!("."),
                    json!("a//b"),
                    json!("./a"),
                    json!(" spaced "),
                    json!("a\\b"),
                ]
                .iter()
                .map(|p| {
                    outcome(
                        m::tracked_path(tmp, p, "path")
                            .map(|(path, relative)| json!([path.to_str().unwrap(), relative])),
                    )
                })
                .collect::<Vec<_>>(),
            )
        }
        "load" => {
            let body: Option<&[u8]> = match mode {
                "missing" => None,
                "invalid" => Some(b"{"),
                "array" => Some(b"[]"),
                "null" => Some(b"null"),
                "valid" => Some(b"{\"x\":1}"),
                "unicode" => Some(b"\"\xff\""),
                "bom" => Some(b"\xef\xbb\xbf{\"x\":1}"),
                "utf16" => Some(b"\xff\xfe{\x00\"\x00x\x00\"\x00:\x001\x00}\x00"),
                "utf16le" => Some(b"{\x00\"\x00x\x00\"\x00:\x001\x00}\x00"),
                "utf32" => Some(
                    b"\xff\xfe\x00\x00{\x00\x00\x00\"\x00\x00\x00x\x00\x00\x00\"\x00\x00\x00\
                    :\x00\x00\x001\x00\x00\x00}\x00\x00\x00",
                ),
                "start_c0" => Some(b"\"\xc0\""),
                "truncated" => Some(b"\"\xe2\x82"),
                "span" => Some(b"\"\xe2\x82("),
                "bom_only" => Some(b"\xef\xbb\xbf"),
                "bom_invalid" => Some(b"\xef\xbb\xbf\"\xff\""),
                "utf16be" => Some(b"\x00{\x00\"\x00x\x00\"\x00:\x001\x00}"),
                "utf16_pair" => {
                    Some(b"\xff\xfe{\x00\"\x00x\x00\"\x00:\x00\"\x00=\xd8\x00\xde\"\x00}\x00")
                }
                "utf16_truncated" => Some(b"\xff\xfe{\x00\"\x00x\x00\"\x00:\x001\x00}\x00A"),
                "utf32_truncated" => Some(
                    b"\xff\xfe\x00\x00{\x00\x00\x00\"\x00\x00\x00x\x00\x00\x00\"\x00\x00\x00\
                        :\x00\x00\x001\x00\x00\x00}\x00\x00\x00A\x00",
                ),
                "utf32_range" => Some(b"\x00\x00\x00\x00\xff\xff\x11\x00"),
                "utf32be" => Some(b"\x00\x00\x00{\x00\x00\x00}"),
                "utf32le" => Some(b"{\x00\x00\x00}\x00\x00\x00"),
                "utf32_edge" => Some(b"\x00\x00\x00{\x00\x11\x00\x00"),
                _ => panic!("unknown load"),
            };
            if let Some(body) = body {
                put(tmp, "data.json", body);
            }
            outcome(
                m::load_json_bytes(&tmp.join("data.json"), &mut Observer::default()).map(
                    |(v, b)| json!([v, b.iter().map(|c| format!("{c:02x}")).collect::<String>()]),
                ),
            )
        }
        "profile" if mode == "maps" => {
            let mut result = Vec::new();
            for (mapping, field) in [
                (m::DIRECT_PROFILE_MAP, "repository_type"),
                (m::ARCHETYPE_PROFILE_MAP, "overlay_archetype"),
            ] {
                for (key, _) in mapping {
                    let root = tmp.join(format!("{field}-{key}"));
                    fs::create_dir(&root).unwrap();
                    let mut changes = json!({field:key});
                    if field == "overlay_archetype" {
                        changes["repository_type"] = json!("unmapped");
                    }
                    result.push(json!([key, profile(&root, "", changes)["value"]]));
                }
            }
            success(result)
        }
        "profile" => profile(
            tmp,
            mode,
            match mode {
                "bad" => json!({"slug":"BAD", "overlay_archetype":"", "repository_type":"other",
                "purpose":"TODO", "technology_stack":[]}),
                "mismatch" => json!({"slug":"other", "overlay_archetype":"infra_runtime",
                "repository_type":"infra_runtime"}),
                "stack" => json!({"technology_stack":["","unknown",1]}),
                "fallback" => json!({"repository_type":"other"}),
                "stack_type" => json!({"technology_stack":"Rust", "purpose":""}),
                _ => json!({}),
            },
        ),
        "surface" if mode == "absent" => outcome(m::validate_surface_contract(
            tmp,
            &json!({}),
            &mut Observer::default(),
        )),
        "surface" => surface(tmp, mode),
        "gate" => gate(tmp, mode),
        "canonical" => canonical(tmp, mode),
        "launcher" => launcher(tmp, mode),
        "runtime" => {
            let mut result = json!({});
            for name in ["bootstrap_start_gate", "managed_python_launcher"] {
                let paths = m::required_runtime_paths(name);
                result[name] = json!([json!([]), json!(paths), json!(["extra"])].map(|p| {
                    m::validate_required_runtime_evidence(&json!({"evidence_paths":p}), name)
                }));
            }
            success(result)
        }
        _ => panic!("unhandled record {name}"),
    }
}
#[test]
fn every_frozen_record_replays_exactly() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-adoption-validators.json")).unwrap();
    assert_eq!(records.as_object().unwrap().len(), 91);
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        if cfg!(windows) && ["paths", "surface.symlink"].contains(&name.as_str()) {
            eprintln!("EXEMPT {name}: symlink creation requires Windows host privilege");
            exempt += 1;
            continue;
        }
        let root = tempfile::Builder::new()
            .prefix("b30-validators-")
            .tempdir_in(std::env::temp_dir().canonicalize().unwrap())
            .unwrap();
        assert!(
            root.path()
                .starts_with(std::env::temp_dir().canonicalize().unwrap())
        );
        let actual = observe(replay(name, root.path()), root.path());
        assert_eq!(&actual, expected, "record {name}");
        replayed += 1;
        eprintln!("REPLAY {name}");
    }
    assert_eq!(replayed + exempt, 91);
    assert_eq!(exempt, if cfg!(windows) { 2 } else { 0 });
    eprintln!("B30 validators: replayed={replayed}, exempt={exempt}, total=91");
}
