use handoff_packet::mir_core::config::{defaults::*, loader::*};
use serde_json::{Value, json};

use std::{fs, path::Path};
const R4: &str =
    "R4: Python importlib.metadata entry points have no native counterpart; owner decision open.";
const EXEMPT: &[(&str, &str)] = &[
    ("provider.create-allowed", R4),
    ("provider.create-default", R4),
    ("provider.create-denied", R4),
    ("registry.AgentRegistry.broken", R4),
    ("registry.AgentRegistry.empty", R4),
    ("registry.AgentRegistry.normal", R4),
    ("registry.AgentRegistry.unknown", R4),
    ("registry.EmbeddingBackendRegistry.broken", R4),
    ("registry.EmbeddingBackendRegistry.empty", R4),
    ("registry.EmbeddingBackendRegistry.normal", R4),
    ("registry.EmbeddingBackendRegistry.unknown", R4),
    ("registry.ProviderRegistry.broken", R4),
    ("registry.ProviderRegistry.empty", R4),
    ("registry.ProviderRegistry.normal", R4),
    ("registry.ProviderRegistry.unknown", R4),
    ("registry.SkillRegistry.broken", R4),
    ("registry.SkillRegistry.empty", R4),
    ("registry.SkillRegistry.normal", R4),
    ("registry.SkillRegistry.unknown", R4),
    ("registry.base", R4),
];
// R4: Python importlib.metadata entry points have no native counterpart; owner decision open.
fn observed(result: Result<Value, ConfigLoadError>) -> Value {
    match result {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":[e.class, e.message]}),
    }
}
fn run(name: &str, root: &Path) -> Value {
    if name == "defaults.all" {
        return json!({"value": all_defaults()});
    }
    if let Some(case) = name.strip_prefix("archive_root.") {
        // Distinct project and home roots; cwd is not an input of the native resolver.
        let authored = match case {
            "relative" => "notes",
            "home" => "~/notes",
            "parent" => "../shared",
            "dot" => "./a/./b",
            _ => panic!("{name}"),
        };
        let (project, home) = (root.join("project"), root.join("home"));
        for path in [&project, &home, &root.join("cwd")] {
            fs::create_dir(path).unwrap();
        }
        let archive =
            ExternalArchiveConfig::from_dict(&json!({"slug": "a", "root": authored})).unwrap();
        let resolved = resolve_archive_root(&project, &archive, &home);
        return observed(resolved.map(|p| json!(p.to_str().unwrap())));
    }
    if let Some(mode) = name.strip_prefix("path.") {
        // Reference slices mode[3:], including the ':' in raw cases.
        let root_text = root.to_str().unwrap();
        let root_text = root_text.strip_prefix(r"\\?\").unwrap_or(root_text);
        let authored = mode[3..].replace("ABS", root_text);
        let path = if mode.starts_with("db:") {
            resolve_memory_db(
                root,
                &ResolvedConfig::from_dict(&json!({"memory":{"db_path":authored}})).unwrap(),
                root,
            )
        } else if mode.starts_with("raw") {
            resolve_path(root, &authored, root)
        } else {
            resolve_archive_root(
                root,
                &ExternalArchiveConfig::from_dict(&json!({"slug":"a","root":authored})).unwrap(),
                root,
            )
        };
        return observed(path.map(|p| json!(p.to_str().unwrap())));
    }
    if let Some(mode) = name.strip_prefix("overlap.") {
        let (a, b) = mode.split_once('.').unwrap();
        return json!({"value": paths_overlap(&root.join(a), &root.join(b))});
    }
    if name.starts_with("load.") || name.starts_with("archive_set.") {
        let case = name.split_once('.').unwrap().1;
        let body = match case {
            "missing" | "directory" => None,
            "empty" | "read" => Some(""),
            "memory" => Some("[memory]\n"),
            "other" => Some("[other]\nx=1"),
            "unknown" => Some("[memory]\nx=1"),
            "wrong" => Some("memory=\"bad\""),
            "toml" => Some("["),
            "invalid" => Some("[memory]\nenabled=false"),
            "embedding" => Some("[memory.embedding]\n"),
            "archives" => Some("[memory]\nexternal_archives=[]"),
            "disabled" => Some("[memory]\nenabled=false\nrequired=false"),
            "env" => Some("[memory]\nplugin_mode=\"auto\""),
            _ => None,
        };
        if let Some(body) = body {
            fs::write(root.join("harness_a.toml"), body).unwrap();
        }
        if case == "directory" {
            fs::create_dir(root.join("harness_a.toml")).unwrap();
        }
        if name.starts_with("archive_set.") {
            let pairs: &[(&str, &str)] = match case {
                "empty" => &[],
                "distinct" => &[("a", "a"), ("b", "b")],
                "duplicate" => &[("a", "a"), ("a", "b")],
                "overlap" => &[("a", "a"), ("b", "a/b")],
                _ => panic!("{name}"),
            };
            let body: String = pairs
                .iter()
                .map(|(s, r)| format!("[[memory.external_archives]]\nslug=\"{s}\"\nroot=\"{r}\"\n"))
                .collect();
            fs::write(root.join("harness_a.toml"), body).unwrap();
        }
        // The loader takes no environment (the reference reads none), so the recorded
        // getenv calls and environ reads are empty by construction; `env` sets none.
        let result = if case == "read" {
            load_config_with_reader(Some(root), root, root, |_| {
                Err(std::io::Error::new(
                    std::io::ErrorKind::PermissionDenied,
                    "denied",
                ))
            })
        } else {
            load_config(None, root, root)
        };
        return observed(result.map(|v| json!([v.to_dict(), [], []])));
    }
    let (model, data) = if let Some(rest) = name.strip_prefix("model.") {
        let (model, case) = rest.split_once('.').unwrap();
        let mut data = if model == "archive" {
            json!({"slug":"a","root":"archive"})
        } else {
            json!({})
        };
        if case == "unknown" {
            data["unknown"] = json!(1);
        }
        (model, data)
    } else {
        let (model, field) = name.split_once('.').unwrap();
        let mut data = if model == "archive" {
            json!({"slug":"a","root":"archive"})
        } else {
            json!({})
        };
        let values = json!({
            "embedding":{"required":true,"backend":"bad","dim":0,"timeout_sec":-1,"norm_tolerance":0,"enabled":true,"base_url":[],"model":3},
            "archive":{"slug":"Bad","root":" ","mode":"bad","chunk_size":49,"chunk_overlap":800,"glob_include":3},
            "memory":{"enabled":false,"db_path":" ","vector_mode":"required","plugin_mode":"bad","recall_policy":"bad","backend":"bad","embedding":{"enabled":true,"fingerprint":"fp"}}
        });
        if field == "dim_policy" {
            data = json!({"dim":8});
        } else if field == "valid" {
            data = json!({"enabled":true,"required":true,"fingerprint":" fp "});
        } else if field == "coerce" {
            data = json!({"dim":"1024","enabled":"false"});
        } else {
            data[field] = values[model][field].clone();
        }
        (model, data)
    };
    // Archive input insertion order follows the Python case, independent of JSON map sorting.
    let result = match model {
        "embedding" => EmbeddingConfig::from_dict(&data).map(|v| v.to_dict()),
        "archive" => ExternalArchiveConfig::from_dict(&data).map(|v| v.to_dict()),
        "memory" => MemoryConfig::from_dict(&data).map(|v| v.to_dict()),
        "resolved" => ResolvedConfig::from_dict(&data).map(|v| v.to_dict()),
        _ => panic!("{name}"),
    };
    observed(result.map_err(|e| validation_error(model, &data, e)))
}
#[test]
fn frozen_config_records() {
    let records: Value = serde_json::from_str(include_str!("fixtures/w2/b02-config.json")).unwrap();
    for (name, reason) in EXEMPT {
        assert!(records.get(name).is_some(), "{name}: {reason}");
    }
    let mut replayed = 0;
    for (name, expected) in records.as_object().unwrap() {
        if EXEMPT.iter().any(|(key, _)| key == name) {
            continue;
        }
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path().canonicalize().unwrap();
        let mut actual = run(name, &root);
        normalize_paths(&mut actual, root.to_str().unwrap());
        assert_eq!(&actual, expected, "{name}");
        replayed += 1;
    }
    assert_eq!(
        (replayed, EXEMPT.len(), records.as_object().unwrap().len()),
        (67, 20, 87)
    );
}
fn normalize_paths(value: &mut Value, root: &str) {
    // Windows verbatim prefixes are not part of the oracle's temporary-root placeholder.
    let root = root.strip_prefix(r"\\?\").unwrap_or(root);
    match value {
        Value::String(s) if s.contains(root) || s.contains("<tmp>") => {
            *s = s
                .replace(r"\\?\", "")
                .replace(root, "<tmp>")
                .replace('\\', "/");
        }
        Value::Array(items) => items.iter_mut().for_each(|v| normalize_paths(v, root)),
        Value::Object(items) => items.values_mut().for_each(|v| normalize_paths(v, root)),
        _ => (),
    }
}
#[test]
fn injected_roots_are_independent() {
    let tmp = tempfile::tempdir().unwrap();
    let base = tmp.path().canonicalize().unwrap();
    let (root, home, cwd) = (base.join("project"), base.join("home"), base.join("cwd"));
    for path in [&root, &home, &cwd] {
        fs::create_dir(path).unwrap();
    }
    fs::write(root.join("harness_a.toml"), "[memory]\nplugin_mode='auto'").unwrap();
    let cfg = load_config(Some(&root), &home, &cwd).unwrap();
    assert_eq!(cfg.to_dict()["memory"]["plugin_mode"], "auto");
    assert_eq!(
        load_config(None, &home, &cwd).unwrap().to_dict()["memory"]["plugin_mode"],
        "disabled"
    );
    let archive = ExternalArchiveConfig::from_dict(&json!({"slug":"a","root":"notes"})).unwrap();
    assert_eq!(
        resolve_archive_root(&root, &archive, &home).unwrap(),
        root.join("notes")
    );
    assert_eq!(
        resolve_path(&root, "~/notes", &home).unwrap(),
        home.join("notes")
    );
}
