use crate::{
    digest::sha256,
    git::{self, Query},
    guard::Guard,
    wire,
};
use regex::Regex;
use serde_json::{Value, json};
use std::{
    sync::LazyLock,
    time::{Instant, SystemTime, UNIX_EPOCH},
};

#[path = "../../handoff-packet/src/python_decimal.rs"]
mod python_decimal;
pub(crate) use python_decimal::decimal_digit;

pub const CONTRACT: &[u8] =
    include_bytes!("../../../plugins/mir-core/skills/ontology/references/common-contract.json");

pub(crate) fn ref_path(reference: &str) -> &str {
    let path = reference.split('#').next().unwrap_or("");
    line_ref(path).map_or(path, |(prefix, _)| prefix)
}

pub(crate) fn line_ref(path: &str) -> Option<(&str, &str)> {
    path.rsplit_once(':').filter(|(_, number)| {
        !number.is_empty() && number.chars().all(|c| decimal_digit(c).is_some())
    })
}

pub(crate) fn require_stable_unicode(text: &str) -> Result<(), &'static str> {
    // Supported CPython versions start with the Unicode 14 database. A newer
    // codepoint's classification depends on the configured reference version.
    static NEWER: LazyLock<Result<Regex, regex::Error>> =
        LazyLock::new(|| Regex::new(r"\P{Age:14.0}"));
    if !text.is_ascii() && NEWER.as_ref().map_err(|_| "E_FORMAT")?.is_match(text) {
        return Err("FORWARD");
    }
    Ok(())
}

pub(crate) fn guarded_refs(mapping: &Value, io: &mut Guard) -> Result<(), &'static str> {
    for (at, entry) in map_entries(mapping) {
        for (_, reference) in located_refs(entry, &at) {
            let path = reference.split('#').next().unwrap_or("");
            let raw = if let Some((prefix, number)) = line_ref(path) {
                require_stable_unicode(number)?;
                prefix
            } else {
                path
            };
            io.path(raw, true)?;
        }
    }
    Ok(())
}

/// JSON pointer and traversal order shared by all ontology tools.
pub(crate) fn pointer(at: &str, key: impl std::fmt::Display) -> String {
    format!(
        "{}/{}",
        at,
        key.to_string().replace('~', "~0").replace('/', "~1")
    )
}
pub(crate) fn map_entries(mapping: &Value) -> Vec<(String, &Value)> {
    let mut out = Vec::new();
    for section in [
        "canonical_index",
        "concepts",
        "relations",
        "domain",
        "questions",
        "error_cases",
        "vocabularies",
        "entrypoints",
        "knowledge_supply",
    ] {
        let value = &mapping[section];
        if section == "domain" && value.is_object() {
            if let Some(kinds) = value.as_object() {
                for (kind, entries) in kinds {
                    if let Some(entries) = entries.as_array() {
                        for (i, entry) in entries.iter().enumerate() {
                            out.push((pointer(&pointer("/domain", kind), i), entry));
                        }
                    }
                }
            }
        } else if section == "concepts" && value.is_object() {
            if let Some(entries) = value.as_object() {
                for (key, entry) in entries {
                    out.push((pointer("/concepts", key), entry));
                }
            }
        } else if let Some(entries) = value.as_array() {
            for (i, entry) in entries.iter().enumerate() {
                out.push((pointer(&format!("/{section}"), i), entry));
            }
        } else if section == "knowledge_supply" && value.is_object() {
            out.push(("/knowledge_supply".into(), value));
        }
    }
    out
}
pub(crate) fn located_refs(entry: &Value, at: &str) -> Vec<(String, String)> {
    let mut out = Vec::new();
    match entry {
        Value::String(s) => out.push((at.into(), s.clone())),
        Value::Array(items) => {
            for (i, item) in items.iter().enumerate() {
                out.extend(located_refs(item, &pointer(at, i)));
            }
        }
        Value::Object(items) => {
            for (key, item) in items {
                let loc = pointer(at, key);
                if matches!(key.as_str(), "ref" | "check" | "binding") && item.is_string() {
                    if key != "binding"
                        || !matches!(item.as_str(), Some("on_demand_stdio" | "resident_stdio"))
                    {
                        out.push((loc, item.as_str().unwrap_or_default().into()));
                    }
                } else if key == "evidence" && item.is_array() || item.is_object() {
                    out.extend(located_refs(item, &loc));
                } else if let Some(items) = item.as_array() {
                    for (i, item) in items.iter().enumerate() {
                        if item.is_array() || item.is_object() {
                            out.extend(located_refs(item, &pointer(&loc, i)));
                        }
                    }
                }
            }
        }
        _ => {}
    }
    out
}

// Python datetime.isoformat emits microseconds unless the fraction is zero.
fn observed_at() -> Result<String, &'static str> {
    timestamp(SystemTime::now())
}
fn timestamp(now: SystemTime) -> Result<String, &'static str> {
    let now = now.duration_since(UNIX_EPOCH).map_err(|_| "E_IO")?;
    let seconds = now.as_secs();
    let days = (seconds / 86400) as i64 + 719468;
    let era = days / 146097;
    let doe = days - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    let fraction = now.subsec_micros();
    let suffix = if fraction == 0 {
        String::new()
    } else {
        format!(".{fraction:06}")
    };
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}{suffix}Z",
        seconds / 3600 % 24,
        seconds / 60 % 60,
        seconds % 60
    ))
}

pub fn finalize(pins: &mut Value, paths: &[Value]) {
    let mut unknowns = pins["unknowns"].as_array().cloned().unwrap_or_default();
    let mut inventory = Vec::new();
    let mut add = |pin: String, pointer: String, kind: &str, required: bool, value: &Value| {
        let available = !value.is_null() && value != "" && value != "untracked";
        inventory.push(
            json!({"pin": pin, "pointer": pointer, "kind": kind, "required": required,
            "availability": if available { "available" } else { "unknown" }}),
        );
        let reason = Value::String(format!("{pin}: unavailable"));
        if required && !available && !unknowns.contains(&reason) {
            unknowns.push(reason);
        }
    };
    for (pin, key, kind) in [
        ("repository_root", "repository_root", "path"),
        ("head", "head", "commit"),
        ("mapping.identity", "mapping_path", "path"),
        ("mapping.version", "mapping_version", "version"),
        ("mapping.digest", "mapping_sha256", "sha256"),
        ("contract.identity", "contract_id", "id"),
        ("contract.version", "contract_version", "version"),
        ("contract.digest", "contract_sha256", "sha256"),
    ] {
        add(pin.into(), format!("/{key}"), kind, true, &pins[key]);
    }
    for (i, _) in paths.iter().enumerate() {
        let source = &pins["sources"][i];
        add(
            format!("sources[{i}].digest"),
            format!("/sources/{i}/sha256"),
            "sha256",
            true,
            &source["sha256"],
        );
        add(
            format!("sources[{i}].revision"),
            format!("/sources/{i}/revision"),
            "last_change_commit",
            false,
            &source["revision"],
        );
    }
    pins["unknowns"] = Value::Array(unknowns);
    pins["pin_inventory"] = Value::Array(inventory);
}

struct Git {
    preflight: Option<&'static str>,
    codes: Vec<Option<&'static str>>,
    failures: Vec<(String, String)>,
}
impl Git {
    fn query(
        &mut self,
        io: &mut Guard,
        unknowns: &mut Vec<Value>,
        label: &str,
        query: Query<'_>,
    ) -> Option<Value> {
        let (result, reason) = if let Some(code) = self.preflight {
            (None, code.into())
        } else {
            let start = Instant::now();
            let (result, code) = match git::run(io, query) {
                Ok(value) => (value, "E_GIT"),
                Err(code) => (None, code),
            };
            self.codes
                .push(if result.is_some() { None } else { Some(code) });
            (
                result,
                format!("{code} after {:.2} s", start.elapsed().as_secs_f64()),
            )
        };
        if result.is_none() {
            self.failures.push((label.into(), reason));
            unknowns.push(Value::String(format!("{label}: git command failed")));
        }
        result
    }
}

pub fn data(args: &Value, io: &mut Guard) -> Result<(Value, Option<&'static str>), &'static str> {
    let contract = wire::parse(CONTRACT)?;
    let mapping_raw = if io.exists(".mir/ontology-map.json")? {
        Some(io.read(".mir/ontology-map.json")?)
    } else {
        None
    };
    let mapping = if let Some(raw) = &mapping_raw {
        wire::parse(raw)?
    } else {
        json!({})
    };
    if !mapping.is_object() {
        return Err("E_FORMAT");
    }
    if let Some(declaration) = mapping.get("contract")
        && (!declaration.is_object()
            || ["id", "version", "version_range", "sha256"]
                .iter()
                .any(|key| {
                    declaration
                        .get(*key)
                        .is_some_and(|value| !value.is_string())
                }))
    {
        return Err("E_FORMAT");
    }
    guarded_refs(&mapping, io)?;
    let mut pins = json!({"repository_root": null, "head": null, "dirty": null, "sources": [],
        "mapping_path": mapping_raw.as_ref().map(|_| ".mir/ontology-map.json"),
        "mapping_version": mapping["contract"]["version"], "mapping_sha256": mapping_raw.as_deref().map(sha256),
        "contract_id": contract["contract_id"], "contract_version": contract["version"],
        "contract_sha256": sha256(CONTRACT), "observed_at": observed_at()?, "unknowns": []});
    let mut unknowns = Vec::new();
    for (key, value) in pins.as_object().ok_or("E_FORMAT")? {
        if value.is_null() && !matches!(key.as_str(), "repository_root" | "head" | "dirty") {
            unknowns.push(Value::String(format!("{key}: unavailable")));
        }
    }
    let root = io.root.to_str().ok_or("E_PATH")?;
    pins["repository_root"] = Value::String(root.into());
    let preflight = match git::preflight(io) {
        Ok(true) => None,
        Ok(false) => Some("E_GIT"),
        Err(code) => Some(code),
    };
    let mut runner = Git {
        preflight,
        codes: Vec::new(),
        failures: Vec::new(),
    };
    pins["head"] = runner
        .query(io, &mut unknowns, "head", Query::Head)
        .unwrap_or(Value::Null);
    pins["dirty"] = runner
        .query(io, &mut unknowns, "dirty", Query::Status)
        .unwrap_or(Value::Null);
    let paths = args["paths"].as_array().ok_or("E_SCHEMA")?;
    let mut sources = Vec::new();
    for raw in paths {
        let raw = raw.as_str().ok_or("E_SCHEMA")?;
        let path = io.path(raw, true)?;
        let relative = path
            .strip_prefix(&io.root)
            .map_err(|_| "E_PATH")?
            .to_str()
            .ok_or("E_PATH")?
            .replace('\\', "/");
        let mut source =
            json!({"path": relative, "revision": null, "sha256": null, "modified_vs_head": null});
        if !io.exists(raw)? {
            unknowns.push(Value::String(format!("{relative}: file unavailable")));
            sources.push(source);
            continue;
        }
        let payload = io.read(raw)?;
        source["sha256"] = Value::String(sha256(&payload));
        if let Some(revision) = runner.query(
            io,
            &mut unknowns,
            &format!("{relative}.revision"),
            Query::Log(&relative),
        ) {
            source["revision"] = if revision == "" {
                Value::String("untracked".into())
            } else {
                revision
            };
            if source["revision"] != "untracked" {
                source["revision_kind"] = Value::String("last_change_commit".into());
            }
        }
        if source["revision"] == "untracked" {
            unknowns.push(Value::String(format!(
                "{relative}.modified_vs_head: untracked"
            )));
        } else if !pins["head"].is_null() {
            source["modified_vs_head"] = runner
                .query(
                    io,
                    &mut unknowns,
                    &format!("{relative}.modified_vs_head"),
                    Query::Diff(&relative),
                )
                .unwrap_or(Value::Null);
        } else {
            unknowns.push(Value::String(format!(
                "{relative}.modified_vs_head: HEAD unavailable"
            )));
        }
        sources.push(source);
    }
    for item in &mut unknowns {
        for (label, reason) in runner.failures.iter().rev() {
            if *item == format!("{label}: git command failed") {
                *item = Value::String(format!("{label}: {reason}"));
                break;
            }
        }
    }
    pins["sources"] = Value::Array(sources);
    pins["unknowns"] = Value::Array(unknowns);
    finalize(&mut pins, paths);
    let git_error = if preflight.is_some() || !runner.codes.contains(&None) {
        preflight.or_else(|| runner.codes.first().copied().flatten())
    } else {
        None
    };
    Ok((pins, git_error))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn timestamp_has_python_utc_shape() {
        let timestamp = observed_at().unwrap_or_default();
        assert!(matches!(timestamp.len(), 20 | 27));
        assert_eq!(timestamp.get(4..5), Some("-"));
        assert_eq!(timestamp.get(10..11), Some("T"));
        assert!(timestamp.ends_with('Z'));
        assert_eq!(
            super::timestamp(UNIX_EPOCH),
            Ok("1970-01-01T00:00:00Z".into())
        );
        assert_eq!(
            super::timestamp(UNIX_EPOCH + std::time::Duration::new(951782400, 123456000)),
            Ok("2000-02-29T00:00:00.123456Z".into())
        );
    }
    #[test]
    fn required_inventory_is_stable_and_revision_is_optional() {
        let mut pins =
            json!({"unknowns": [], "sources": [{"sha256": "abc", "revision": "untracked"}]});
        finalize(&mut pins, &[json!("source")]);
        assert_eq!(pins["pin_inventory"].as_array().map(Vec::len), Some(10));
        assert_eq!(pins["pin_inventory"][9]["availability"], "unknown");
        assert_eq!(pins["pin_inventory"][9]["required"], false);
        assert_eq!(pins["unknowns"].as_array().map(Vec::len), Some(8));
        let once = pins.clone();
        finalize(&mut pins, &[json!("source")]);
        assert_eq!(pins, once);
    }
    #[test]
    fn refs_only_follow_declared_fields() {
        let refs: Vec<String> = located_refs(
            &json!({"binding": "on_demand_stdio", "endpoints": ["ignored"], "nested": [{"ref": "a#x"}], "evidence": ["b:12"]}),
            "",
        ).into_iter().map(|(_, reference)| reference).collect();
        assert_eq!(refs, ["a#x", "b:12"]);
        assert_eq!(ref_path("a:12#x"), "a");
        assert_eq!(ref_path("a:١٢#x"), "a");
        assert_eq!(ref_path("a:Ⅻ#x"), "a:Ⅻ");
    }
}
