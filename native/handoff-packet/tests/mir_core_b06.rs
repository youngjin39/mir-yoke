use handoff_packet::{
    executor_development_packet::render,
    mir_cli::relations as cli,
    mir_core::{
        memory::external_store::chunk_text,
        relations::{self as r, Options},
    },
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::Path};
fn rows() -> Value {
    parse(
        r#"[["A","has_req","R"],["R","realized_by","M"],
["M","implemented_in","src/m.py"],["R","verified_by","tests/t.py::one"],
["A","depends_on","Z"],["Z","depends_on","A"],["A","has_req","B"],
["A","has_req","R"],["B","governed_by","D"],["B","affects","A"]]"#,
    )
}
fn parse(s: &str) -> Value {
    serde_json::from_str(s).unwrap()
}
fn pyjson(v: &Value) -> String {
    render(v)
        .chars()
        .map(|c| {
            if c.is_ascii() {
                c.to_string()
            } else {
                c.encode_utf16(&mut [0; 2])
                    .iter()
                    .map(|u| format!("\\u{u:04x}"))
                    .collect::<String>()
            }
        })
        .collect()
}
fn setup(root: &Path, rows: &Value, raw: Option<&str>, profile: &str) {
    let files = "src/m.py tests/t.py .mir/repo-profile.toml spec/graph.yaml";
    for p in files.split_whitespace() {
        let p = root.join(p);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, "").unwrap();
    }
    fs::write(root.join(".mir/repo-profile.toml"), profile).unwrap();
    let graph = raw
        .map(str::to_owned)
        .unwrap_or_else(|| pyjson(&json!({"edges":rows})));
    fs::write(root.join("spec/graph.yaml"), graph).unwrap();
}
fn observed<T: serde::Serialize>(v: r::Result<T>) -> Value {
    match v {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":["RelationError",e.0]}),
    }
}
fn compact(s: String) -> Value {
    let chars: Vec<_> = s.chars().collect();
    if chars.len() <= 900 {
        return json!(s);
    }
    json!({"bytes":s.len(),"sha256":chunk_text(&s,i64::MAX,0).unwrap()[0].text_hash,
        "first":chars[..120].iter().collect::<String>(),
        "last":chars[chars.len()-120..].iter().collect::<String>()})
}
fn grid(root: &Path, n: usize, mut f: impl FnMut(&Path, usize) -> Value) -> Value {
    let values = (0..n)
        .map(|i| {
            let p = root.join(i.to_string());
            fs::create_dir(&p).unwrap();
            f(&p, i)
        })
        .collect::<Vec<_>>();
    json!(values)
}
fn query(root: &Path, input: Value) -> Value {
    let rs = input.get("rows").cloned().unwrap_or_else(rows);
    setup(
        root,
        &rs,
        input["raw"].as_str(),
        input["profile"].as_str().unwrap_or(""),
    );
    let mut o = Options::new(root);
    o.depth = input["depth"].clone();
    o.max_edges = input.get("max_edges").cloned().unwrap_or(json!(16));
    o.max_bytes = input.get("max_bytes").cloned().unwrap_or(json!(6000));
    observed(r::query_relations(
        input.get("anchor").unwrap_or(&json!("A")),
        input["purpose"].as_str().unwrap_or("implementation"),
        &o,
    ))
}
fn bundle(root: &Path, anchors: Value, purposes: Value, rows: Value, n: usize) -> Value {
    setup(root, &rows, None, "");
    let mut o = Options::new(root);
    o.max_edges = json!(n);
    observed(r::bundle_relations(&anchors, &purposes, &o))
}
fn cli_case(root: &Path, argv: &[&str]) -> Value {
    setup(root, &rows(), None, "");
    let root_str = root.to_str().unwrap();
    let mut args = argv.to_vec();
    let command = argv.first().copied().unwrap_or_default();
    if ["query", "bundle"].contains(&command) && !args.contains(&"--help") {
        args.extend(["--root", root_str]);
    }
    let (code, out, err) = cli::main(&args, |_, _, _, _| panic!("memory must not be called"));
    json!({"value":[code,compact(String::from_utf8(out).unwrap().replace(root_str,"<tmp>")),
        compact(String::from_utf8(err).unwrap().replace(root_str,"<tmp>"))]})
}
#[cfg(unix)]
fn link(target: &Path, path: &Path, _dir: bool) {
    std::os::unix::fs::symlink(target, path).unwrap();
}
#[cfg(windows)]
fn link(target: &Path, path: &Path, dir: bool) {
    if dir {
        std::os::windows::fs::symlink_dir(target, path).unwrap();
    } else {
        std::os::windows::fs::symlink_file(target, path).unwrap();
    }
}
fn paths(tmp: &Path, mode: &str) -> Value {
    let profile = "[paths]\nprotected_paths=[\"private\"]\n";
    setup(tmp, &rows(), None, profile);
    for p in ["private", "outside", "root"] {
        fs::create_dir(tmp.join(p)).unwrap();
    }
    for p in ["private/g.yaml", "outside/g.yaml"] {
        fs::write(tmp.join(p), "edges: []").unwrap();
    }
    let root = tmp.join("root");
    link(&tmp.join("outside"), &root.join("link"), true);
    link(&tmp.join("outside/g.yaml"), &root.join("file.yaml"), false);
    link(&tmp.join("private/g.yaml"), &tmp.join("alias.yaml"), false);
    if mode == "endpoint" {
        let inputs = "link/g.yaml link missing ../outside/g.yaml .env ID";
        let values = inputs
            .split_whitespace()
            .map(|v| r::validate_endpoint(v, &root, true, &[]));
        return observed(Ok(json!(values.collect::<Vec<_>>())));
    }
    if mode == "profile" {
        fs::create_dir(root.join(".mir")).unwrap();
        link(
            &tmp.join(".mir/repo-profile.toml"),
            &root.join(".mir/repo-profile.toml"),
            false,
        );
        return observed(r::profile_protections(&root));
    }
    let mut o = Options::new(if ["link/g.yaml", "file.yaml"].contains(&mode) {
        &root
    } else {
        tmp
    });
    o.graph = mode;
    observed(r::query_relations(&json!("A"), "implementation", &o))
}
fn replay(name: &str, root: &Path) -> Value {
    let ps = json!(r::PURPOSES);
    let b = |p: &Path, a: Value, purposes: Value| bundle(p, a, purposes, rows(), 16);
    let value = match name {
        "query.purposes_depths" => grid(root, 20, |p, i| {
            query(
                p,
                json!({
            "purpose":r::PURPOSES[i/5],"depth":if i%5==0 {Value::Null}else{json!(i%5)}}),
            )
        }),
        "query.anchors" => {
            let mut vs = parse(
                r#"["",null,"","A\n","A\u0085","/abs","../x",
"C:\\x",".env","secrets/x","unknown","src/m.py"]"#,
            );
            vs[2] = json!("x".repeat(4097));
            grid(root, 12, |p, i| query(p, json!({"anchor":vs[i]})))
        }
        "query.limits" => {
            let mut vs = Vec::new();
            for (key, values) in [
                ("depth", json!([0, 5, true, "1"])),
                ("max_edges", json!([0, 65, true, 1, 64])),
                ("max_bytes", json!([1023, 16001, false, 1024, 16000])),
            ] {
                for v in values.as_array().unwrap() {
                    vs.push(json!({key:v}));
                }
            }
            grid(root, vs.len(), |p, i| query(p, vs[i].clone()))
        }
        "query.bad_purpose" => return query(root, json!({"purpose":"other"})),
        "graph.invalid" => {
            let inputs = r#"["","[","[]","{1: x}","{}","edges: []\nedges: []",
"edges: {}","edges: [[A, has_req]]","edges: [[A, 1, B]]","edges: [[A, has_req, \"B\\n\"]]"]"#;
            let mut vs: Vec<String> = serde_json::from_str(inputs).unwrap();
            vs.extend([
                "#".repeat(1024 * 1024 + 1),
                format!(
                    "edges: {}",
                    pyjson(&json!(vec![["A", "has_req", "B"]; 10001]))
                ),
            ]);
            grid(root, vs.len(), |p, i| query(p, json!({"raw":vs[i]})))
        }
        "graph.paths" => {
            let vs = "missing ../outside .env private/g.yaml alias.yaml link/g.yaml file.yaml \
endpoint profile"
                .split_whitespace()
                .collect::<Vec<_>>();
            grid(root, vs.len(), |p, i| paths(p, vs[i]))
        }
        "profile.invalid" => {
            let vs = [
                "[".into(),
                "paths=1".into(),
                "[paths]\nprotected_paths=\"x\"".into(),
                "[paths]\nprotected_paths=[\"../x\"]".into(),
                "[paths]\nprotected_paths=[\"\"]".into(),
                "#".repeat(65537),
                format!(
                    "[paths]\nprotected_paths={}",
                    pyjson(&json!(vec!["x"; 257]))
                ),
            ];
            grid(root, vs.len(), |p, i| query(p, json!({"profile":vs[i]})))
        }
        "profile.collections" => {
            return query(
                root,
                json!({"profile":
            "[paths]\nprotected_paths=[\"src\", \"src\"]\n[boundaries]\nsecrets=[\"tests/*\"]\n\
[preserve]\nagent_memory_paths=[\"private\"]\n"}),
            );
        }
        "query.skipped" => {
            let mut rs = rows();
            for v in ".env secrets/key ../bad absent src private/key".split_whitespace() {
                rs.as_array_mut()
                    .unwrap()
                    .push(json!(["A", "implemented_in", v]));
            }
            return query(
                root,
                json!({"rows":rs,
                "profile":"[paths]\nprotected_paths=[\"private\"]"}),
            );
        }
        "query.locators" => grid(root, 3, |p, i| {
            let mut rs = rows();
            rs.as_array_mut()
                .unwrap()
                .push(json!(["R", "verified_by", "tests/t.py::two"]));
            let anchor = ["tests/t.py", "./tests/t.py::one", "tests/t.py::absent"][i];
            query(
                p,
                json!({"anchor":anchor,"purpose":"verification","max_edges":1,"rows":rs}),
            )
        }),
        "bundle.routes" => {
            let inputs = parse(
                r#"[[[],null],[["A","B"],null],[["A"],[]],[["A"],["impact"]],
[["A"],["other","impact"]],[["unknown"],null],
[["A","A"],["implementation","verification","implementation"]],
[["src/m.py"],["implementation","verification"]],[["src/m.py::x"],null],
[["missing/file"],null],["A",null],[["../bad"],null]]"#,
            );
            grid(root, 12, |p, i| {
                b(
                    p,
                    inputs[i][0].clone(),
                    if inputs[i][1].is_null() {
                        ps.clone()
                    } else {
                        inputs[i][1].clone()
                    },
                )
            })
        }
        "bundle.unavailable" => {
            return observed(r::bundle_relations(&json!(["A"]), &ps, &Options::new(root)));
        }
        "bundle.protected" => return b(root, json!([".env"]), ps),
        "profile.values" => {
            setup(
                root,
                &rows(),
                None,
                "[paths]\nprotected_paths=[\"private\", \"private\"]\n\
[boundaries]\nsecrets=[\"keys/*\"]\n[preserve]\nagent_memory_paths=[\"local\"]",
            );
            return observed(r::profile_protections(root));
        }
        "bundle.empty_facet" => {
            return bundle(root, json!(["A"]), ps, json!([["A", "has_req", "B"]]), 16);
        }
        "bundle.ambiguous" => {
            let mut rs = rows();
            rs.as_array_mut()
                .unwrap()
                .push(json!(["OTHER", "implemented_in", "src/m.py"]));
            return bundle(root, json!(["src/m.py"]), ps, rs, 16);
        }
        "bundle.limits" => grid(root, 3, |p, i| {
            bundle(p, json!(["A"]), ps.clone(), rows(), [1, 2, 16][i])
        }),
        "render.bytes" => grid(root, 16, |p, i| {
            let mut rs = rows();
            for n in 0..8 {
                rs.as_array_mut().unwrap().push(json!([
                    "A",
                    "has_req",
                    format!("N{n}{}", "\u{e9}".repeat(150))
                ]));
            }
            setup(p, &rs, None, "");
            let o = Options::new(p);
            let v = if i < 8 {
                r::query_relations(&json!("A"), "implementation", &o)
            } else {
                r::bundle_relations(&json!(["A"]), &ps, &o)
            }
            .unwrap();
            let before = v.clone();
            let budget = [100, 1024, 6000, 16000][i % 4];
            let out = match i / 4 {
                0 | 2 => r::render_json(&v, budget),
                1 => r::render_human(&v, budget),
                _ => r::render_bundle_human(&v, budget),
            };
            observed(out.map(|s| json!([compact(s), before == v])))
        }),
        "helpers.values" => {
            setup(root, &rows(), None, "");
            let edge = r::Edge {
                source: "A".into(),
                relation: "has_req".into(),
                target: "B".into(),
                source_line: None,
                provenance: Some(json!({"database":"synthetic","sources":[
                    {"source_path":"docs/a.md","summary":"\u{e9}","reason":"declared"}]})),
            };
            let value = r::result(
                ("A", "implementation", "hash", "custom.yaml"),
                std::slice::from_ref(&edge),
                vec![],
                vec!["A".into()],
            );
            json!([
                edge.as_dict(),
                r::render_edge(&edge.as_dict(), "custom.yaml"),
                r::render_human(&value, 6000).unwrap(),
                r::render_source(&json!(
                    {"memory_db":"synthetic"}))
                .unwrap(),
                r::source_line(r::DEFAULT_GRAPH, &json!(2)),
                r::source_line("custom.yaml", &json!(2)),
                r::notices(
                    &BTreeMap::from([("z".into(), 2), ("a".into(), 1)]),
                    vec!["extra".into()]
                )
            ])
        }
        "helpers.protection" | "helpers.protection_edges" => {
            let inputs = if name == "helpers.protection" {
                ".ENV/x|secrets/x|.mir/memory.db-wal|private/a|src/./m.py::x|A\u{2029}"
            } else {
                "secrets|private_notes/a|privatex|cfg/.env.local|src/.envrc|SECRETS"
            };
            json!(
                inputs
                    .split('|')
                    .map(|v| json!([
                        v,
                        r::protected(v, &["private".into()]),
                        r::matches_protection(v, "private"),
                        r::endpoint_path(v, false),
                        r::normalized_locator(v),
                        r::has_control_characters(v)
                    ]))
                    .collect::<Vec<_>>()
            )
        }
        "helpers.paths" => {
            let vs = json!([null, "", ".", "C:\\x", "a\\b", "./src/m.py"]);
            grid(root, 6, |_, i| {
                observed(r::safe_relative_path(&vs[i], "test"))
            })
        }
        "helpers.patterns" => {
            let vs = json!([3, "/abs", ".", "x".repeat(4097), "a\t", "a\\b"]);
            grid(root, 6, |_, i| observed(r::profile_pattern(&vs[i])))
        }
        "helpers.roots" => grid(root, 2, |p, i| {
            observed(r::resolve_root(&if i == 0 {
                json!(3)
            } else {
                json!(p.join("missing-root-that-does-not-exist"))
            }))
        }),
        "helpers.source_invalid" => return observed(r::render_source(&json!({}))),
        "cli.arguments" => {
            let args = parse(
                r#"[[],["--help"],["query","--help"],["bundle","--help"],
["other"],["query","A"],["query","A","--purpose","other"],
["query","A","--purpose","impact","--depth","bad"],
["query","A","--purpose","impact","--graph","../escape"],
["query","A","--purpose","impact","--graph","x","--memory"]]"#,
            );
            grid(root, 10, |p, i| {
                let args = args[i].as_array().unwrap();
                let args: Vec<_> = args.iter().map(|v| v.as_str().unwrap()).collect();
                cli_case(p, &args)
            })
        }
        "cli.commands" | "cli.bundle_graph" => {
            let commands = if name == "cli.commands" {
                vec![
                    "query A --purpose implementation",
                    "query A --purpose verification",
                    "query A --purpose impact",
                    "query A --purpose dependencies",
                    "query unknown --purpose impact",
                    "bundle A --purpose implementation",
                ]
            } else {
                vec!["bundle A --purpose implementation --purpose verification"]
            };
            grid(root, commands.len() * 2, |p, i| {
                let mut args = commands[i / 2].split_whitespace().collect::<Vec<_>>();
                if i % 2 == 1 {
                    args.push("--json");
                }
                cli_case(p, &args)
            })
        }
        _ => panic!("unmapped record {name}"),
    };
    json!({"value":value})
}
#[test]
fn frozen_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b06-relations.json")).unwrap();
    let tmp = tempfile::tempdir().unwrap();
    let (mut replayed, exempt) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        let root = tmp.path().join(name);
        fs::create_dir(&root).unwrap();
        assert_eq!(replay(name, &root), *expected, "{name}");
        replayed += 1;
        eprintln!("{name}: replayed");
    }
    assert_eq!((replayed, exempt), (28, 0));
    eprintln!("replayed={replayed} exempt={exempt} total=28");
}
