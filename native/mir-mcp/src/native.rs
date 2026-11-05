//! Bounded native tool boundary with explicit semantic fallback.
use crate::{guard::Guard, handoff, pagination};
use serde_json::{Value, json};
fn validate(args: &Value) -> Result<(), &'static str> {
    let obj = args.as_object().ok_or("E_SCHEMA")?;
    if obj
        .keys()
        .any(|k| !["target_root", "paths", "cursor", "page_size"].contains(&k.as_str()))
    {
        return Err("E_SCHEMA");
    }
    let text = |v: &Value, max| v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= max);
    if !text(&args["target_root"], 4096)
        || args.get("cursor").is_some_and(|v| !text(v, 1024))
        || args
            .get("page_size")
            .is_some_and(|v| !v.as_u64().is_some_and(|n| (1..=64).contains(&n)))
    {
        return Err("E_SCHEMA");
    }
    let paths = args["paths"].as_array().ok_or("E_SCHEMA")?;
    if paths.is_empty()
        || paths.len() > 16
        || paths.iter().any(|v| !text(v, 4096))
        || paths
            .iter()
            .enumerate()
            .any(|(i, v)| paths[..i].contains(v))
    {
        return Err("E_SCHEMA");
    }
    Ok(())
}
fn execute(args: &Value) -> Result<Value, &'static str> {
    validate(args)?;
    let mut io = Guard::new(args["target_root"].as_str().ok_or("E_SCHEMA")?)?;
    let mut bound_args = args.clone();
    bound_args
        .as_object_mut()
        .ok_or("E_SCHEMA")?
        .shift_remove("cursor");
    for path in args["paths"].as_array().ok_or("E_SCHEMA")? {
        io.path(path.as_str().ok_or("E_SCHEMA")?, true)?;
    }
    let (data, error) = handoff::data(&bound_args, &mut io)?;
    io.tick()?;
    // Apply the same structure bounds to generated tool data as to parsed JSON.
    crate::wire::parse(&pagination::compact(&data)?)?;
    let hash = pagination::binding(
        "handoff_pins",
        io.root.to_str().ok_or("E_PATH")?,
        &bound_args,
        &Value::Object(io.sources.clone()),
        &Value::Object(io.source_digests.clone()),
        handoff::CONTRACT,
    )?;
    pagination::page(data, args, &hash, error, io.profile_protections)
}
pub static TIMED_OUT: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
pub fn call(name: &str, args: &Value) -> Value {
    // A filesystem call can block without returning to Guard::tick. Bound the
    // entire operation, then terminate after flushing a timeout response so an
    // abandoned reader can never overlap a later request.
    let cloud_root = args["target_root"].as_str().map(std::path::PathBuf::from);
    let args = args.clone();
    let name = name.to_owned();
    let completed = bounded(std::time::Duration::from_secs(10), move || {
        if name == "handoff_pins" {
            execute(&args)
        } else {
            crate::ontology::execute(&name, &args)
        }
    });
    if completed == Err("E_TIMEOUT") {
        TIMED_OUT.store(true, std::sync::atomic::Ordering::Relaxed);
    }
    let structured = match completed {
        Ok(v) => v,
        Err(code) => {
            let data = if code == "E_CLOUD_SYNC" {
                let reason = cloud_root
                    .and_then(|p| std::fs::canonicalize(p).ok())
                    .and_then(|p| crate::guard::cloud_reason(&p).ok().flatten());
                reason.map_or(Value::Null, |reason| json!({"unknowns":[format!("target_root is inside a cloud-synced folder ({reason}); Mir does not run there. Move the repository to a local folder.")]}))
            } else {
                Value::Null
            };
            json!({"ok":false,"data":data,"error":{"code":code},"next_cursor":null,"profile_protections":"available"})
        }
    };
    let is_error = structured["ok"] != true;
    let mut content = json!([]);
    if is_error {
        let mut reason = json!({"code":structured["error"]["code"]});
        if let Some(unknowns) = structured["data"].get("unknowns") {
            reason["unknowns"] = unknowns.clone();
        }
        while serde_json::to_string(&reason)
            .ok()
            .and_then(|s| serde_json::to_string(&s).ok())
            .is_some_and(|s| s.len() > 512)
        {
            if let Some(list) = reason["unknowns"].as_array_mut() {
                list.pop();
            }
            reason["omitted"] = json!(reason["omitted"].as_u64().unwrap_or(0) + 1);
        }
        content =
            json!([{"type":"text","text":serde_json::to_string(&reason).unwrap_or_default()}]);
    }
    json!({"content":content,"structuredContent":structured,"isError":is_error})
}

fn bounded<T: Send + 'static>(
    wait: std::time::Duration,
    work: impl FnOnce() -> Result<T, &'static str> + Send + 'static,
) -> Result<T, &'static str> {
    let (tx, rx) = std::sync::mpsc::sync_channel(1);
    let worker = std::thread::spawn(move || {
        let _ = tx.send(work());
    });
    match rx.recv_timeout(wait) {
        Ok(value) => {
            let _ = worker.join();
            value
        }
        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => Err("E_TIMEOUT"),
        Err(_) => Err("E_IO"),
    }
}

#[cfg(test)]
mod tests {
    use super::bounded;
    use std::time::{Duration, Instant};
    #[test]
    fn outer_deadline_does_not_require_guard_reentry() {
        let start = Instant::now();
        assert_eq!(
            bounded(Duration::from_millis(10), || {
                std::thread::sleep(Duration::from_millis(200));
                Ok(())
            }),
            Err("E_TIMEOUT")
        );
        assert!(start.elapsed() < Duration::from_millis(150));
        // Let the controlled test worker finish before ending this fixture.
        std::thread::sleep(Duration::from_millis(210));
        assert_eq!(bounded(Duration::from_secs(1), || Ok(7)), Ok(7));
    }
}
