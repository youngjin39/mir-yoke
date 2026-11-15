//! Replay the 77 immutable Python records, including file bytes and host calls.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::bootstrap::{self as m, Error, Host};
use handoff_packet::plugin_scripts::ontology_check::{Doc, object};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::Path};
#[path = "../src/digest.rs"]
mod digest;

fn doc(value: Value) -> Doc {
    Doc::from(value)
}
fn put(root: &Path, name: &str, body: impl AsRef<[u8]>) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, body).unwrap();
}
fn put_json(root: &Path, name: &str, value: &Doc) {
    put(root, name, value.dump(false, None));
}
fn release(root: &Path, paths: &[&str]) {
    let files = paths
        .iter()
        .map(|p| {
            object(vec![
                ("path", doc(json!(p))),
                (
                    "sha256",
                    doc(json!(digest::sha256(&fs::read(root.join(p)).unwrap()))),
                ),
            ])
        })
        .collect();
    put_json(
        root,
        "config/adopter-payload.json",
        &object(vec![("files", Doc::Array(files))]),
    );
}
fn source() -> Doc {
    let pack = object(vec![
        ("agents", doc(json!(["agents/main.md", "agents/worker.md"]))),
        ("plugins", doc(json!(["tools"]))),
    ]);
    object(vec![
        (
            "source",
            object(vec![
                ("url", doc(json!("https://example.invalid/provider"))),
                ("ref", doc(json!("v1"))),
            ]),
        ),
        (
            "profiles",
            object(vec![
                ("aliases", doc(json!({"hybrid_pipeline":"code_app"}))),
                (
                    "packs",
                    Doc::Object(
                        m::PROFILE_CHOICES
                            .iter()
                            .map(|p| ((*p).into(), pack.clone()))
                            .collect(),
                    ),
                ),
            ]),
        ),
        ("plugins", doc(json!({"tools":{"skills":["design"]}}))),
    ])
}
struct Fake<'a> {
    root: &'a Path,
    mode: &'a str,
    calls: Vec<Value>,
    cli_calls: Vec<Value>,
}
impl Host for Fake<'_> {
    fn env(&mut self, _: &str) -> Option<String> {
        panic!("unexpected env")
    }
    fn resolve(&mut self, _: &Path) -> Result<std::path::PathBuf, Error> {
        panic!("unexpected resolve")
    }
    fn expanduser(&mut self, _: &Path) -> Result<std::path::PathBuf, Error> {
        panic!("unexpected expanduser")
    }
    fn is_dir(&mut self, _: &Path) -> bool {
        panic!("unexpected is_dir")
    }
    fn writable(&mut self, _: &Path) -> bool {
        panic!("unexpected writable")
    }
    fn device(&mut self, _: &Path) -> Result<u64, Error> {
        panic!("unexpected device")
    }
    fn run(&mut self, request: &m::CommandRequest) -> Result<m::CommandOutput, Error> {
        assert_eq!(request.cwd, self.root);
        assert!(request.stdin_null && request.capture_output && request.text && !request.check);
        assert!(request.environment.is_empty());
        self.calls.push(json!([request.argv, request.cwd, -3]));
        Ok(m::CommandOutput {
            returncode: i32::from(self.root.join("fail").exists()),
            stdout: fs::read(self.root.join("stdout")).unwrap_or_default(),
            stderr: if self.root.join("stderr").exists() {
                b"denied".to_vec()
            } else {
                vec![]
            },
        })
    }
    fn capability_import(&mut self) -> Result<(), Error> {
        if self.mode == "import" {
            Err(Error::new(
                "ModuleNotFoundError",
                "No module named 'missing_package'",
            ))
        } else {
            Ok(())
        }
    }
    fn capability_main(&mut self, argv: &[String]) -> Result<m::CapabilityOutput, Error> {
        self.cli_calls.push(json!(argv));
        Ok(m::CapabilityOutput {
            code: if ["output", "silent"].contains(&self.mode) {
                7
            } else {
                0
            },
            stdout: if self.mode == "output" {
                "sync refused\n".into()
            } else {
                "".into()
            },
            stderr: "".into(),
        })
    }
    fn validate_artifacts(&mut self, records: &Value, plugins: &Value) -> Result<(), Error> {
        if self.mode == "native_error" {
            Err(Error::new("ValueError", "artifact refused"))
        } else {
            handoff_packet::mir_core::capabilities::native::validate_artifacts(
                records, plugins, false,
            )
            .map_err(|e| Error::new("ValueError", e))
        }
    }
}
fn catalog(root: &Path, profile: &str, mode: &str) -> Result<Value, Error> {
    let mut agents = object(vec![
        (
            "main",
            object(vec![
                ("role", doc(json!("control_plane"))),
                ("recommended_skills", doc(json!(["design", "unused"]))),
            ]),
        ),
        ("worker", doc(json!({"role":"execution"}))),
    ]);
    if mode == "roles" {
        agents.set("worker", doc(json!({"role":"control_plane"})));
    }
    let inventory = object(vec![
        (
            "agents",
            if mode == "agents" {
                doc(json!({}))
            } else {
                agents
            },
        ),
        (
            "skills",
            if mode == "skills" {
                doc(json!({}))
            } else {
                object(vec![
                    ("design", doc(json!({"status":"local"}))),
                    ("unused", doc(json!({}))),
                ])
            },
        ),
    ]);
    let template = object(vec![
        (
            "default_skill_pack",
            doc(json!({"core":["design","unused"]})),
        ),
        (
            "tracked_paths",
            doc(json!({"harness_structure":["plugins/local","docs/"]})),
        ),
    ]);
    let mut templates = Doc::Object(
        [
            "code_app",
            "hybrid_pipeline",
            "infra_runtime",
            "ontology_content",
        ]
        .iter()
        .map(|t| ((*t).into(), template.clone()))
        .collect(),
    );
    if mode == "single_template" {
        let selected = if profile == "content_workspace" {
            "ontology_content"
        } else {
            profile
        };
        if let Doc::Object(entries) = &mut templates {
            entries.retain(|(key, _)| key == selected);
        }
    }
    let mut data = object(vec![
        (
            "catalog",
            if mode == "inventory" {
                Doc::null()
            } else {
                inventory
            },
        ),
        (
            "templates",
            if mode == "template" {
                doc(json!({}))
            } else {
                templates
            },
        ),
        ("repositories_dir", doc(json!("repos"))),
        ("repositories", doc(json!(["provider"]))),
    ]);
    let mut caps = source();
    if mode == "pack" {
        let mut profiles = caps.get("profiles").clone();
        let mut packs = profiles.get("packs").clone();
        packs.set("code_app", Doc::null());
        profiles.set("packs", packs);
        caps.set("profiles", profiles);
    }
    put_json(root, "config/capability-sources.json", &caps);
    if mode == "object" {
        data = doc(json!([]));
    }
    put(
        root,
        "config/repo-agent-management.json",
        if mode == "invalid" {
            "[".into()
        } else {
            data.dump(false, None)
        },
    );
    release(root, &["config/repo-agent-management.json"]);
    match mode {
        "authored" => put_json(
            root,
            "config/repo-agent-management.json",
            &doc(json!({"authored":true})),
        ),
        "absent" => fs::remove_file(root.join("config/repo-agent-management.json")).unwrap(),
        "unmatched" => put(root, "config/adopter-payload.json", "{}"),
        "agent_file" => put(root, "agents/main.md", "Authored agent body\n"),
        _ => {}
    }
    let mut host = Fake {
        root,
        mode,
        calls: vec![],
        cli_calls: vec![],
    };
    // Exercise the real compiler via the default Host method, not a test replacement.
    host.compile_adopter_agent_catalog(root, profile)
        .map(|v| json!(v))
}
fn reset(root: &Path, mode: &str, task: bool, host: &mut Fake<'_>) -> Result<Value, Error> {
    let paths = if task {
        vec![
            "tasks/change_log.md",
            "tasks/checklist.md",
            "tasks/handoffs/session-handoff-LATEST.md",
            "tasks/intent.json",
            "tasks/plan.md",
            "tasks/tdd.json",
        ]
    } else {
        vec!["CLAUDE.md", ".ai-harness/bluebricks.md", ".mir/boundary.md"]
    };
    for p in &paths {
        put(root, p, "provider\n");
    }
    release(root, &paths);
    for p in &paths {
        if ["authored", "authored_generator"].contains(&mode) {
            put(root, p, "authored\n");
        } else if mode == "absent" {
            fs::remove_file(root.join(p)).unwrap();
        }
    }
    if [
        "success",
        "failure",
        "stdout",
        "unknown",
        "authored_generator",
    ]
    .contains(&mode)
    {
        put(
            root,
            "scripts/generate_codex_derivatives.sh",
            "fake generator",
        );
    }
    if ["failure", "stdout", "unknown", "authored_generator"].contains(&mode) {
        put(root, "fail", "");
    }
    if mode == "failure" {
        put(root, "stderr", "");
    } else if mode == "stdout" {
        put(root, "stdout", "stdout failure\n");
    }
    if task {
        m::reset_provider_task_state(root, "Build product")?;
    } else {
        m::reset_provider_contract_state(root, "product", "code_app", "Build product", host)?;
    }
    Ok(Value::Null)
}
fn load(root: &Path, mode: &str) -> Result<Value, Error> {
    let mut data = source();
    match mode {
        "empty" => data = doc(json!({})),
        "object" => data = doc(json!([])),
        "source" => data.set("source", doc(json!([]))),
        "url" => data.set("source", doc(json!({"ref":"v1"}))),
        "ref" => data.set("source", doc(json!({"url":"u"}))),
        "profiles" => data.set("profiles", doc(json!({}))),
        "profiles_type" => data.set("profiles", doc(json!([]))),
        "packs" => data.set("profiles", doc(json!({"packs":[]}))),
        "missing_pack" => data.set("profiles", doc(json!({"packs":{}}))),
        _ => {}
    }
    if mode != "missing" {
        put(
            root,
            "config/capability-sources.json",
            if mode == "invalid" {
                "{".into()
            } else {
                data.dump(false, None)
            },
        );
    }
    m::load_capability_sources(root, "code_app")
}
fn lock(root: &Path, mode: &str) {
    let mut data = object(vec![
        ("schema_version", doc(json!(1))),
        ("source", doc(json!({"commit":"a".repeat(40)}))),
        (
            "plugins",
            object(vec![("z", doc(json!({}))), ("a", doc(json!({})))]),
        ),
        (
            "agents",
            object(vec![("worker", doc(json!({}))), ("main", doc(json!({})))]),
        ),
        ("profile", doc(json!("code_app"))),
        ("registration", doc(json!({"status":"active"}))),
    ]);
    match mode {
        "inactive" => data.set("registration", doc(json!({"status":"pending"}))),
        "registration" => data.set("registration", doc(json!([]))),
        "commit" => data.set("source", doc(json!({"commit":"short"}))),
        "uppercase" => data.set("source", doc(json!({"commit":"A".repeat(40)}))),
        "plugins" | "source" => data.set(mode, doc(json!({}))),
        "long_commit" => data.set("source", doc(json!({"commit":"a".repeat(41)}))),
        "agents_list" => data.set("agents", doc(json!(["worker", "main"]))),
        _ => {}
    }
    if mode.starts_with("native") {
        data.set(
            "native_artifacts",
            doc(if mode == "native_valid" {
                json!({})
            } else {
                json!([])
            }),
        );
        if mode == "native_config" {
            put(root, "config/capability-sources.json", "{}");
        }
    }
    if mode != "missing" {
        put(
            root,
            ".mir/capability-lock.json",
            match mode {
                "invalid" => "{".into(),
                "object" => "[]".into(),
                _ => data.dump(false, None),
            },
        );
    }
}
fn case(root: &Path, name: &str, host: &mut Fake<'_>) -> Result<Value, Error> {
    let (operation, mode) = name.split_once('.').unwrap();
    match operation {
        "catalog" => {
            let (profile, mode) = mode.split_once('.').unwrap_or(("code_app", mode));
            catalog(root, profile, mode)
        }
        "contract" | "tasks" => reset(root, mode, operation == "tasks", host),
        "load" => load(root, mode),
        "activate" | "finalize" | "lock" => {
            lock(root, mode);
            let receipt = (mode != "no_receipt").then(|| {
                json!({"status":
                if mode == "prior_ready" { "ready" } else { "restart_required" }})
            });
            let value = match operation {
                "activate" => m::activate_capabilities(root, "code_app", host)?,
                "finalize" => m::finalize_capabilities(root, receipt.as_ref(), host)?,
                _ => m::capability_lock_evidence(root, host)?,
            };
            let value = (value.0, m::scalar_evidence(&value.1).unwrap());
            Ok(json!([value, host.cli_calls]))
        }
        _ => panic!("unmapped record {name}"),
    }
}
fn compact_bytes(bytes: &[u8]) -> Value {
    if bytes.len() > 512 {
        json!({"len":bytes.len(),"sha256":digest::sha256(bytes)})
    } else {
        json!(std::str::from_utf8(bytes).unwrap())
    }
}
fn compact_value(value: Value) -> Value {
    let body = doc(value.clone()).dump(true, None);
    if body.len() > 512 {
        compact_bytes(body.as_bytes())
    } else {
        value
    }
}
/// Python text-mode writes use CRLF on Windows; the oracle was captured on Unix.
fn disk(bytes: Vec<u8>) -> Vec<u8> {
    #[cfg(windows)]
    let bytes = String::from_utf8(bytes.clone())
        .map(|text| text.replace("\r\n", "\n").into_bytes())
        .unwrap_or(bytes);
    bytes
}
fn files(root: &Path, current: &Path, out: &mut BTreeMap<String, Value>) {
    for entry in fs::read_dir(current).unwrap() {
        let path = entry.unwrap().path();
        if path.is_file() {
            let bytes = disk(fs::read(&path).unwrap());
            out.insert(
                path.strip_prefix(root)
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .replace('\\', "/"),
                compact_bytes(&bytes),
            );
        } else if path.is_dir() {
            files(root, &path, out);
        }
    }
}
fn normalise(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => {
            let s = s.replace(root.to_str().unwrap(), "<tmp>");
            #[cfg(windows)]
            let s = s
                .replace("\\\\?\\", "")
                .replace(
                    root.to_str().unwrap().trim_start_matches("\\\\?\\"),
                    "<tmp>",
                )
                .replace(
                    &root
                        .to_str()
                        .unwrap()
                        .trim_start_matches("\\\\?\\")
                        .replace('\\', "/"),
                    "<tmp>",
                );
            json!(s.replace("<tmp>\\", "<tmp>/"))
        }
        Value::Array(v) => Value::Array(v.into_iter().map(|v| normalise(v, root)).collect()),
        Value::Object(v) => Value::Object(
            v.into_iter()
                .map(|(k, v)| (k, normalise(v, root)))
                .collect(),
        ),
        v => v,
    }
}
#[test]
fn replay_all_77_frozen_records() {
    let records: BTreeMap<String, Value> =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-capabilities.json")).unwrap();
    assert_eq!(records.len(), 77);
    let captured_profiles: Vec<_> = records
        .keys()
        .filter_map(|n| n.strip_prefix("catalog."))
        .filter_map(|n| n.strip_suffix(".matched"))
        .collect();
    let mut profiles = m::PROFILE_CHOICES.to_vec();
    profiles.sort();
    assert_eq!(profiles, captured_profiles);
    let mut failures = vec![];
    let mut replayed = 0;
    for (name, expected) in records {
        let temp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        let root = temp.path().canonicalize().unwrap();
        let mode = name.split_once('.').unwrap().1;
        let mut host = Fake {
            root: &root,
            mode,
            calls: vec![],
            cli_calls: vec![],
        };
        let result = case(&root, &name, &mut host);
        let mut actual = match result {
            Ok(v) => json!({"value":compact_value(normalise(v, &root))}),
            Err(e) => json!({"error":[e.class,e.message]}),
        };
        let mut written = BTreeMap::new();
        files(&root, &root, &mut written);
        actual["files"] = json!(written);
        actual["calls"] = json!(host.calls);
        let actual = normalise(actual, &root);
        replayed += 1;
        println!("{name}: replayed");
        if actual != expected {
            failures.push(format!("{name}\nactual: {actual}\nexpected: {expected}"));
        }
    }
    // No symlink or permission cases exist in this oracle, on either platform.
    assert_eq!((replayed, 0), (77, 0));
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

#[test]
fn failed_activation_cannot_be_finalized() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-capabilities.json")).unwrap();
    let temp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
    let root = temp.path().canonicalize().unwrap();
    lock(&root, "output");
    let mut host = Fake {
        root: &root,
        mode: "output",
        calls: vec![],
        cli_calls: vec![],
    };
    let activation = m::activate_capabilities(&root, "code_app", &mut host).unwrap();
    assert_eq!(
        json!([activation.0, m::scalar_evidence(&activation.1).unwrap()]),
        records["activate.output"]["value"][0]
    );
    assert_eq!(
        normalise(json!(host.cli_calls), &root),
        records["activate.output"]["value"][1]
    );
    host.cli_calls.clear();
    host.mode = "valid";
    let prior = json!({"status":activation.0});
    let result = m::finalize_capabilities(&root, Some(&prior), &mut host).unwrap();
    // The frozen rejection cell covers any prior status other than restart_required.
    assert_eq!(
        json!([
            (result.0, m::scalar_evidence(&result.1).unwrap()),
            host.cli_calls
        ]),
        records["finalize.prior_ready"]["value"]
    );
}

#[test]
fn each_profile_uses_its_own_template() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-capabilities.json")).unwrap();
    for profile in m::PROFILE_CHOICES {
        let temp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        let root = temp.path().canonicalize().unwrap();
        // Removing unused templates must preserve the captured compiled bytes.
        let result = catalog(&root, profile, "single_template").unwrap();
        let record = &records[format!("catalog.{profile}.matched")];
        assert_eq!(result, record["value"]);
        assert_eq!(
            compact_bytes(&disk(
                fs::read(root.join("config/repo-agent-management.json")).unwrap()
            )),
            record["files"]["config/repo-agent-management.json"]
        );
    }
}

#[test]
fn native_lock_with_tracked_configuration_uses_frozen_evidence() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-capabilities.json")).unwrap();
    let temp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
    let root = temp.path().canonicalize().unwrap();
    lock(&root, "native_valid");
    put(
        &root,
        "config/capability-sources.json",
        include_str!("../../../config/capability-sources.json"),
    );
    let mut host = Fake {
        root: &root,
        mode: "native_valid",
        calls: vec![],
        cli_calls: vec![],
    };
    let evidence = m::capability_lock_evidence(&root, &mut host).unwrap();
    assert_eq!(
        json!([
            (evidence.0, m::scalar_evidence(&evidence.1).unwrap()),
            host.cli_calls
        ]),
        records["lock.native_valid"]["value"]
    );
}
