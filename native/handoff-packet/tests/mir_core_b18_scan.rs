use handoff_packet::mir_cli::context::do_sync;
use handoff_packet::mir_core::memory::{external_store as es, store};
use serde_json::{Value, json};
use std::path::Path;
#[path = "support/external_replay.rs"]
mod support;
use support::{clean_paths, connect, rows, schema};

const CLOCK: &str = "2026-01-02T00:00:00+00:00";
fn clock() -> String {
    CLOCK.into()
}
fn write(root: &Path, name: &str, text: &[u8]) {
    let path = root.join(name);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(path, text).unwrap();
}
fn observed<T: serde::Serialize>(result: Result<T, es::HelperError>) -> Value {
    match result {
        Ok(v) => json!({"value": v}),
        Err(e) => json!({"error": [e.kind, e.message]}),
    }
}
fn state(c: &store::Connection, tmp: &Path) -> Value {
    let mut out = json!({});
    for table in [
        "external_archives",
        "external_documents",
        "external_chunks",
        "external_store_meta",
    ] {
        let mut stmt = c
            .conn
            .prepare(&format!("SELECT * FROM {table} ORDER BY 1"))
            .unwrap();
        let n = stmt.column_count();
        let rows = stmt
            .query_map([], |r| {
                (0..n)
                    .map(|i| {
                        Ok(match r.get_ref(i)? {
                            rusqlite::types::ValueRef::Null => Value::Null,
                            rusqlite::types::ValueRef::Integer(n) => json!(n),
                            rusqlite::types::ValueRef::Text(s) => {
                                let s = std::str::from_utf8(s)
                                    .unwrap()
                                    .replace(tmp.to_str().unwrap(), "<tmp>")
                                    .replace(CLOCK, "<clock>");
                                let s = if s.starts_with("<tmp>") {
                                    s.replace('\\', "/")
                                } else {
                                    s
                                };
                                if s.chars().count() > 100 {
                                    json!([
                                        s.chars().count(),
                                        es::chunk_text(&s, i64::MAX, 0).unwrap()[0].text_hash
                                    ])
                                } else {
                                    json!(s)
                                }
                            }
                            other => panic!("unexpected {other:?}"),
                        })
                    })
                    .collect::<Result<Vec<_>, rusqlite::Error>>()
            })
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        out[table] = json!(rows);
    }
    out["fts"] = json!(
        c.conn
            .query_row("SELECT count(*) FROM external_chunks_fts", [], |r| r
                .get::<_, i64>(0))
            .unwrap()
    );
    out["vectors"] = rows(
        &c.conn,
        "SELECT rowid,length(embedding) FROM external_chunks_vec ORDER BY rowid",
    );
    out
}
fn registration(root: &Path) -> es::Registration {
    es::Registration {
        slug: "sample".into(),
        root_path: root.to_str().unwrap().into(),
        mode: "indexed".into(),
        owner: "synthetic".into(),
        chunk_size: 8,
        chunk_overlap: 0,
        glob_include: vec![],
        glob_exclude: vec![],
        historical_glob: vec![],
    }
}
fn replay(name: &str, tmp: &Path) -> Value {
    let c = connect(&tmp.join("synthetic.db"));
    store::apply_migrations(&c.conn).unwrap();
    let db = es::ExternalStore::new(&c, &clock).unwrap();
    if let Some(mode) = name.strip_prefix("register.") {
        let mut a = registration(&tmp.join("archive"));
        match mode {
            "empty_slug" => a.slug.clear(),
            "odd_slug" => a.slug = "../a b".into(),
            "mode" => a.mode = "invalid".into(),
            "empty_root" => a.root_path.clear(),
            "size" => a.chunk_size = 0,
            "overlap" => a.chunk_overlap = 8,
            "negative" => a.chunk_overlap = -1,
            "file_root" => write(tmp, "archive", b"abcdefghij"),
            "missing_root" | "duplicate" => (),
            _ => panic!("unknown {mode}"),
        }
        let first = observed(db.register(&a));
        let mut result = json!({"first":first, "state":state(&c,tmp)});
        if mode == "duplicate" {
            a.owner = "changed".into();
            result["second"] = json!(db.register(&a).unwrap());
            result["after"] = state(&c, tmp);
        }
        if ["missing_root", "file_root", "size", "overlap", "negative"].contains(&mode) {
            if ["size", "overlap", "negative"].contains(&mode) {
                write(&tmp.join("archive"), "a.md", b"abcdefghij");
            }
            result["scan"] = json!(db.scan(1, None).unwrap());
            result["after"] = state(&c, tmp);
        }
        return json!({"value":result});
    }
    if let Some(mode) = name.strip_prefix("guard.") {
        let root = tmp.join("archive");
        write(&root, "a.md", b"abcdefghij");
        write(tmp, "outside.md", b"abcdefghij");
        write(&root, "bad.md", b"ab\xffcd");
        let names: &[&str] = if mode == "symlink" {
            #[cfg(unix)]
            {
                use std::os::unix::fs::symlink;
                symlink(root.join("a.md"), root.join("inner.md")).unwrap();
                symlink(tmp.join("outside.md"), root.join("outer.md")).unwrap();
                symlink(tmp, root.join("dir")).unwrap();
            }
            &["inner.md", "outer.md", "dir/outside.md"]
        } else {
            &[
                "a.md",
                "../outside.md",
                "sub/../a.md",
                "bad.md",
                "absent.md",
            ]
        };
        let id = db.register(&registration(&root)).unwrap();
        let row = db.fetch_archive(id).unwrap();
        let reads: Vec<Value> = names
            .iter()
            .map(|n| observed(db.read_file(&row, n)))
            .collect();
        let mut result = json!({"value":{
            "fetch":observed(db.fetch_archive(999).map(|_| Value::Null)),"read":reads}});
        clean_paths(&mut result, tmp);
        return result;
    }
    if let Some(mode) = name.strip_prefix("scan.") {
        let root = tmp.join("archive");
        for name in [
            "a.md",
            "b.md",
            "docs/decisions/c.md",
            "tasks/handoffs/h.md",
            ".ai-harness/rules/r.md",
            "docs/old.md",
            "skip.md",
            "note.txt",
        ] {
            write(&root, name, b"# Title\n\nabcdefghij");
        }
        write(&root, "empty.md", b"");
        write(&root, "docs/status.md", b"---\nstatus: archived\n---\nbody");
        if mode == "frontmatter" {
            write(
                &root,
                "docs/mirror.md",
                b"---\nsource: Mirrored-Summary\n---\nbody",
            );
            write(&root, "docs/dep.md", b"---\nstatus: Deprecated\n---\nbody");
            write(
                &root,
                "docs/live.md",
                b"---\nstatus: accepted\nsource: manual\n---\nbody",
            );
        }
        let mut a = registration(&root);
        if mode == "immutable" {
            a.mode = mode.into();
        }
        a.glob_include = vec!["**/*.md".into()];
        a.glob_exclude = vec!["skip.md".into()];
        a.historical_glob = vec!["docs/old.md".into()];
        let id = db.register(&a).unwrap();
        let batches = std::cell::RefCell::new(Vec::<Vec<String>>::new());
        let mut encode = |texts: &[String]| {
            batches.borrow_mut().push(texts.to_vec());
            if mode == "failure" && batches.borrow().len() == 2 {
                return Err(es::HelperError {
                    kind: "RuntimeError",
                    message: "synthetic mid-scan failure".into(),
                });
            }
            Ok(texts
                .iter()
                .map(|_| {
                    let mut v = vec![0.; es::DEFAULT_EMBED_DIM];
                    v[0] = 1.;
                    v
                })
                .collect())
        };
        let first = db
            .scan_with_vectors(id, Some(&mut encode), Some("fake"), Some(2))
            .unwrap();
        let mut result =
            json!({"first":first, "state":state(&c,tmp),"calls":batches.borrow().clone()});
        let persisted = connect(&tmp.join("synthetic.db"));
        result["committed"] = state(&persisted, tmp);
        drop(persisted);
        batches.borrow_mut().clear();
        match mode {
            "modified" | "immutable" => write(&root, "a.md", b"changed"),
            "deleted" => std::fs::remove_file(root.join("a.md")).unwrap(),
            "renamed" => std::fs::rename(root.join("a.md"), root.join("renamed.md")).unwrap(),
            "metadata" => {
                c.conn
                    .execute(
                        "DELETE FROM external_store_meta WHERE key != \
                    'external_embedding_fingerprint'",
                        [],
                    )
                    .unwrap();
                c.conn
                    .execute("UPDATE external_documents SET title='stale'", [])
                    .unwrap();
            }
            "content" | "history" | "exclude" => {
                match mode {
                    "content" => a.chunk_size = 4,
                    "history" => a.historical_glob.clear(),
                    "exclude" => a.glob_exclude.push("a.md".into()),
                    _ => unreachable!(),
                }
                db.register(&a).unwrap();
                result["sentinel"] = state(&c, tmp);
            }
            _ => (),
        }
        result["replay"] = json!(
            db.scan_with_vectors(id, Some(&mut encode), Some("fake"), Some(2))
                .unwrap()
        );
        result["after"] = state(&c, tmp);
        result["replay_calls"] = json!(batches.borrow().clone());
        return json!({"value":result});
    }
    if name == "index.direct" {
        let root = tmp.join("archive");
        write(&root, "a.md", "\u{e9}\u{4e2d}\n\n# Tail".as_bytes());
        let mut a = registration(&root);
        a.chunk_size = 4;
        a.chunk_overlap = 1;
        let id = db.register(&a).unwrap();
        let archive = db.fetch_archive(id).unwrap();
        let mut result = json!({"id":db.index_file(&archive,"a.md").unwrap(),
            "duplicate":observed(db.index_file(&archive,"a.md")),
            "missing":observed(db.index_file(&archive,"absent.md")),
            "state":state(&c,tmp)});
        for (k, v) in schema(&c.conn).as_object().unwrap() {
            result[k] = v.clone();
        }
        clean_paths(&mut result, tmp);
        return json!({"value":result});
    }
    if name == "sync.relative" {
        write(tmp, "one/a.md", b"abcdefghij");
        write(tmp, "two/b.md", b"abcdefghij");
        let archives: Vec<_> = [("one", "sub/../one"), ("two", "./two/")]
            .iter()
            .map(|(n, r)| {
                json!({"slug":n,"root":r,"mode":"indexed","glob_include":[],
                    "glob_exclude":[],"historical_glob":[],"chunk_size":8,"chunk_overlap":0})
            })
            .collect();
        let cfg = json!({"memory":{"external_archives":archives,
            "embedding":{"enabled":false}}});
        let (mut exits, mut stdout) = (vec![], String::new());
        for _ in 0..2 {
            let (code, text) = do_sync(&db, &cfg, tmp, &tmp.join("home")).unwrap();
            exits.push(code);
            stdout.push_str(&text);
        }
        return json!({"value":{"exits":exits,"stdout":stdout,"state":state(&c,tmp)}});
    }
    let mode = name.strip_prefix("sync.").unwrap();
    write(tmp, "one/a.md", b"abcdefghij");
    write(tmp, "two/b.md", b"abcdefghij");
    if mode == "failure" {
        write(tmp, "two/bad.md", &[255]);
    }
    let archives: Vec<_> = if mode == "empty" {
        vec![]
    } else {
        ["one", "missing", "two"]
            .iter()
            .map(|n| {
                json!({"slug":n,"root":n,"mode":"indexed","glob_include":[],
                    "glob_exclude":[],"historical_glob":[],"chunk_size":8,"chunk_overlap":0})
            })
            .collect()
    };
    let mut stdout = String::new();
    let mut exits = vec![];
    for _ in 0..2 {
        let cfg = json!({"memory":{"external_archives":archives,
            "embedding":{"enabled":false}}});
        let (code, text) = do_sync(&db, &cfg, tmp, &tmp.join("home")).unwrap();
        exits.push(code);
        stdout.push_str(&text);
    }
    json!({"value":{"args":{"action":"sync","db":"synthetic.db", "project_root":".",
        "reindex_missing_vectors":false},"exits":exits,"stdout":stdout,"state":state(&c,tmp)}})
}
#[test]
fn frozen_records() {
    let records: Value = serde_json::from_str(include_str!("fixtures/w2/b18-scan.json")).unwrap();
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        if cfg!(windows) && name == "guard.symlink" {
            // Unprivileged Windows processes cannot create the reference's symbolic links.
            exempt += 1;
            continue;
        }
        let tmp = tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap();
        assert_eq!(&replay(name, tmp.path()), expected, "{name}");
        replayed += 1;
    }
    let expected = if cfg!(windows) { (27, 1) } else { (28, 0) };
    assert_eq!((replayed, exempt), expected);
}
