use crate::{
    digest::sha256,
    git::{self, Query},
    guard::Guard,
    wire,
};
use serde_json::{Value, json};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub const CONTRACT: &[u8] =
    include_bytes!("../../../plugins/mir-core/skills/ontology/references/common-contract.json");

fn ref_path(reference: &str) -> &str {
    let path = reference.split('#').next().unwrap_or("");
    if let Some((prefix, number)) = path.rsplit_once(':')
        && !number.is_empty()
        && number.chars().all(decimal)
    {
        return prefix;
    }
    path
}

// Unicode decimal digits (Python regex \d), rather than the broader numeric
// category, which includes superscripts and Roman numerals.
fn decimal(c: char) -> bool {
    matches!(c as u32,
        0x30..=0x39 | 0x660..=0x669 | 0x6f0..=0x6f9 | 0x7c0..=0x7c9 | 0x966..=0x96f |
        0x9e6..=0x9ef | 0xa66..=0xa6f | 0xae6..=0xaef | 0xb66..=0xb6f | 0xbe6..=0xbef |
        0xc66..=0xc6f | 0xce6..=0xcef | 0xd66..=0xd6f | 0xde6..=0xdef | 0xe50..=0xe59 |
        0xed0..=0xed9 | 0xf20..=0xf29 | 0x1040..=0x1049 | 0x1090..=0x1099 | 0x17e0..=0x17e9 |
        0x1810..=0x1819 | 0x1946..=0x194f | 0x19d0..=0x19d9 | 0x1a80..=0x1a89 | 0x1a90..=0x1a99 |
        0x1b50..=0x1b59 | 0x1bb0..=0x1bb9 | 0x1c40..=0x1c49 | 0x1c50..=0x1c59 | 0xa620..=0xa629 |
        0xa8d0..=0xa8d9 | 0xa900..=0xa909 | 0xa9d0..=0xa9d9 | 0xa9f0..=0xa9f9 | 0xaa50..=0xaa59 |
        0xabf0..=0xabf9 | 0xff10..=0xff19 | 0x104a0..=0x104a9 | 0x10d30..=0x10d39 | 0x10d40..=0x10d49 |
        0x11066..=0x1106f | 0x110f0..=0x110f9 | 0x11136..=0x1113f | 0x111d0..=0x111d9 |
        0x112f0..=0x112f9 | 0x11450..=0x11459 | 0x114d0..=0x114d9 | 0x11650..=0x11659 |
        0x116c0..=0x116c9 | 0x116d0..=0x116e3 | 0x11730..=0x11739 | 0x118e0..=0x118e9 |
        0x11950..=0x11959 | 0x11bf0..=0x11bf9 | 0x11c50..=0x11c59 | 0x11d50..=0x11d59 |
        0x11da0..=0x11da9 | 0x11f50..=0x11f59 | 0x16130..=0x16139 | 0x16a60..=0x16a69 |
        0x16ac0..=0x16ac9 | 0x16b50..=0x16b59 | 0x16d70..=0x16d79 | 0x1ccf0..=0x1ccf9 |
        0x1d7ce..=0x1d7ff | 0x1e140..=0x1e149 | 0x1e2f0..=0x1e2f9 | 0x1e4f0..=0x1e4f9 |
        0x1e5f1..=0x1e5fa | 0x1e950..=0x1e959 | 0x1fbf0..=0x1fbf9)
}

fn entry_refs(entry: &Value, refs: &mut Vec<String>) {
    match entry {
        Value::String(value) => refs.push(value.clone()),
        Value::Array(values) => {
            for value in values {
                entry_refs(value, refs);
            }
        }
        Value::Object(values) => {
            for (key, value) in values {
                if matches!(key.as_str(), "ref" | "check") {
                    if let Some(value) = value.as_str() {
                        refs.push(value.into());
                        continue;
                    }
                } else if key == "binding" {
                    if let Some(value) = value.as_str() {
                        if !matches!(value, "on_demand_stdio" | "resident_stdio") {
                            refs.push(value.into());
                        }
                        continue;
                    }
                } else if key == "evidence" && value.is_array() {
                    entry_refs(value, refs);
                    continue;
                }
                if value.is_object() {
                    entry_refs(value, refs);
                } else if let Some(values) = value.as_array() {
                    for value in values {
                        if value.is_array() || value.is_object() {
                            entry_refs(value, refs);
                        }
                    }
                }
            }
        }
        _ => {}
    }
}

fn guarded_refs(mapping: &Value, io: &mut Guard) -> Result<(), &'static str> {
    let mut entries = Vec::new();
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
            if let Some(values) = value.as_object() {
                for value in values.values() {
                    if let Some(items) = value.as_array() {
                        entries.extend(items);
                    }
                }
            }
        } else if section == "concepts" && value.is_object() {
            if let Some(values) = value.as_object() {
                entries.extend(values.values());
            }
        } else if let Some(values) = value.as_array() {
            entries.extend(values);
        } else if section == "knowledge_supply" && value.is_object() {
            entries.push(value);
        }
    }
    let mut refs = Vec::new();
    for entry in entries {
        entry_refs(entry, &mut refs);
    }
    for reference in refs {
        io.path(ref_path(&reference), true)?;
    }
    Ok(())
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
        let mut refs = Vec::new();
        entry_refs(
            &json!({"binding": "on_demand_stdio", "endpoints": ["ignored"], "nested": [{"ref": "a#x"}], "evidence": ["b:12"]}),
            &mut refs,
        );
        assert_eq!(refs, ["a#x", "b:12"]);
        assert_eq!(ref_path("a:12#x"), "a");
        assert_eq!(ref_path("a:١٢#x"), "a");
        assert_eq!(ref_path("a:Ⅻ#x"), "a:Ⅻ");
    }
}
