//! Replay the pinned Python core-adoption oracle, including bytes, modes and order.
#![forbid(unsafe_code)]
#![cfg(unix)]
use handoff_packet::mir_cli::bootstrap::{self as m, CommandOutput, CommandRequest, Error, Host};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    os::unix::fs::{MetadataExt, PermissionsExt, symlink},
    path::{Path, PathBuf},
};

struct Observer {
    root: PathBuf,
    external: PathBuf,
    options: Value,
    release: BTreeMap<String, Vec<u8>>,
    events: Vec<Value>,
    fd_counts: BTreeMap<(String, String), u64>,
    journal_calls: u64,
    swapped: bool,
}
impl Observer {
    fn fd(&mut self, operation: &str, phase: &str) -> std::io::Result<()> {
        let occurrence = self
            .fd_counts
            .entry((operation.into(), phase.into()))
            .or_default();
        *occurrence += 1;
        self.events
            .push(json!(["fd", operation, phase, *occurrence]));
        let fail = &self.options["fd_fail"];
        if fail["operation"] == operation && fail["phase"] == phase && fail["at"] == *occurrence {
            return Err(std::io::Error::from_raw_os_error(
                fail["errno"].as_i64().unwrap_or(5) as i32,
            ));
        }
        Ok(())
    }
    fn text(&self, path: &Path) -> String {
        path.to_string_lossy()
            .replace(self.external.to_str().unwrap(), "<external>")
            .replace(self.root.to_str().unwrap(), "<root>")
    }
    fn rename(
        &mut self,
        source: &Path,
        destination: &Path,
        mut operation: Option<&mut dyn FnMut() -> Result<(), Error>>,
    ) -> Result<(), Error> {
        let src = if destination.file_name().unwrap() == "slim-transaction.json" {
            self.journal_calls += 1;
            "<journal-temp>".to_owned()
        } else {
            self.text(source)
        };
        self.events
            .push(json!(["replace", src, self.text(destination)]));
        if self.options["deny_replace"]
            .as_str()
            .is_some_and(|name| destination == self.root.join(name))
            || destination.file_name().unwrap() == "slim-transaction.json"
                && self.options["deny_journal_at"] == self.journal_calls
        {
            return Err(Error::new(
                "PermissionError",
                format!("[Errno 13] Permission denied: '{}'", destination.display()),
            ));
        }
        if let Some(operation) = operation.as_mut() {
            operation()?;
        } else {
            fs::rename(source, destination).map_err(|e| Error::new("OSError", e.to_string()))?;
        }
        if destination.file_name().unwrap() == "slim-transaction.json" && self.journal_calls == 1 {
            match self.options["journal_action"].as_str() {
                Some("unsafe_source") => {
                    fs::create_dir_all(self.root.join("provider")).unwrap();
                    if self.root.join("provider/a").exists() {
                        fs::remove_file(self.root.join("provider/a")).unwrap();
                    }
                    symlink("../outside", self.root.join("provider/a")).unwrap();
                }
                Some("changed_source") => {
                    fs::create_dir_all(self.root.join("provider")).unwrap();
                    fs::write(self.root.join("provider/a"), b"changed").unwrap()
                }
                Some("unsafe_parent") => {
                    let parent = self.root.join(".mir/slim-quarantine").join("a".repeat(32));
                    fs::create_dir_all(&parent).unwrap();
                    if !parent.join("provider").exists() {
                        symlink("../../../../outside", parent.join("provider")).unwrap();
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }
}
impl Host for Observer {
    fn slim_before_move(&mut self, _root: &Path, source: &Path, destination: &Path) {
        let race = self.options["race"].as_str().unwrap_or("");
        if destination.file_name().unwrap() == "slim-transaction.json"
            || race.is_empty()
            || self.swapped
        {
            return;
        }
        self.swapped = true;
        let outside = self.root.parent().unwrap().join("outside");
        let relative = |target: &Path, from: &Path| {
            let levels = from
                .strip_prefix(self.root.parent().unwrap())
                .unwrap()
                .components()
                .count();
            PathBuf::from(format!(
                "{}{}",
                "../".repeat(levels),
                target
                    .strip_prefix(self.root.parent().unwrap())
                    .unwrap()
                    .display()
            ))
        };
        if race == "source_leaf" {
            fs::remove_file(source).unwrap();
            symlink(
                relative(&outside.join("a"), source.parent().unwrap()),
                source,
            )
            .unwrap();
            return;
        }
        let parent = if ["source", "rollback_source", "recovery_source"].contains(&race) {
            source.parent().unwrap()
        } else {
            destination.parent().unwrap()
        };
        fs::rename(
            parent,
            parent.with_file_name(format!(
                "{}-saved",
                parent.file_name().unwrap().to_str().unwrap()
            )),
        )
        .unwrap();
        symlink(relative(&outside, parent.parent().unwrap()), parent).unwrap();
    }
    fn slim_write(&mut self, file: &mut fs::File, body: &[u8], phase: &str) -> std::io::Result<()> {
        use std::io::Write;
        self.fd("write", phase)?;
        file.write_all(body)
    }
    fn slim_fsync(&mut self, file: &fs::File, phase: &str) -> std::io::Result<()> {
        self.fd("fsync", phase)?;
        file.sync_all()
    }
    fn env(&mut self, name: &str) -> Option<String> {
        (name == "HOME").then(|| {
            self.root
                .parent()
                .unwrap()
                .join("home")
                .display()
                .to_string()
        })
    }
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error> {
        if path.exists() {
            fs::canonicalize(path).map_err(|e| Error::new("OSError", e.to_string()))
        } else {
            Ok(path.to_path_buf())
        }
    }
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error> {
        Ok(path.to_path_buf())
    }
    fn is_dir(&mut self, path: &Path) -> bool {
        path.is_dir()
    }
    fn writable(&mut self, _path: &Path) -> bool {
        true
    }
    fn device(&mut self, path: &Path) -> Result<u64, Error> {
        Ok(fs::metadata(path).unwrap().dev())
    }
    fn platform_system(&mut self) -> String {
        self.options["platform"].as_str().unwrap_or("Darwin").into()
    }
    fn slim_pid(&mut self) -> u32 {
        424242
    }
    fn slim_transaction_id(&mut self) -> String {
        "a".repeat(32)
    }
    fn slim_process_alive(&mut self, _pid: i64) -> Result<bool, Error> {
        Ok(self.options["alive"] == true || self.options["alive_permission"] == true)
    }
    fn replace(&mut self, source: &Path, destination: &Path) -> Result<(), Error> {
        self.rename(source, destination, None)
    }
    fn slim_replace(
        &mut self,
        source: &Path,
        destination: &Path,
        operation: &mut dyn FnMut() -> Result<(), Error>,
    ) -> Result<(), Error> {
        self.rename(source, destination, Some(operation))
    }
    fn validate_boundary_schema(&mut self, _value: &Value, _schema: &Value) -> Result<(), Error> {
        if self.options["schema_error"] == true {
            Err(Error::new("ValidationError", "schema denied"))
        } else {
            Ok(())
        }
    }
    fn slim_run_clean(&mut self, request: &CommandRequest) -> Result<CommandOutput, Error> {
        self.run(request)
    }
    fn run(&mut self, request: &CommandRequest) -> Result<CommandOutput, Error> {
        assert_eq!(request.cwd, self.root);
        assert!(request.stdin_null && request.capture_output && !request.check);
        let argv: Vec<_> = request
            .argv
            .iter()
            .map(|arg| self.text(Path::new(arg)))
            .collect();
        self.events.push(json!(["run", argv]));
        if request.argv[0] == "git" {
            let name = request.argv[2].split_once(':').unwrap().1;
            if self.options["git_remove_control"] == name {
                fs::remove_file(self.root.join(name)).unwrap();
            }
            return Ok(CommandOutput {
                returncode: self.options["git_returncode"].as_i64().unwrap_or(0) as i32,
                stdout: if self.options["release_changed"] == true {
                    b"changed".to_vec()
                } else {
                    self.release[name].clone()
                },
                stderr: vec![],
            });
        }
        if request.argv[1] == "bootstrap" {
            match self.options["preflight_action"].as_str() {
                Some("remove_marker") => fs::remove_dir_all(self.root.join("provider")).unwrap(),
                Some("create_lock") => {
                    let path = self.root.join(".mir/slim.lock");
                    fs::write(&path, "race").unwrap();
                    fs::set_permissions(path, fs::Permissions::from_mode(0o600)).unwrap();
                }
                _ => {}
            }
            return Ok(CommandOutput {
                returncode: i32::from(self.options["preflight_fail"] == true),
                stdout: vec![],
                stderr: b"preflight denied".to_vec(),
            });
        }
        Ok(CommandOutput {
            returncode: self.options["verify_returncode"].as_i64().unwrap_or(0) as i32,
            stdout: self.options["verify_stdout"]
                .as_str()
                .map(|s| s.as_bytes().to_vec())
                .unwrap_or_else(|| {
                    serde_json::to_vec(
                        &json!({"ready":self.options["verify_ready"] != false,"changed_paths":[]}),
                    )
                    .unwrap()
                }),
            stderr: self.options["verify_stderr"]
                .as_str()
                .unwrap_or("")
                .as_bytes()
                .to_vec(),
        })
    }
}
fn decode(hex: &str) -> Vec<u8> {
    hex.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|s| u8::from_str_radix(std::str::from_utf8(s).unwrap(), 16).unwrap())
        .collect()
}
fn encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn populate(root: &Path, entries: &Value) {
    fs::create_dir_all(root).unwrap();
    let mut entries: Vec<_> = entries.as_object().unwrap().iter().collect();
    entries.sort_by_key(|(name, _)| (name.matches('/').count(), *name));
    let mut permissions = Vec::new();
    for (name, entry) in entries {
        let path = root.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        match entry["kind"].as_str().unwrap() {
            "dir" => fs::create_dir_all(&path).unwrap(),
            "symlink" => {
                symlink(entry["target"].as_str().unwrap(), &path).unwrap();
                continue;
            }
            "file" => fs::write(&path, decode(entry["hex"].as_str().unwrap())).unwrap(),
            kind => panic!("unknown initial node {kind}"),
        }
        permissions.push((path, entry["mode"].as_u64().unwrap() as u32));
    }
    for (path, mode) in permissions.into_iter().rev() {
        fs::set_permissions(path, fs::Permissions::from_mode(mode)).unwrap();
    }
}
fn snapshot(root: &Path) -> Value {
    fn walk(root: &Path, dir: &Path, rows: &mut serde_json::Map<String, Value>) {
        let entries = match fs::read_dir(dir) {
            Ok(entries) => entries,
            Err(error) if error.kind() == std::io::ErrorKind::PermissionDenied => return,
            Err(error) => panic!("cannot snapshot {}: {error}", dir.display()),
        };
        let mut paths: Vec<_> = entries.map(|e| e.unwrap().path()).collect();
        paths.sort();
        for path in paths {
            let name = path
                .strip_prefix(root)
                .unwrap()
                .to_str()
                .unwrap()
                .to_owned();
            let meta = fs::symlink_metadata(&path).unwrap();
            if meta.is_symlink() {
                rows.insert(
                    name,
                    json!({"kind":"symlink","target":fs::read_link(&path).unwrap()}),
                );
            } else if meta.is_dir() {
                rows.insert(name, json!({"kind":"dir","mode":meta.mode() & 0o7777}));
                walk(root, &path, rows);
            } else {
                rows.insert(name,json!({"kind":"file","mode":meta.mode() & 0o7777,"hex":encode(&fs::read(&path).unwrap())}));
            }
        }
    }
    let mut rows = serde_json::Map::new();
    walk(root, root, &mut rows);
    Value::Object(rows)
}
fn rewrite(value: &Value, root: &Path, external: &Path, expand: bool) -> Value {
    match value {
        Value::String(s) => {
            if expand {
                json!(
                    s.replace("<external>", external.to_str().unwrap())
                        .replace("<root>", root.to_str().unwrap())
                )
            } else {
                let loop_errno = if cfg!(target_os = "macos") { 62 } else { 40 };
                json!(
                    s.replace(external.to_str().unwrap(), "<external>")
                        .replace(root.to_str().unwrap(), "<root>")
                        .replace(&format!("[Errno {loop_errno}]"), "[Errno <ELOOP>]")
                )
            }
        }
        Value::Array(a) => Value::Array(
            a.iter()
                .map(|v| rewrite(v, root, external, expand))
                .collect(),
        ),
        Value::Object(o) => Value::Object(
            o.iter()
                .map(|(k, v)| (k.clone(), rewrite(v, root, external, expand)))
                .collect(),
        ),
        _ => value.clone(),
    }
}
fn make_accessible(path: &Path) {
    if path.is_symlink() || !path.is_dir() {
        return;
    }
    fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
    for entry in fs::read_dir(path).unwrap() {
        make_accessible(&entry.unwrap().path());
    }
}
#[test]
fn pinned_core_adoption_records() {
    // Run with the capture runner's umask 022 to replay frozen file modes.
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/stage-e01-core-adoption.json")).unwrap();
    assert_eq!(
        fixture["reference"],
        "9ce2c2efcf10862b907f7c801b8ff40a9dbfb04f"
    );
    assert_eq!(
        fixture["reference_patch"],
        json!({
            "src/mir/core/adoption/_filesystem.py": "77463d2151d68e11e177d61612217b2e50b0e8fd61c9c16f120a10c643503c13",
            "src/mir/core/adoption/runtime.py": "29cfc15e43004c60c2ce78225a7a147fa7d2fa5e5d742a7fad0fda41b86a617b",
            "src/mir/core/adoption/slim.py": "e9d8479dd3ac87cb6f02fb5391976cc031f87c3834231eb38ff955a8255eb8c3"
        })
    );
    let scratch = std::env::var_os("E01_SCRATCH").map_or_else(
        || Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/stage-e01"),
        PathBuf::from,
    );
    fs::create_dir_all(&scratch).unwrap();
    let temp = tempfile::Builder::new()
        .prefix("oracle-")
        .tempdir_in(scratch)
        .unwrap();
    let mut failures = Vec::new();
    let filter = std::env::var("E01_CASE").unwrap_or_default();
    for case in fixture["records"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        if !filter.is_empty() && !name.contains(&filter) {
            continue;
        }
        let root = temp.path().join(name).join("project");
        populate(&root, &case["initial"]);
        let external = root.parent().unwrap().join("external-cli");
        fs::write(&external, "synthetic cli").unwrap();
        fs::set_permissions(&external, fs::Permissions::from_mode(0o755)).unwrap();
        fs::create_dir(root.parent().unwrap().join("outside")).unwrap();
        if case["options"]["outside_permission"] == true {
            let outside = root.parent().unwrap().join("outside");
            fs::write(outside.join("secret"), "outside").unwrap();
            fs::set_permissions(outside, fs::Permissions::from_mode(0o0)).unwrap();
        }
        if case["options"]["race"].is_string() {
            for name in ["a", "z"] {
                fs::write(
                    root.parent().unwrap().join("outside").join(name),
                    format!("OUTSIDE-{}", name.to_uppercase()),
                )
                .unwrap();
            }
        }
        let release = [
            "config/adopter-boundary.json",
            "config/adopter-payload.json",
        ]
        .into_iter()
        .filter_map(|name| {
            fs::read(root.join(name))
                .ok()
                .map(|bytes| (name.to_owned(), bytes))
        })
        .collect();
        let mut host = Observer {
            root: root.clone(),
            external: external.clone(),
            options: case["options"].clone(),
            release,
            events: vec![],
            fd_counts: BTreeMap::new(),
            journal_calls: 0,
            swapped: false,
        };
        let initial_tree = snapshot(&root);
        let outside_tree = snapshot(&root.parent().unwrap().join("outside"));
        for (index, step) in case["steps"].as_array().unwrap().iter().enumerate() {
            host.events.clear();
            let input = rewrite(&step["input"], &root, &external, true);
            let result = match m::core_adoption_operation(
                &root,
                step["operation"].as_str().unwrap(),
                &input,
                &mut host,
            ) {
                Ok(v) => json!({"value":v}),
                Err(e) => json!({"error":[e.class,e.message]}),
            };
            if case.get("native_decline").is_some() {
                assert_eq!(
                    result["error"][0], "NotImplementedError",
                    "{name}: {result}"
                );
                assert_eq!(
                    snapshot(&root),
                    initial_tree,
                    "{name}: declined after changing the tree"
                );
                assert!(
                    host.events.is_empty(),
                    "{name}: unsupported input reached subprocess or mutation"
                );
                continue;
            }
            let actual = json!({"result":rewrite(&result,&root,&external,false),"events":host.events,"tree":snapshot(&root)});
            if case["options"]["race"].is_string() {
                assert!(host.swapped, "{name}: race seam was not reached");
                assert_eq!(
                    snapshot(&root.parent().unwrap().join("outside")),
                    outside_tree,
                    "{name}: outside tree changed"
                );
            }
            let expected = &case["expected"][index];
            if actual != *expected {
                for key in ["result", "events", "tree"] {
                    if actual[key] != expected[key] {
                        failures.push(format!(
                            "{name}[{index}].{key}\nexpected: {}\nactual: {}",
                            expected[key], actual[key]
                        ));
                    }
                }
            }
        }
    }
    make_accessible(temp.path());
    assert!(
        failures.is_empty(),
        "{} mismatches:\n{}",
        failures.len(),
        failures.join("\n\n")
    );
}

#[test]
fn unsafe_direct_journal_declines_before_filesystem_access() {
    let scratch = std::env::var_os("E01_SCRATCH").map_or_else(
        || Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/stage-e01"),
        PathBuf::from,
    );
    fs::create_dir_all(&scratch).unwrap();
    let temp = tempfile::Builder::new()
        .prefix("guard-")
        .tempdir_in(scratch)
        .unwrap();
    let root = temp.path().join("missing");
    let sentinel = temp.path().join("escape");
    fs::write(&sentinel, b"outside").unwrap();
    let mut host = Observer {
        root: root.clone(),
        external: temp.path().join("external"),
        options: json!({}),
        release: BTreeMap::new(),
        events: vec![],
        fd_counts: BTreeMap::new(),
        journal_calls: 0,
        swapped: false,
    };
    let result = m::core_adoption_operation(
        &root,
        "rollback_journal",
        &json!({"journal": {
        "transaction_id": "a".repeat(32), "paths": ["../escape"]}}),
        &mut host,
    );
    assert_eq!(result.unwrap_err().class, "NotImplementedError");
    assert!(!root.exists());
    assert_eq!(fs::read(sentinel).unwrap(), b"outside");
    assert!(host.events.is_empty());
}
