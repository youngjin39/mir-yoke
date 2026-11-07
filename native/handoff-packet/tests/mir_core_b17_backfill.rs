use handoff_packet::mir_cli::context::do_sync_with_embedding;
use handoff_packet::mir_core::memory::{external_store as es, store};
use serde_json::{Value, json};
use std::{
    cell::{Cell, RefCell},
    path::Path,
};
#[path = "support/external_replay.rs"]
mod support;
use support::{connect, rows, schema};
fn clock() -> String {
    "2026-01-02T00:00:00+00:00".into()
}
fn observed<T: serde::Serialize>(result: Result<T, es::HelperError>) -> Value {
    match result {
        Ok(v) => json!({"value": v}),
        Err(e) => json!({"error": [e.kind,e.message]}),
    }
}
fn state(db: &es::ExternalStore<'_>, archive: i64) -> Value {
    let c = &db.connection.conn;
    json!({"coverage":db.vector_coverage(archive).unwrap(),
        "documents":rows(c, "SELECT relative_path,vec_indexed_at IS NOT NULL \
            FROM external_documents WHERE archive_id=1 ORDER BY relative_path"),
        "chunks":rows(c,"SELECT c.id,d.relative_path,c.chunk_index FROM external_chunks c \
            JOIN external_documents d ON d.id=c.document_id ORDER BY c.id"),
        "vectors":if db.connection.vec_available {rows(c,
            "SELECT rowid,length(embedding),substr(hex(embedding),1,16) \
            FROM external_chunks_vec ORDER BY rowid")} else {json!([])},
        "fingerprint":rows(c,"SELECT value FROM external_store_meta \
            WHERE key='external_embedding_fingerprint'")})
}
fn replay(name: &str, tmp: &Path) -> Value {
    let mode = name.split_once('.').unwrap().1;
    let missing = matches!(mode, "missing" | "cli_missing");
    let c = if missing {
        store::connect(
            &tmp.join("synthetic.db"),
            store::ConnectOptions {
                timeout: None,
                vec_loading: store::VecLoading::Unavailable("synthetic unavailable"),
            },
        )
        .unwrap()
    } else {
        connect(&tmp.join("synthetic.db"))
    };
    store::apply_migrations(&c.conn).unwrap();
    if name.starts_with("table.") {
        let create: Vec<_> = [2, 2, 3]
            .into_iter()
            .map(|dim| observed(es::ensure_external_vec_table(&c.conn, dim)))
            .collect();
        let mut result = schema(&c.conn);
        result["available"] = json!(c.vec_available);
        result["create"] = json!(create);
        return json!({"value":result});
    }
    let batches = RefCell::new(Vec::<Vec<String>>::new());
    let fault = Cell::new(true);
    let mut encode = |texts: &[String]| {
        batches.borrow_mut().push(texts.to_vec());
        let second = fault.get() && batches.borrow().len() == 2;
        if mode == "failure" && second {
            return Err(es::HelperError {
                kind: "RuntimeError",
                message: "synthetic backend failure".into(),
            });
        }
        let mut vectors: Vec<_> = texts
            .iter()
            .map(|_| {
                let mut v = vec![0.; es::DEFAULT_EMBED_DIM];
                v[0] = 1.;
                v
            })
            .collect();
        if mode == "dimension" && second {
            vectors[1] = vec![1.];
        }
        if mode == "count" && second {
            vectors.pop();
        }
        Ok(vectors)
    };
    let db = es::ExternalStore::new(&c, &clock).unwrap();
    let root = tmp.join("archive");
    std::fs::create_dir(&root).unwrap();
    let archive = db
        .register(&es::Registration {
            slug: "sample".into(),
            root_path: root.to_str().unwrap().into(),
            mode: "indexed".into(),
            owner: "synthetic".into(),
            chunk_size: 8,
            chunk_overlap: 0,
            glob_include: vec![],
            glob_exclude: vec![],
            historical_glob: vec![],
        })
        .unwrap();
    if mode == "adopt" {
        db.reindex_missing_vectors(archive, Some(&mut encode), "old")
            .unwrap();
    }
    if mode != "empty" {
        std::fs::write(root.join("a.md"), "alpha001alpha002alpha003").unwrap();
        let seed = matches!(
            mode,
            "seed" | "partial" | "mismatch" | "legacy" | "unstamped"
        );
        db.scan_with_vectors(
            archive,
            if seed { Some(&mut encode) } else { None },
            Some("model-a"),
            None,
        )
        .unwrap();
        for n in ["b", "c"] {
            std::fs::write(root.join(format!("{n}.md")), n.repeat(24)).unwrap();
        }
        std::fs::write(root.join("empty.md"), "").unwrap();
        db.scan(archive, None).unwrap();
    }
    match mode {
        "partial" => {
            c.conn
                .execute("DELETE FROM external_chunks_vec WHERE rowid=2", [])
                .unwrap();
        }
        "unstamped" => {
            c.conn
                .execute(
                    "UPDATE external_documents SET vec_indexed_at=NULL \
            WHERE relative_path='a.md'",
                    [],
                )
                .unwrap();
        }
        "legacy" => {
            c.conn
                .execute(
                    "DELETE FROM external_store_meta \
            WHERE key='external_embedding_fingerprint'",
                    [],
                )
                .unwrap();
        }
        "changed" | "cli_changed" => {
            std::fs::write(root.join("b.md"), "changed since sync").unwrap();
        }
        _ => (),
    }
    batches.borrow_mut().clear();
    let mut result = json!({"before":state(&db,archive)});
    let fingerprint = match mode {
        "mismatch" => "model-b",
        "blank" => "",
        _ => "model-a",
    };
    if mode.starts_with("cli") {
        let cfg = json!({"memory":{"embedding":{
            "enabled":mode!="cli_disabled","fingerprint":fingerprint}}});
        let backend = match mode {
            "cli_backend_failure" => Err(es::HelperError {
                kind: "RuntimeError",
                message: "synthetic backend unavailable".into(),
            }),
            "cli_no_backend" => Ok(None),
            _ => Ok(Some(&mut encode as &mut es::EmbedFn<'_>)),
        };
        let (exit, stdout) =
            do_sync_with_embedding(&db, &cfg, tmp, &tmp.join("home"), true, || backend).unwrap();
        result["exit"] = json!(exit);
        result["stdout"] = json!(stdout);
    } else {
        result["first"] = observed(db.reindex_missing_vectors(
            archive,
            if mode == "no_backend" {
                None
            } else {
                Some(&mut encode)
            },
            fingerprint,
        ));
    }
    result["after"] = state(&db, archive);
    result["batches"] = json!(batches.borrow().clone());
    if matches!(
        mode,
        "normal" | "seed" | "partial" | "adopt" | "empty" | "unstamped"
    ) {
        batches.borrow_mut().clear();
        result["replay"] = json!(
            db.reindex_missing_vectors(archive, Some(&mut encode), fingerprint)
                .unwrap()
        );
        result["replay_batches"] = json!(batches.borrow().clone());
        result["replay_state"] = state(&db, archive);
    }
    if matches!(mode, "failure" | "dimension" | "count") {
        batches.borrow_mut().clear();
        fault.set(false);
        result["resume"] = json!(
            db.reindex_missing_vectors(archive, Some(&mut encode), fingerprint)
                .unwrap()
        );
        result["resume_batches"] = json!(batches.borrow().clone());
    }
    drop(c);
    if !missing {
        let c = connect(&tmp.join("synthetic.db"));
        result["persisted"] = state(&es::ExternalStore::new(&c, &clock).unwrap(), archive);
    }
    json!({"value":result})
}
// Plain sync: embedding factory failure policy and the optional FTS-only retry.
fn replay_sync(mode: &str, tmp: &Path) -> Value {
    let c = connect(&tmp.join("synthetic.db"));
    store::apply_migrations(&c.conn).unwrap();
    let db = es::ExternalStore::new(&c, &clock).unwrap();
    let root = tmp.join("archive");
    std::fs::create_dir(&root).unwrap();
    let archive = db
        .register(&es::Registration {
            slug: "sample".into(),
            root_path: root.to_str().unwrap().into(),
            mode: "indexed".into(),
            owner: "synthetic".into(),
            chunk_size: 8,
            chunk_overlap: 0,
            glob_include: vec![],
            glob_exclude: vec![],
            historical_glob: vec![],
        })
        .unwrap();
    std::fs::write(root.join("a.md"), "alpha001alpha002").unwrap();
    let batches = RefCell::new(Vec::<Vec<String>>::new());
    let mut encode = |texts: &[String]| -> Result<Vec<Vec<f64>>, es::HelperError> {
        batches.borrow_mut().push(texts.to_vec());
        Err(es::HelperError {
            kind: "RuntimeError",
            message: "synthetic encode failure".into(),
        })
    };
    let vector_mode = if matches!(mode, "vector_required" | "required_encode") {
        "required"
    } else {
        "optional"
    };
    let cfg = json!({"memory":{"embedding":{"enabled":true,"required":mode == "required",
        "fingerprint":"model-a"},"vector_mode":vector_mode}});
    let backend = if matches!(mode, "required" | "vector_required" | "degraded") {
        Err(es::HelperError {
            kind: "RuntimeError",
            message: "synthetic backend unavailable".into(),
        })
    } else {
        Ok(Some(&mut encode as &mut es::EmbedFn<'_>))
    };
    let (exit, stdout) =
        do_sync_with_embedding(&db, &cfg, tmp, &tmp.join("home"), false, || backend).unwrap();
    let after = state(&db, archive);
    json!({"value":{"exit":exit,"stdout":stdout,"batches":batches.borrow().clone(),
        "after":after}})
}
#[test]
fn frozen_backfill_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b17-backfill.json")).unwrap();
    let mut replayed = 0;
    for (name, expected) in records.as_object().unwrap() {
        let tmp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        let mut actual = match name.strip_prefix("sync.") {
            Some(mode) => replay_sync(mode, tmp.path()),
            None => replay(name, tmp.path()),
        };
        support::clean_paths(&mut actual, tmp.path());
        assert_eq!(&actual, expected, "{name}");
        replayed += 1;
        eprintln!("{name}: replayed");
    }
    assert_eq!(replayed, 28);
    eprintln!("28 records replayed, 0 exempt");
}
