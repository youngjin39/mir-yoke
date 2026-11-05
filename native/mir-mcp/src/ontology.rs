//! Guarded ontology projections with explicit Python-semantic fallback.
use crate::{checker::Checker, guard::Guard, handoff, pagination, wire};
use serde_json::{Value, json};
use std::collections::BTreeSet;

fn text(v: &Value, max: usize) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= max)
}
fn integer(v: &Value, max: u64) -> bool {
    v.as_u64().is_some_and(|n| (1..=max).contains(&n))
}
fn validate(name: &str, args: &Value) -> Result<(), &'static str> {
    let obj = args.as_object().ok_or("E_SCHEMA")?;
    let extra: &[&str] = match name {
        "ontology_validate" => &["scope"],
        "ontology_lookup" => &["query", "limit"],
        "ontology_impact" => &["paths"],
        _ => return Err("E_SCHEMA"),
    };
    if obj.keys().any(|k| {
        !["target_root", "cursor", "page_size"].contains(&k.as_str())
            && !extra.contains(&k.as_str())
    }) || !text(&args["target_root"], 4096)
        || args.get("cursor").is_some_and(|v| !text(v, 1024))
        || args.get("page_size").is_some_and(|v| !integer(v, 64))
    {
        return Err("E_SCHEMA");
    }
    match name {
        "ontology_validate"
            if args
                .get("scope")
                .is_some_and(|v| !matches!(v.as_str(), Some("contract" | "mapping" | "both"))) =>
        {
            return Err("E_SCHEMA");
        }
        "ontology_lookup"
            if !text(&args["query"], 256) || args.get("limit").is_some_and(|v| !integer(v, 16)) =>
        {
            return Err("E_SCHEMA");
        }
        "ontology_impact" => {
            let paths = args["paths"].as_array().ok_or("E_SCHEMA")?;
            if paths.is_empty()
                || paths.len() > 64
                || paths
                    .iter()
                    .enumerate()
                    .any(|(i, p)| !text(p, 4096) || paths[..i].contains(p))
            {
                return Err("E_SCHEMA");
            }
        }
        _ => {}
    }
    Ok(())
}
// Python numeric repr participates in word matching; do not approximate floats.
fn complex_number(v: &Value) -> bool {
    match v {
        Value::Number(n) => n.as_i64().is_none() && n.as_u64().is_none(),
        Value::Array(a) => a.iter().any(complex_number),
        Value::Object(o) => o.values().any(complex_number),
        _ => false,
    }
}
fn words(s: &str) -> BTreeSet<String> {
    s.split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|s| !s.is_empty())
        .map(str::to_ascii_lowercase)
        .collect()
}
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
        Value::Number(n) => n.as_f64() != Some(0.0),
    }
}
fn lookup(mapping: &Value, args: &Value) -> Result<Value, &'static str> {
    let query = args["query"].as_str().ok_or("E_SCHEMA")?;
    if !query.is_ascii() {
        return Err("FORWARD");
    }
    let terms = words(query);
    let mut matches = Vec::new();
    for (at, entry) in handoff::map_entries(mapping) {
        if !["/questions/", "/concepts/", "/domain/"]
            .iter()
            .any(|s| at.starts_with(s))
        {
            continue;
        }
        let text = serde_json::to_string(entry).map_err(|_| "E_FORMAT")?;
        if !at.is_ascii() || !text.is_ascii() || complex_number(entry) {
            return Err("FORWARD");
        }
        let tokens = words(&format!("{at} {text}"));
        let score = terms.intersection(&tokens).count();
        if score == 0 {
            continue;
        }
        let mut refs = Vec::new();
        for (_, reference) in handoff::located_refs(entry, &at) {
            if !refs.contains(&reference) {
                refs.push(reference);
            }
        }
        let label = if truthy(&entry["name"]) {
            &entry["name"]
        } else {
            &entry["label"]
        };
        matches.push(json!({"pointer":at,"score":score,"label":label.as_str().filter(|s| !s.is_empty()).unwrap_or(&at),"refs":refs}));
    }
    matches.sort_by_key(|m| std::cmp::Reverse(m["score"].as_u64().unwrap_or(0)));
    matches.truncate(args["limit"].as_u64().unwrap_or(3) as usize);
    Ok(
        json!({"contract":{"id":mapping["contract"]["id"],"version":mapping["contract"]["version"]},"matches":matches}),
    )
}
fn touches(path: &str, changed: &[Value]) -> bool {
    let parts: Vec<_> = path
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .collect();
    let normalized = if parts.is_empty() {
        ".".into()
    } else {
        parts.join("/")
    };
    changed.iter().filter_map(Value::as_str).any(|s| {
        s == normalized || s.starts_with(&format!("{}/", normalized.trim_end_matches('/')))
    })
}
fn impact(mapping: &Value, args: &Value, io: &mut Guard) -> Result<Value, &'static str> {
    // Malformed semantic entries can still project a numeric `ref`; preserve
    // Python's float spelling (and non-finite handling) through the reference.
    if complex_number(mapping) {
        return Err("FORWARD");
    }
    let changed = args["paths"].as_array().ok_or("E_SCHEMA")?;
    let mut affected = Vec::new();
    let mut affected_paths = BTreeSet::new();
    let mut stale = Vec::new();
    let mut checks = BTreeSet::new();
    let mut undeclared = Vec::new();
    for (at, entry) in handoff::map_entries(mapping) {
        let refs = handoff::located_refs(entry, &at);
        if refs
            .iter()
            .any(|(_, r)| touches(handoff::ref_path(r), changed))
        {
            affected
                .push(json!({"pointer":at,"refs":refs.iter().map(|(_, r)|r).collect::<Vec<_>>()}));
            affected_paths.extend(refs.iter().map(|(_, r)| handoff::ref_path(r).to_owned()));
            if at.starts_with("/domain/invariants/") && entry.is_object() {
                if let Some(check) = entry["check"].as_str() {
                    checks.insert(check.to_owned());
                } else if entry.get("check").is_none() {
                    undeclared.push(json!({"pointer":at,"ref":entry["ref"]}));
                }
            }
        }
        for (loc, r) in refs {
            let covered = loc.ends_with("/check")
                && entry.is_object()
                && (at.starts_with("/domain/invariants/")
                    || at.starts_with("/error_cases/") && entry["status"] == "covered");
            let mut checker = Checker::new();
            checker.ref_check(&json!(r), &loc, covered, io)?;
            for finding in checker.errors {
                stale.push(json!({"pointer":finding["pointer"],"ref":r,"code":"E_REF"}));
            }
        }
    }
    if let Some(cases) = mapping["error_cases"].as_array() {
        for case in cases {
            if case.is_object()
                && case["status"] == "covered"
                && let Some(r) = case["check"].as_str()
                && (touches(handoff::ref_path(r), changed)
                    || affected_paths
                        .iter()
                        .any(|p| touches(p, &[json!(handoff::ref_path(r))])))
            {
                checks.insert(r.to_owned());
            }
        }
    }
    Ok(
        json!({"affected_entries":affected,"checks_to_run":checks,"stale_refs":stale,"undeclared_check_links":undeclared,"revalidate":changed.contains(&json!(".mir/ontology-map.json"))}),
    )
}
pub fn execute(name: &str, args: &Value) -> Result<Value, &'static str> {
    validate(name, args)?;
    let mut io = Guard::new(args["target_root"].as_str().ok_or("E_SCHEMA")?)?;
    let mut bound = args.clone();
    bound
        .as_object_mut()
        .ok_or("E_SCHEMA")?
        .shift_remove("cursor");
    if let Some(paths) = args["paths"].as_array() {
        for p in paths {
            io.path(p.as_str().ok_or("E_SCHEMA")?, true)?;
        }
    }
    let contract = wire::parse(handoff::CONTRACT)?;
    let contract_only = name == "ontology_validate" && args["scope"] == "contract";
    let mapping = if contract_only {
        json!({})
    } else {
        let raw = io.read(".mir/ontology-map.json")?;
        std::str::from_utf8(&raw).map_err(|_| "E_IO")?;
        wire::parse(&raw)?;
        // The protocol validator retains number types only. Mapping semantics
        // require the original arbitrary-precision values.
        serde_json::from_slice(raw.strip_prefix(&[239, 187, 191]).unwrap_or(&raw))
            .map_err(|_| "E_FORMAT")?
    };
    if !mapping.is_object() || mapping.get("contract").is_some_and(|v| !v.is_object()) {
        return Err("E_FORMAT");
    }
    if ["id", "version", "version_range", "sha256"]
        .iter()
        .any(|k| mapping["contract"].get(*k).is_some_and(|v| !v.is_string()))
    {
        return Err("E_FORMAT");
    }
    handoff::guarded_refs(&mapping, &mut io)?;
    let (data, keys): (Value, &[&str]) = match name {
        "ontology_lookup" => (lookup(&mapping, args)?, &["matches"]),
        "ontology_impact" => (
            impact(&mapping, args, &mut io)?,
            &[
                "affected_entries",
                "checks_to_run",
                "stale_refs",
                "undeclared_check_links",
            ],
        ),
        _ => {
            let mut checker = Checker::new();
            if !contract_only {
                checker.mapping(&mapping, &mut io)?;
            }
            let mut findings = checker.errors.clone();
            findings.extend(checker.warnings.clone());
            let findings: Vec<Value> = findings
                .iter()
                .map(|f| json!({"code":f["code"],"pointer":f["pointer"]}))
                .collect();
            (
                json!({"valid":checker.errors.is_empty(),"contract_version":contract["version"],"mapping_version":mapping["contract"]["version"],"counts":{"errors":checker.errors.len(),"warnings":checker.warnings.len(),"refs":checker.checked_refs.len()},"findings":findings}),
                &["findings"],
            )
        }
    };
    io.tick()?;
    wire::parse(&pagination::compact(&data)?)?;
    let hash = pagination::binding(
        name,
        io.root.to_str().ok_or("E_PATH")?,
        &bound,
        &Value::Object(io.sources.clone()),
        &Value::Object(io.source_digests.clone()),
        handoff::CONTRACT,
    )?;
    pagination::page_tool(data, args, &hash, None, io.profile_protections, keys, false)
}
