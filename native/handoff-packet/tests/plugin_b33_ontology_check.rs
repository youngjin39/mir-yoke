//! Frozen Python output is the oracle, including errors and long-value hashes.
use handoff_packet::plugin_scripts::ontology_check::{self as q, Doc, Reader};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    fs,
    path::{Path, PathBuf},
};
#[path = "../src/digest.rs"]
mod digest;
fn d(v: Value) -> Doc {
    Doc::from(v)
}
fn parse(s: &str) -> Doc {
    q::load_json(s).unwrap()
}
fn setup(root: &Path) -> (Doc, Doc) {
    let c = parse(concat!(
        r#"{"schema":"mir-semantic-contract/v1","contract_id":"sample","version":"1.1.0","#,
        r#""rules":[{"id":"r"}],"concepts":[{"id":"c"}],"relations":[{"id":"rel","#,
        r#""from":["c"],"to":["*"]}],"error_cases":[{"id":"e","rules":["r"]}],"#,
        r#""axes":{"state":{"values":{"ok":""}}},"mapping":{"required_keys":["namespace"],"#,
        r#""knowledge_supply_values":["connected"]}}"#
    ));
    let m = parse(concat!(
        r#"{"schema":"mir-semantic-mapping/v1","namespace":"sample","contract":{"id":"sample","#,
        r#""version":"1.1.0","version_range":">=1.0.0 <2.0.0"},"canonical_index":["a.py"],"#,
        r#""concepts":{"c":{"status":"mapped","local":[{"name":"alpha","ref":"a.py#alpha"}]}},"#,
        r#""vocabularies":[{"name":"v","ref":"a.md","values":{"ready":{"state":"ok"}}}],"#,
        r#""relations":[{"local":"r","common":"rel","from":["c"],"to":"*"}],"#,
        r#""domain":{"concepts":[{"ref":"a.py"}],"relations":[{"ref":"a.py"}],"#,
        r#""invariants":[{"ref":"a.py","check":"a.py:2"},{"ref":"a.md"}]},"#,
        r#""questions":[{"id":"q","question":"alpha sample","evidence":["a.py","absent"]}],"#,
        r#""error_cases":[{"id":"e","status":"covered","check":"a.py#alpha"}],"#,
        r#""knowledge_supply":{"memory_keeper":"connected","binding":"resident_stdio"},"#,
        r#""entrypoints":[{"ref":"a.py"}]}"#
    ));
    fs::create_dir_all(root.join(".mir")).unwrap();
    for (name, text) in [
        ("a.py", "def alpha():\n    pass\n".into()),
        ("a.md", "# Alpha\n".into()),
        (".mir/repo-profile.toml", "slug = \"sample\"\n".into()),
        ("contract.json", c.dump(false, None)),
        (".mir/ontology-map.json", m.dump(false, None)),
    ] {
        fs::write(root.join(name), text).unwrap();
    }
    (c, m)
}
fn clean(v: Value, root: &Path) -> Value {
    match v {
        Value::String(s) => {
            let parent = root.parent().unwrap().to_str().unwrap();
            let s = s
                // Handoff stdout contains JSON inside a string; replace its escaped root first.
                .replace(&root.to_str().unwrap().replace('\\', "\\\\"), "<tmp>")
                .replace(root.to_str().unwrap(), "<tmp>")
                .replace(&parent.replace('\\', "\\\\"), "<parent>")
                .replace(parent, "<parent>");
            let chars = s.chars().collect::<Vec<_>>();
            if chars.len() > 240 {
                json!({"length":chars.len(),"sha256":digest::sha256(s.as_bytes()),
                "first":chars[..120].iter().collect::<String>(),
                "last":chars[chars.len()-120..].iter().collect::<String>()})
            } else {
                json!(s)
            }
        }
        Value::Array(a) => json!(a.into_iter().map(|v| clean(v, root)).collect::<Vec<_>>()),
        Value::Object(m) => {
            Value::Object(m.into_iter().map(|(k, v)| (k, clean(v, root))).collect())
        }
        v => v,
    }
}
fn observe(v: q::Result<Value>, root: &Path) -> Value {
    match v {
        Ok(v) => json!({"value":clean(v,root)}),
        Err(e) => json!({"error":[e.class,
        e.message.replace(root.to_str().unwrap(),"<tmp>")]}),
    }
}
fn digest(v: Value) -> Value {
    let text = d(v.clone()).dump(true, None);
    if text.len() > 512 {
        json!({"len":text.len(),"sha256":digest::sha256(text.as_bytes())})
    } else {
        v
    }
}
struct Io<'a>(&'a Path);
impl Reader for Io<'_> {
    fn path(&self, p: &str, _: bool) -> q::Result<PathBuf> {
        Ok(self.0.join(p))
    }
    fn exists(&self, p: &str) -> q::Result<bool> {
        Ok(self.0.join(p).exists())
    }
    fn read(&self, p: &str) -> q::Result<Vec<u8>> {
        let path = if p == "." {
            self.0.to_path_buf()
        } else {
            self.0.join(p)
        };
        if path.is_dir() {
            return Err(q::error(
                "IsADirectoryError",
                format!("[Errno 21] Is a directory: '{}'", path.display()),
            ));
        }
        fs::read(&path).map_err(|e| q::error("OSError", e.to_string()))
    }
}
fn run(
    root: &Path,
    data: &Doc,
    contract: &Doc,
    is_contract: bool,
    guarded: bool,
) -> q::Result<Value> {
    let io = Io(root);
    let mut c = q::Checker::new(guarded.then_some(&io as &dyn Reader));
    let result = if is_contract {
        let c = c.contract(data);
        json!({"sha256":digest::sha256(
        c.dump(true,None).as_bytes())})
    } else {
        {
            let v = c.mapping(data, contract, b"{}", root)?;
            if matches!(v, Doc::Object(_) | Doc::Array(_)) {
                json!({"sha256":digest::sha256(v.dump(true,None).as_bytes())})
            } else {
                v.value()
            }
        }
    };
    Ok(json!([
        result,
        c.errors.iter().map(Doc::value).collect::<Vec<_>>(),
        c.warnings.iter().map(Doc::value).collect::<Vec<_>>(),
        c.checked_refs,
        c.line_refs
    ]))
}
fn replace(doc: &mut Doc, path: &[Value], value: Doc) {
    if path.is_empty() {
        *doc = value;
        return;
    }
    match doc {
        Doc::Object(m) => {
            let (_, v) = m
                .iter_mut()
                .find(|(k, _)| Some(k.as_str()) == path[0].as_str())
                .unwrap();
            replace(v, &path[1..], value);
        }
        Doc::Array(a) => replace(
            &mut a[path[0].as_u64().unwrap() as usize],
            &path[1..],
            value,
        ),
        _ => panic!("invalid test path"),
    }
}
fn variants(doc: &Doc, path: Vec<Value>, out: &mut Vec<Vec<Value>>) {
    out.push(path.clone());
    let children: Vec<_> = match doc {
        Doc::Object(m) => m.iter().map(|(k, v)| (json!(k), v)).collect(),
        Doc::Array(a) => a.iter().enumerate().map(|(i, v)| (json!(i), v)).collect(),
        _ => vec![],
    };
    for (k, v) in children {
        let mut p = path.clone();
        p.push(k);
        variants(v, p, out);
    }
}
fn update_declaration(m: &mut Doc, version: &str, bounds: &str) {
    let mut c = m.get("contract").clone();
    c.set("version", d(json!(version)));
    c.set("version_range", d(json!(bounds)));
    c.set("sha256", d(json!("bad")));
    m.set("contract", c);
}
fn validation(root: &Path, guarded: bool) -> Value {
    let (mut contract, mut mapping) = setup(root);
    let mut results = vec![];
    for (original, is_contract) in [(&contract, true), (&mapping, false)] {
        results.push(run(root, original, &contract, is_contract, guarded).unwrap());
        let mut paths = vec![];
        variants(original, vec![], &mut paths);
        for path in paths {
            for value in [
                json!(null),
                json!({}),
                json!([]),
                json!(""),
                json!("unknown"),
                json!(false),
            ] {
                let mut data = original.clone();
                replace(&mut data, &path, d(value.clone()));
                results.push(json!([
                    path,
                    value,
                    digest(observe(
                        run(root, &data, &contract, is_contract, guarded),
                        root
                    ))
                ]));
            }
        }
    }
    for version in ["1.0.0", "1.2.0", "2.0.0", "bad"] {
        for bounds in [">=1.0.0 <2.0.0", ">=2.0.0 <3.0.0", ">=2.0.0 <1.0.0"] {
            update_declaration(&mut mapping, version, bounds);
            results.push(run(root, &mapping, &contract, false, guarded).unwrap());
        }
    }
    let changes = vec![
        (json!(["contract", "version"]), vec![json!("1.0.0")]),
        (
            json!(["concepts", "c"]),
            vec![
                json!({"status":"absent"}),
                json!({"status":"not_applicable","reason":"x"}),
            ],
        ),
        (
            json!(["relations"]),
            vec![
                json!([{"local":"r","local_only":"x","ref":"a.py"}]),
                json!([{"local":"r","common":"rel","from":["bad"],"to":[]}]),
            ],
        ),
        (
            json!(["vocabularies", 0, "values"]),
            vec![
                json!({"x":{"local_only":"x","state":"ok"}}),
                json!({"x":{"local_only":"x"}}),
            ],
        ),
        (
            json!(["error_cases"]),
            vec![
                json!([{"id":"e","status":"covered"}]),
                json!([{"id":"e","status":"planned","check":"a.py"}]),
            ],
        ),
    ];
    for (path, values) in changes {
        for value in values {
            let mut data = mapping.clone();
            update_declaration(&mut data, "1.1.0", ">=1.0.0 <2.0.0");
            replace(&mut data, path.as_array().unwrap(), d(value));
            results.push(run(root, &data, &contract, false, guarded).unwrap());
        }
    }
    replace(
        &mut contract,
        &[json!("rules")],
        d(json!([{"id":"r"},{"id":"r"}])),
    );
    results.push(run(root, &contract, &contract, true, guarded).unwrap());
    update_declaration(&mut mapping, "1.0.0", ">=1.0.0 <2.0.0");
    replace(
        &mut mapping,
        &[json!("knowledge_supply")],
        d(json!({"memory_keeper":"connected"})),
    );
    results.push(run(root, &mapping, &contract, false, guarded).unwrap());
    replace(
        &mut mapping,
        &[json!("domain"), json!("relations"), json!(0)],
        parse(r#"{"ref":"a.py","common":"rel","from":["bad"],"to":[]}"#),
    );
    update_declaration(&mut mapping, "1.1.0", ">=1.0.0 <2.0.0");
    results.push(run(root, &mapping, &contract, false, guarded).unwrap());
    mapping.remove("namespace");
    for profile in [None, Some(""), Some("slug = \"other\"")] {
        let p = root.join(".mir/repo-profile.toml");
        if let Some(text) = profile {
            fs::write(p, text).unwrap();
        } else {
            fs::remove_file(p).unwrap();
        }
        results.push(run(root, &mapping, &contract, false, guarded).unwrap());
    }
    json!(results)
}
struct Git<'a> {
    state: &'a str,
    calls: RefCell<Vec<Value>>,
}
impl q::GitRunner for Git<'_> {
    fn run(&self, argv: &[String], timeout: u64) -> q::Result<q::GitOutput> {
        self.calls
            .borrow_mut()
            .push(json!([argv,{"capture_output":true,"check":false,
            "timeout":timeout}]));
        if self.state == "timeout" {
            return Err(q::error(
                "TimeoutExpired",
                format!("Command 'git' timed out after {timeout} seconds"),
            ));
        }
        if self.state == "oserror" {
            return Err(q::error("OSError", "blocked"));
        }
        Ok(q::GitOutput {
            returncode: i32::from(self.state == "fail"),
            stdout: if argv.iter().any(|s| s == "diff") {
                b"a.py\0old\0".to_vec()
            } else if argv
                .iter()
                .any(|s| ["rev-parse", "log"].contains(&s.as_str()))
            {
                b"abc\n".to_vec()
            } else {
                vec![]
            },
            stderr: b"bad\xff\n".to_vec(),
        })
    }
}
impl q::PinRunner for Git<'_> {
    fn run(&self, label: &str, _: &[String]) -> q::Result<Doc> {
        Ok(d(if self.state == "fail" {
            Value::Null
        } else if label.ends_with("modified_vs_head") {
            json!(false)
        } else {
            json!("abc")
        }))
    }
}
fn git(state: &str) -> Git<'_> {
    Git {
        state,
        calls: RefCell::new(vec![]),
    }
}
fn fake(root: &Path, state: &str, call: impl FnOnce(&Git<'_>) -> q::Result<Value>) -> Value {
    let g = git(state);
    let value = observe(call(&g), root);
    json!([value, g.calls.into_inner()])
}
fn pins(root: &Path, state: &str, guarded: bool) -> Value {
    setup(root);
    fake(root, state, |g| {
        q::handoff_pins(
            root,
            &["a.py".into(), "absent".into()],
            &d(json!({})),
            guarded.then_some(&Io(root) as &dyn Reader),
            (guarded && state != "missing_runner").then_some(g as &dyn q::PinRunner),
            &q::Context {
                git: g,
                observed_at: "fixed",
            },
        )
        .map(|v| v.value())
    })
}
fn symbols(root: &Path) -> Value {
    let mut out = vec![];
    for suffix in [
        ".md",
        ".markdown",
        ".mdx",
        ".json",
        ".py",
        ".rs",
        ".js",
        ".ts",
        ".go",
        ".kt",
        ".kts",
        ".dart",
        ".toml",
        ".sh",
        ".bash",
        ".zsh",
        ".txt",
    ] {
        for text in [
            "# Alpha\n# Alpha\n```\n# Hidden\n```\n<!-- # Secret -->",
            "pub fn alpha() {}\nalpha = 1\n[alpha]\nfunction alpha() {",
            "/* fun hidden() */\n// fun secret()\nfun alpha() {}",
            "{\"a/b\": [{\"~x\": 0}], \"alpha\": {}}",
            "{bad",
            "test(\"alpha\", x)",
        ] {
            for name in [
                "",
                "alpha",
                "pkg.alpha",
                "alpha-1",
                "hidden",
                "secret",
                "/a~1b/0/~0x",
                "/a~1b/00",
                "/bad~2",
            ] {
                out.push(observe(
                    q::resolves_symbol(text, name, suffix, None).map(|v| json!(v)),
                    root,
                ));
            }
        }
    }
    out.push(observe(
        q::resolves_symbol("{bad", "alpha", ".json", None).map(|v| json!(v)),
        root,
    ));
    out.push(observe(
        q::resolves_symbol(
            "{bad",
            "alpha",
            ".json",
            Some(&|_| {
                Err(q::error(
                    "JSONDecodeError",
                    "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)",
                ))
            }),
        )
        .map(|v| json!(v)),
        root,
    ));
    json!(out)
}
fn selections(root: &Path, guarded: bool) -> Value {
    let (_, m) = setup(root);
    let io = Io(root);
    let io = guarded.then_some(&io as &dyn Reader);
    let mut out = vec![
        json!(
            q::map_entries(&m)
                .iter()
                .map(|(p, e)| json!([p, e.value()]))
                .collect::<Vec<_>>()
        ),
        json!(q::entry_refs(&m, "")),
    ];
    for diff in [false, true] {
        for paths in [
            vec![],
            vec!["a.py"],
            vec![".mir/ontology-map.json"],
            vec!["a.md"],
        ] {
            out.push(
                q::impact(
                    &m,
                    root,
                    &paths.iter().map(|s| (*s).into()).collect::<Vec<_>>(),
                    diff,
                    io,
                )
                .unwrap()
                .value(),
            );
        }
    }
    for query in ["", "alpha", "sample c"] {
        for limit in [0, 1, 3, 99] {
            out.push(q::lookup(&m, query, limit, io).unwrap().value());
        }
    }
    json!(out)
}
fn refs(root: &Path, guarded: bool) -> Value {
    setup(root);
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(root.parent().unwrap(), root.join("escape")).unwrap();
        std::os::unix::fs::symlink("loop", root.join("loop")).unwrap();
    }
    let io = Io(root);
    let mut c = q::Checker::new(guarded.then_some(&io as &dyn Reader));
    let mut out = vec![];
    for r in [
        Value::Null,
        json!(""),
        json!("/abs"),
        json!("C:\\abs"),
        json!("C:rel"),
        json!("a\\b"),
        json!("../x"),
        json!("escape"),
        json!("absent"),
        json!("."),
        json!("a.py"),
        json!("a.py#alpha"),
        json!("a.py#missing"),
        json!("a.py:0"),
        json!("a.py:99"),
        json!("a.md:1"),
    ] {
        out.push(observe(
            c.covered_check(&d(r), "/r", root).map(|_| json!("None")),
            root,
        ));
    }
    c.refs(&d(json!([{"ref":"a.py"},"a.md"])), "/refs", root)
        .unwrap();
    json!([
        out,
        c.errors.iter().map(Doc::value).collect::<Vec<_>>(),
        c.warnings.iter().map(Doc::value).collect::<Vec<_>>(),
        c.checked_refs,
        q::impact(
            &d(json!({"canonical_index":["loop"]})),
            root,
            &["loop".into()],
            false,
            None
        )
        .unwrap()
        .value()
    ])
}
fn cli(root: &Path, args: &[&str], payload: Option<&str>) -> Value {
    setup(root);
    #[cfg(windows)]
    if args == ["mapping", "--handoff", "a.py"] {
        fs::write(root.join("a.py"), b"def alpha():\r\n    pass\r\n").unwrap();
    }
    if let Some(payload) = payload {
        let p = root.join(".mir/ontology-map.json");
        if payload == "missing" {
            fs::remove_file(p).unwrap();
        } else {
            fs::write(p, payload).unwrap();
        }
    }
    let mut args = args.iter().map(|s| (*s).into()).collect::<Vec<String>>();
    if !args.is_empty() && args[0] != "contract" {
        args.extend(["--repo".into(), root.display().to_string()]);
    }
    args.extend([
        "--contract".into(),
        root.join("contract.json").display().to_string(),
    ]);
    let g = git("ok");
    let o = q::main(
        &args,
        &q::Context {
            git: &g,
            observed_at: "fixed",
        },
    );
    json!([[{"value":o.exit},g.calls.into_inner()],o.stdout,o.stderr])
}
fn replay(name: &str, root: &Path) -> Value {
    match name {
        "validation" | "validation_codes" => validation(root, name.ends_with("codes")),
        "symbols" => symbols(root),
        "selection_False" | "selection_True" => selections(root, name.ends_with("True")),
        "refs" | "refs_codes" => refs(root, name.ends_with("codes")),
        "version" => json!(
            [
                Value::Null,
                json!(1),
                json!(""),
                json!("01.0.0"),
                json!("1.2.3"),
                json!("1.2.3-01"),
                json!("1.2.3-a.2+build"),
                json!("1.2.3-0")
            ]
            .iter()
            .map(|v| observe(
                Ok(q::version_key(&d(v.clone())).map_or(Value::Null, |d| d.value())),
                root
            ))
            .collect::<Vec<_>>()
        ),
        "helpers" => json!([
            q::pointer("/a", "~x/y"),
            q::ref_path("a.py:3#x"),
            q::touches("./a", &["a/b".into()]),
            (["0", "-1", "1", "bad", "1.5"]
                .iter()
                .map(|v| observe(q::positive_int(v).map(|v| json!(v)), root))
                .collect::<Vec<_>>())
        ]),
        "question_counts" => {
            let (c, m) = setup(root);
            json!(
                (1..=3)
                    .map(|n| {
                        let mut m = m.clone();
                        m.set(
                            "questions",
                            d(json!(
                                (0..n)
                                    .map(|i| json!({"id":format!("q{i}"),"question":"alpha sample",
                    "evidence":["a.py"]}))
                                    .collect::<Vec<_>>()
                            )),
                        );
                        let mut checker = q::Checker::new(None);
                        checker.mapping(&m, &c, b"{}", root).unwrap();
                        json!([
                            n,
                            checker.warnings.iter().map(Doc::value).collect::<Vec<_>>()
                        ])
                    })
                    .collect::<Vec<_>>()
            )
        }
        "lookup_scores" => {
            let (_, mut m) = setup(root);
            m.set(
                "questions",
                d(json!([
                {"id":"one","question":"alpha","evidence":[]},
                {"id":"three","question":"alpha beta gamma","evidence":[]},
                {"id":"two","question":"alpha beta","evidence":[]}])),
            );
            json!(
                q::lookup(&m, "alpha beta gamma", 99, None)
                    .unwrap()
                    .get("matches")
                    .list()
                    .iter()
                    .map(|m| json!([m.get("pointer").value(), m.get("score").value()]))
                    .collect::<Vec<_>>()
            )
        }
        "git" => json!(
            ["ok", "fail", "timeout", "oserror"]
                .iter()
                .map(|state| observe(
                    Ok(fake(root, state, |g| q::changed_paths(
                        None, "HEAD", root, g
                    )
                    .map(|v| json!(v)))),
                    root
                ))
                .collect::<Vec<_>>()
        ),
        "pins" | "guarded_pins" => {
            let guarded = name == "guarded_pins";
            let states = if guarded {
                vec!["ok", "fail", "missing_runner"]
            } else {
                vec!["ok", "fail", "timeout", "oserror"]
            };
            json!(
                states
                    .iter()
                    .map(|state| observe(Ok(pins(root, state, guarded)), root))
                    .collect::<Vec<_>>()
            )
        }
        "paths" => {
            let g = git("ok");
            let cases = [
                (Some(vec!["a".into(), "./a".into(), "z".into()]), ""),
                (Some(vec!["../a".into()]), ""),
                (Some(vec![root.join("a").display().to_string()]), ""),
                (Some(vec!["/outside".into()]), ""),
                (None, "-bad"),
            ];
            json!(
                cases
                    .iter()
                    .map(|(p, b)| observe(
                        q::changed_paths(p.as_deref(), b, root, &g).map(|v| json!(v)),
                        root
                    ))
                    .collect::<Vec<_>>()
            )
        }
        "main" => {
            let cases = vec![
                vec!["contract"],
                vec!["mapping", "--handoff", "a.py"],
                vec!["mapping", "--json"],
                vec!["impact", "--paths", "a.py", "--strict"],
                vec!["impact", "--git-diff", "--json"],
                vec!["lookup", "alpha"],
                vec!["lookup", "alpha", "--json"],
                vec!["lookup", "alpha", "--limit", "0"],
                vec![],
                vec!["unknown"],
            ];
            json!(
                cases
                    .iter()
                    .map(|args| observe(Ok(cli(root, args, None)), root))
                    .collect::<Vec<_>>()
            )
        }
        "main_errors" => {
            let mut out = vec![];
            let large = format!("{}{{}}", " ".repeat(32769));
            for cmd in ["mapping", "impact", "lookup"] {
                for payload in ["missing", "{", "[]", &large] {
                    let args = match cmd {
                        "impact" => vec![cmd, "--paths", "a.py", "--strict"],
                        "lookup" => vec![cmd, "alpha"],
                        _ => vec![cmd],
                    };
                    out.push(observe(Ok(cli(root, &args, Some(payload))), root));
                }
            }
            json!(out)
        }
        "lookup_casefold" => json!(
            ["ALPHA", "aLpHa_x"]
                .map(|q| observe(Ok(cli(root, &["lookup", q, "--json"], None)), root))
        ),
        "main_limit" => {
            let values = [
                "abc",
                "1_0",
                " 2 ",
                "\u{1c}3",
                "\u{663}",
                "-99999999999999999999999",
                "99999999999999999999",
                "a'b",
                "+1",
                "1__0",
                "-0",
            ];
            json!(values.map(|v| observe(
                Ok(cli(root, &["lookup", "alpha", "--limit", v], None)),
                root
            )))
        }
        _ => panic!("unhandled {name}"),
    }
}
fn main8_expected(unix: &Value, windows: bool) -> Value {
    if !windows {
        return unix.clone();
    }
    let capture: Value =
        serde_json::from_str(include_str!("fixtures/wt-path-records-main8-windows.json")).unwrap();
    let mut observation = capture["records"][0]["observation"].clone();
    // Replace only the captured synthetic root, preserving the diagnostic suffix bytes.
    observation[2] = json!(
        observation[2]
            .as_str()
            .unwrap()
            .replace(r"{ROOT}\\ontology-main-8", "<tmp>")
    );
    json!({"value": observation})
}
#[test]
fn main8_expectation_selector_matches_capture() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b33-ontology-check.json")).unwrap();
    let capture: Value =
        serde_json::from_str(include_str!("fixtures/wt-path-records-main8-windows.json")).unwrap();
    let unix = &records["main"]["value"][8];
    assert_eq!(main8_expected(unix, false), *unix, "Unix record unchanged");
    let mut observation = capture["records"][0]["observation"].clone();
    observation[2] = json!(
        observation[2]
            .as_str()
            .unwrap()
            .replace(r"{ROOT}\\ontology-main-8", "<tmp>")
    );
    let windows = main8_expected(unix, true);
    assert_eq!(
        windows,
        json!({"value": observation}),
        "Windows captured main[8]"
    );
    assert_eq!(windows["value"][0], json!([{ "value": 2 }, []]));
    assert_eq!(windows["value"][1], "");
    assert_ne!(windows, *unix, "Windows suffix must differ from Unix");
}
#[test]
fn frozen_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b33-ontology-check.json")).unwrap();
    let mut replayed = 0;
    #[cfg(windows)]
    let mut exempt = 0;
    #[cfg(unix)]
    let exempt = 0;
    for (name, expected) in records.as_object().unwrap() {
        let tmp = tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap();
        let actual = observe(Ok(replay(name, tmp.path())), tmp.path());
        #[cfg(windows)]
        let windows_expected = {
            let mut e = expected.clone();
            if name == "main" {
                let capture: Value =
                    serde_json::from_str(include_str!("fixtures/wt-path-records-windows.json"))
                        .unwrap();
                let stdout = capture["records"][9]["stdout"]
                    .as_str()
                    .unwrap()
                    .replace("{ROOT}\\\\plugin-capture\\\\ontology-main-1", "<tmp>");
                e["value"][1]["value"][1] = clean(json!(stdout), tmp.path());
                e["value"][8] = main8_expected(&e["value"][8], true);
            }
            e
        };
        #[cfg(windows)]
        let expected = &windows_expected;
        #[cfg(windows)]
        if ["refs", "refs_codes", "paths"].contains(&name.as_str()) {
            // Unix symlinks and POSIX absolute-path cells cannot run as native Windows fixtures.
            if name == "paths" {
                for i in [0, 1, 2, 4] {
                    assert_eq!(actual["value"][i], expected["value"][i]);
                }
            } else {
                for i in (0..16).filter(|i| *i != 7) {
                    assert_eq!(actual["value"][0][i], expected["value"][0][i]);
                }
                let a = actual["value"][1].as_array().unwrap();
                let e = expected["value"][1].as_array().unwrap();
                if name == "refs" {
                    for i in (0..e.len()).filter(|i| *i != 7) {
                        assert_eq!(a[i], e[i]);
                    }
                } else {
                    let a = a
                        .iter()
                        .enumerate()
                        .filter(|(i, _)| *i != 7)
                        .map(|(_, v)| v)
                        .collect::<Vec<_>>();
                    assert_eq!(a, e.iter().collect::<Vec<_>>());
                }
                for key in [
                    "changed_paths",
                    "affected_entries",
                    "checks_to_run",
                    "undeclared_check_links",
                    "revalidate",
                ] {
                    assert_eq!(actual["value"][4][key], expected["value"][4][key]);
                }
                assert_eq!(actual["value"][2], expected["value"][2]);
                assert_eq!(actual["value"][3], expected["value"][3]);
            }
            eprintln!("EXEMPT {name}: Unix path/symlink cells; representable cells replayed");
            exempt += 1;
            continue;
        }
        if actual != *expected {
            if let (Some(a), Some(e)) = (actual["value"].as_array(), expected["value"].as_array()) {
                for (i, (a, e)) in a.iter().zip(e).enumerate() {
                    assert_eq!(a, e, "{name}[{i}]");
                }
            }
            assert_eq!(actual, *expected, "record {name}");
        }
        eprintln!("REPLAYED {name}");
        replayed += 1;
    }
    assert_eq!(replayed + exempt, 19);
    #[cfg(unix)]
    {
        assert_eq!((replayed, exempt), (19, 0));
    }
    #[cfg(windows)]
    {
        assert_eq!((replayed, exempt), (16, 3));
    }
}
