//! Replay the unmodified Python oracle. Exemptions are Python-only surfaces, never new goldens.
use handoff_packet::plugin_scripts::relations_query::{self as q, Reader};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    fs,
    path::{Path, PathBuf},
};
#[path = "../src/digest.rs"]
mod digest;
const ROWS: &[(&str, &str, &str)] = &[
    ("A", "has_req", "R"),
    ("R", "realized_by", "M"),
    ("M", "implemented_in", "src/a.py::z"),
    ("M", "implemented_in", "src/a.py::a"),
    ("R", "verified_by", "tests/a.py"),
    ("A", "depends_on", "B"),
    ("B", "depends_on", "C"),
    ("C", "depends_on", "A"),
    ("A", "depends_on", "B"),
    ("A", "affects", "Z"),
    ("A", "blocks", "Q"),
    ("A", "decided_by", "D"),
    ("A", "governed_by", "G"),
    ("A", "exposes", "E"),
    ("A", "refines", "R"),
    ("A", "constrains", "M"),
    ("A", "implemented_in", ".env"),
    ("A", "verified_by", "missing/file"),
    ("../bad", "has_req", "A"),
];
fn graph() -> Vec<u8> {
    let mut raw = String::from("edges:\n");
    for (a, r, b) in ROWS {
        raw.push_str(&format!(
            "  - {}\n",
            json!([a, r, b]).to_string().replace(',', ", ")
        ));
    }
    raw.into_bytes()
}
fn setup(root: &Path) {
    for name in ["src/a.py", "tests/a.py", "spec/graph.yaml"] {
        let p = root.join(name);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(
            p,
            if name.ends_with("yaml") {
                graph()
            } else {
                b"pass\n".to_vec()
            },
        )
        .unwrap();
    }
}
fn compact(v: Value) -> Value {
    match v {
        Value::String(s) if s.chars().count() > 240 => json!({"length":s.chars().count(),
            "sha256":digest::sha256(s.as_bytes()),"first":s.chars().take(120).collect::<String>(),
            "last":s.chars().skip(s.chars().count()-120).collect::<String>()}),
        Value::Array(a) => Value::Array(a.into_iter().map(compact).collect()),
        Value::Object(m) => Value::Object(m.into_iter().map(|(k, v)| (k, compact(v))).collect()),
        other => other,
    }
}
fn observe(v: q::Result<Value>) -> Value {
    match v {
        Ok(v) => json!({"value":compact(v)}),
        Err(q::RelationsError::Code(c)) => json!({"error":["RelationsError",c]}),
        Err(q::RelationsError::Refusal { class, message }) => json!({"error":[class,message]}),
    }
}
fn query(root: &Path, anchor: &str, purpose: &str, depth: Value, cap: usize) -> Value {
    let o = q::Options {
        root,
        graph: q::DEFAULT_GRAPH,
        depth,
        max_edges: json!(cap),
    };
    observe(q::query_relations(
        &json!(anchor),
        &json!(purpose),
        &o,
        None,
    ))
}
fn rows() -> Value {
    let mut values = vec![
        "[A, depends_on, B] # comment".into(),
        "[\"a,b\", r, 'it''s']".into(),
        "[]".into(),
        "[a,b]".into(),
        "[a,b,c,d]".into(),
        "[a, b, c]#bad".into(),
        "[a,b,c]junk".into(),
        "[a, null, c]".into(),
        "[a, 2026-01-01, c]".into(),
        "[a, &x, c]".into(),
        "[a, : x, c]".into(),
        "[a, \"\", c]".into(),
        "[a, \"\\u0085\", c]".into(),
        "[a, \"\\ud800\", c]".into(),
        "[a, 'unfinished, c]".into(),
        "[a, \"bad\\q\", c]".into(),
        "[a, b, c".into(),
    ];
    values.extend([
        format!("[a, {}, c]", "x".repeat(4096)),
        format!("[a, {}, c]", "x".repeat(4097)),
    ]);
    json!(
        values
            .iter()
            .map(|s: &String| observe(q::row(s).map(|v| json!(v))))
            .collect::<Vec<_>>()
    )
}
fn graphs() -> Value {
    let raws: Vec<&[u8]> = vec![
        b"# c\n\nedges: # c\n - [a,r,b]\r\n",
        b"edges: [] # empty\n",
        b"",
        b"edges:\n",
        b"other: []",
        b"edges: []\n - [a,r,b]",
        b"edges:\n - [a,r,b]\n  - [b,r,c]",
        b"edges:\n\t- [a,r,b]",
        b"edges:\n - [a,r,b]\rx",
        b"\xff",
        b"edges:\n - [a,r,b]\n - [a,r,b]",
    ];
    json!(
        raws.iter()
            .map(|s| observe(
                q::parse_graph(s)
                    .map(|g| json!(g.iter().map(q::Edge::as_dict).collect::<Vec<_>>()))
            ))
            .collect::<Vec<_>>()
    )
}
#[cfg(unix)]
const PROFILE: &str = concat!(
    "[paths]\nprotected_paths=[\"private\"]\n",
    "[boundaries]\nsecrets=[\"vault/*\"]\n[preserve]\nagent_memory_paths=[\"remember\"]"
);
#[cfg(unix)]
fn reader(root: &Path, profile: &str) -> q::Result<Value> {
    fs::create_dir_all(root.join(".mir")).unwrap();
    fs::write(root.join(".mir/repo-profile.toml"), profile).unwrap();
    std::os::unix::fs::symlink(root.join(".env"), root.join("alias")).unwrap();
    std::os::unix::fs::symlink(root.parent().unwrap(), root.join("escape")).unwrap();
    let obj = q::LocalReader::new(root)?;
    let values = [
        "src/a.py",
        "missing",
        "src",
        ".env",
        ".aws/key",
        "x.pem",
        "alias",
        "escape/outside",
        "private/a",
        "vault/a",
        "remember/a",
        "../x",
    ];
    let mut out = json!({});
    for mode in ["endpoint", "exists", "path"] {
        out[mode] = json!(
            values
                .iter()
                .map(|p| observe(match mode {
                    "endpoint" => q::validate_endpoint(p, &obj, true).map(|v| json!(v)),
                    "exists" => obj.exists(p).map(|v| json!(v)),
                    _ => obj.path(p, true).map(|p| json!(
                        p.to_str().unwrap().replace(root.to_str().unwrap(), "<tmp>")
                    )),
                }))
                .collect::<Vec<_>>()
        );
    }
    Ok(out)
}
struct Injected {
    refusal: String,
    calls: RefCell<Vec<Value>>,
}
impl Injected {
    fn call(&self, mode: &str, call: Value) -> q::Result<()> {
        self.calls.borrow_mut().push(call);
        if self.refusal == mode {
            return Err(q::RelationsError::Refusal {
                class: "PermissionError".into(),
                message: format!("guard {mode} refusal"),
            });
        }
        Ok(())
    }
}
impl Reader for Injected {
    fn path(&self, p: &str, allow: bool) -> q::Result<PathBuf> {
        self.call("path", json!(["path", p, allow]))?;
        Ok(PathBuf::new())
    }
    fn exists(&self, p: &str) -> q::Result<bool> {
        self.call("exists", json!(["exists", p]))?;
        Ok(self.refusal != "missing")
    }
    fn read(&self, p: &str) -> q::Result<Vec<u8>> {
        self.call("read", json!(["read", p]))?;
        Ok(if self.refusal == "large" {
            vec![b'x'; q::MAX_GRAPH_BYTES + 1]
        } else {
            graph()
        })
    }
}
fn injected(root: &Path, refusal: &str) -> Value {
    let io = Injected {
        refusal: refusal.into(),
        calls: RefCell::new(vec![]),
    };
    let result = observe(q::query_relations(
        &json!("src/a.py"),
        &json!("impact"),
        &q::Options::new(root),
        Some(&io),
    ));
    json!({"result":result,"calls":io.calls.into_inner()})
}
fn cli(root: &Path) -> Value {
    let cases: Vec<Vec<&str>> = vec![
        vec!["A", "implementation"],
        vec!["A", "dependencies", "--depth", "4"],
        vec!["unknown", "impact"],
        vec!["A", "bad"],
        vec![],
        vec!["A", "impact", "--depth", "bad"],
    ];
    json!(
        cases
            .iter()
            .map(|args| {
                let mut args: Vec<_> = args.iter().map(|s| s.to_string()).collect();
                args.extend(["--root".into(), root.to_str().unwrap().into()]);
                let out = q::main(&args);
                observe(Ok(
                    json!({"exit":out.exit,"stdout":out.stdout,"stderr":out.stderr}),
                ))
            })
            .collect::<Vec<_>>()
    )
}
fn replay(name: &str, root: &Path) -> q::Result<Value> {
    let value = match name {
        "row" => rows(),
        "parse_graph" => graphs(),
        "parse_graph_comment_cr" => json!([observe(
            q::parse_graph(b"edges:\n - [a,r,b]\n# c\rx\n")
                .map(|g| json!(g.iter().map(q::Edge::as_dict).collect::<Vec<_>>()))
        )]),
        "reader_uppercase" => {
            let obj = q::LocalReader::new(root)?;
            json!(
                ["SECRETS/a", ".ENV", "X.PEM", ".AWS/key"]
                    .map(|p| observe(obj.exists(p).map(|b| json!(b))))
            )
        }
        "graph_edges_limit" => json!(
            [q::MAX_GRAPH_EDGES, q::MAX_GRAPH_EDGES + 1]
                .iter()
                .map(|n| {
                    let raw = format!("edges:\n{}", " - [a,r,b]\n".repeat(*n));
                    observe(q::parse_graph(raw.as_bytes()).map(|v| json!(v.len())))
                })
                .collect::<Vec<_>>()
        ),
        "helpers" => json!({"paths":(["A","a.py","./x","a/b::f"].map(|p|
            q::endpoint_path(p,false))),"normalized":q::normalized_locator("./a//b::f"),
            "controls":(["a","\t","\u{2029}"].map(q::has_control_characters)),
            "notices":q::notices(&[("z".into(),2),("a".into(),1)].into(),vec!["extra".into()])}),
        "purpose_invalid" => json!(
            [Value::Null, json!(""), json!("other")]
                .iter()
                .map(|p| observe(q::query_relations(
                    &json!("A"),
                    p,
                    &q::Options::new(root),
                    None
                )))
                .collect::<Vec<_>>()
        ),
        #[cfg(unix)]
        "reader_default" => return reader(root, ""),
        #[cfg(unix)]
        "reader_profile" => return reader(root, PROFILE),
        "main" => cli(root),
        s if s.starts_with("injected_") => injected(root, &s[9..]),
        s if s.starts_with("query_") => {
            return q::query_relations(&json!("A"), &json!(&s[6..]), &q::Options::new(root), None);
        }
        s if s.starts_with("depth_") => {
            json!([1, 2, 4].map(|d| query(root, "A", &s[6..], json!(d), 16)))
        }
        s if s.starts_with("locator_") => {
            return q::query_relations(
                &json!(&s[8..]),
                &json!("impact"),
                &q::Options {
                    max_edges: json!(1),
                    ..q::Options::new(root)
                },
                None,
            );
        }
        s if s.starts_with("max_edges_") => {
            return q::query_relations(
                &json!("A"),
                &json!("implementation"),
                &q::Options {
                    depth: json!(4),
                    max_edges: json!(s[10..].parse::<usize>().unwrap()),
                    ..q::Options::new(root)
                },
                None,
            );
        }
        s if s.starts_with("profile_invalid_") => {
            let profiles = [
                "[paths]\nprotected_paths=\"x\"".into(),
                "paths=[]".into(),
                "[".into(),
                "[paths]\nprotected_paths=[\"../x\"]".into(),
                format!("[paths]\nprotected_paths={}", json!(vec!["x"; 257])),
                "#".repeat(65537),
            ];
            fs::create_dir_all(root.join(".mir")).unwrap();
            fs::write(
                root.join(".mir/repo-profile.toml"),
                &profiles[s[16..].parse::<usize>().unwrap()],
            )
            .unwrap();
            q::LocalReader::new(root)?;
            panic!("invalid profile accepted");
        }
        _ => panic!("unhandled record: {name}"),
    };
    Ok(value)
}
// Whole-record exemptions are explicit because Python's compact matrix contains
// values or monkeypatch operations that cannot be supplied to the Rust API.
fn exemption(name: &str) -> Option<&'static str> {
    match name {
        "relative" | "query_invalid" => Some("Python lone-surrogate str has no Rust str value"),
        "reader_io" => Some("Python Path.open monkeypatch has no Rust filesystem equivalent"),
        #[cfg(windows)]
        "reader_default" | "reader_profile" => Some("Unix symlink fixture; Windows exempt"),
        _ => None,
    }
}
#[test]
fn frozen_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b33-relations-query.json")).unwrap();
    let mut replayed = 0;
    let mut exempt = 0;
    for (name, expected) in records.as_object().unwrap() {
        if let Some(reason) = exemption(name) {
            eprintln!("EXEMPT {name}: {reason}");
            exempt += 1;
            continue;
        }
        let tmp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        setup(tmp.path());
        assert_eq!(
            observe(replay(name, tmp.path())),
            *expected,
            "record {name}"
        );
        eprintln!("REPLAYED {name}");
        replayed += 1;
    }
    assert_eq!(replayed + exempt, 39);
    #[cfg(unix)]
    assert_eq!((replayed, exempt), (36, 3));
    #[cfg(windows)]
    assert_eq!((replayed, exempt), (34, 5));
}
// Representable cells of the three whole-record exemptions replay against their frozen cells.
#[test]
fn representable_cells_of_exempt_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b33-relations-query.json")).unwrap();
    let tmp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
    setup(tmp.path());
    let (x4096, x4097) = ("x".repeat(4096), "x".repeat(4097));
    // Index 14 is a Python lone surrogate, which no Rust str can hold.
    let paths = [
        Some(None),
        Some(Some("")),
        Some(Some(".")),
        Some(Some("./src//a.py")),
        Some(Some("src\\a.py")),
        Some(Some("../x")),
        Some(Some("/x")),
        Some(Some("C:\\x")),
        Some(Some("C:x")),
        Some(Some("\\\\host\\share")),
        Some(Some("a\0")),
        Some(Some("a\u{7f}")),
        Some(Some("a\u{9f}")),
        Some(Some("a\u{2028}")),
        None,
        Some(Some(x4096.as_str())),
        Some(Some(x4097.as_str())),
    ];
    assert_eq!(
        paths.len(),
        records["relative"]["value"].as_array().unwrap().len()
    );
    for (i, p) in paths.iter().enumerate() {
        if let Some(p) = p {
            let actual = observe(q::relative(*p).map(|v| json!(v)));
            assert_eq!(actual, records["relative"]["value"][i], "relative[{i}]");
        }
    }
    // Index 2 is a Python lone surrogate anchor.
    let invalid = [
        Some(("".into(), Value::Null, None)),
        Some(("src/a.py\u{1}".into(), Value::Null, None)),
        None,
        Some(("x".repeat(4097), Value::Null, None)),
        Some(("\u{e9}".repeat(2049), Value::Null, None)),
        Some(("unknown".into(), Value::Null, None)),
        Some(("../a".into(), Value::Null, None)),
        Some((".env".into(), Value::Null, None)),
        Some(("A".into(), json!(true), None)),
        Some(("A".into(), json!(0), None)),
        Some(("A".into(), json!(5), None)),
        Some(("A".into(), Value::Null, Some(json!(0)))),
        Some(("A".into(), Value::Null, Some(json!(65)))),
        Some(("A".into(), Value::Null, Some(json!(1.5)))),
    ];
    assert_eq!(
        invalid.len(),
        records["query_invalid"]["value"].as_array().unwrap().len()
    );
    for (i, item) in invalid.into_iter().enumerate() {
        let Some((anchor, depth, cap)) = item else {
            continue;
        };
        let defaults = q::Options::new(tmp.path());
        let o = q::Options {
            depth,
            max_edges: cap.unwrap_or(defaults.max_edges.clone()),
            ..defaults
        };
        let actual = observe(q::query_relations(
            &json!(anchor),
            &json!("implementation"),
            &o,
            None,
        ));
        assert_eq!(
            actual, records["query_invalid"]["value"][i],
            "query_invalid[{i}]"
        );
    }
    // reader_io cells 0-7; cell 3 passes Python None and cell 8 patches Path.open.
    let io = &records["reader_io"]["value"];
    let reader = q::LocalReader::new(tmp.path()).unwrap();
    let read = |p: &str| observe(reader.read(p).map(|b| json!(String::from_utf8(b).unwrap())));
    for (i, p) in ["src/a.py", "absent", "src"].into_iter().enumerate() {
        assert_eq!(read(p), io[i], "reader_io[{i}]");
    }
    for (i, p) in [(4, "absent"), (5, "src/a.py")] {
        let actual = observe(q::LocalReader::new(&tmp.path().join(p)).map(|_| Value::Null));
        assert_eq!(actual, io[i], "reader_io[{i}]");
    }
    for (i, size) in [(6, q::MAX_GRAPH_BYTES), (7, q::MAX_GRAPH_BYTES + 1)] {
        fs::write(tmp.path().join("large"), vec![b'#'; size]).unwrap();
        assert_eq!(read("large"), io[i], "reader_io[{i}]");
    }
}

#[test]
fn cli_options_and_python_integer_grammar() {
    assert_eq!(q::row("[a,\u{1c}b\u{1f},c]").unwrap(), ["a", "b", "c"]);
    let tmp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
    setup(tmp.path());
    let root = format!("--root={}", tmp.path().to_str().unwrap());
    for depth in ["1", "+1", " 1 ", "0_1", "\u{661}"] {
        let args = ["A", "implementation", &root, "--dep", depth].map(String::from);
        let out = q::main(&args);
        assert_eq!(out.exit, 0, "{depth:?}: {}", out.stderr);
        let value: Value = serde_json::from_str(&out.stdout).unwrap();
        assert_eq!(value["edges"].as_array().unwrap().len(), 6);
    }
    let args = ["A", "implementation", &root, "--depth", &"9".repeat(100)].map(String::from);
    let out = q::main(&args);
    assert_eq!(out.exit, 1);
    assert!(out.stdout.contains("E_SCHEMA"));
    for depth in ["_1", "1_", "1__0"] {
        let out = q::main(&["A", "impact", &root, "--depth", depth].map(String::from));
        assert_eq!(out.exit, 2);
        assert!(out.stderr.contains("invalid int value"));
    }
    let out = q::main(&["--help".into()]);
    assert_eq!(out.exit, 0);
    assert!(out.stderr.is_empty());
    assert!(out.stdout.contains("positional arguments:\n  anchor\n"));
    assert!(out.stdout.ends_with("  --max-edges MAX_EDGES\n"));
}
