use handoff_packet::mir_core::memory::{external_store::*, store};
use serde_json::Value;
use std::{fs, process::Command};

#[test]
fn crlf_pull_console_matches_python_bytes() {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/y-e8-crlf.json")).unwrap();
    let pull = &fixture["pull"];
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    fs::create_dir(root.join("notes")).unwrap();
    // Preserve the CRLF bytes even on macOS; text-mode writes hide this regression.
    fs::write(root.join("notes/0.md"), pull["body"].as_str().unwrap()).unwrap();
    fs::write(
        root.join("harness_a.toml"),
        pull["config"].as_str().unwrap(),
    )
    .unwrap();
    let c = store::connect(
        &root.join("memory.db"),
        store::ConnectOptions {
            timeout: None,
            vec_loading: store::VecLoading::Bundled,
        },
    )
    .unwrap();
    store::apply_migrations(&c.conn).unwrap();
    let clock = || "2026-11-15T00:00:00Z".into();
    let es = ExternalStore::new(&c, &clock).unwrap();
    let aid = es
        .register(&Registration {
            slug: "notes".into(),
            root_path: root.join("notes").to_str().unwrap().into(),
            mode: "indexed".into(),
            owner: "synthetic".into(),
            glob_include: vec![],
            glob_exclude: vec![],
            historical_glob: vec![],
            chunk_size: 800,
            chunk_overlap: 100,
        })
        .unwrap();
    es.scan(aid, None).unwrap();
    drop(c);
    let out = Command::new(env!("CARGO_BIN_EXE_mir"))
        .args(["context", "pull", "apple", "--db", "memory.db", "--k", "1"])
        .current_dir(&root)
        .env_clear()
        .envs(
            ["SystemRoot", "WINDIR", "HOME", "MIR_HUB_DB_PATH"]
                .into_iter()
                .filter_map(|key| std::env::var_os(key).map(|value| (key, value))),
        )
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(0), "{out:?}");
    let key = if cfg!(windows) {
        "stdout_windows"
    } else {
        "stdout"
    };
    assert_eq!(out.stdout, pull[key].as_str().unwrap().as_bytes());
    assert!(out.stderr.is_empty(), "{out:?}");
}
