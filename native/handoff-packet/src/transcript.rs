use super::{Error, LIMIT, Result, captures, json, lines, p};
use serde_json::{Map, Value};
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom},
    path::Path,
};
fn object(v: &Value) -> Result<&Map<String, Value>> {
    v.as_object().ok_or(Error::Shape)
}
fn message_text(message: &Value) -> Result<String> {
    let m = object(message)?;
    let empty = json!([]);
    let content = m.get("content").unwrap_or(&empty);
    if let Some(s) = content.as_str() {
        return Ok(s.to_owned());
    }
    let mut out = Vec::new();
    for item in content.as_array().ok_or(Error::Shape)? {
        let item = object(item)?;
        if ["text", "output_text", "input_text"]
            .contains(&item.get("type").and_then(Value::as_str).unwrap_or(""))
        {
            out.push(
                item.get("text")
                    .map_or(Ok(""), |v| v.as_str().ok_or(Error::Shape))?,
            );
        }
    }
    Ok(out.join("\n"))
}
fn hook_prompts(row: &Value) -> Result<Vec<(String, String)>> {
    let row = object(row)?;
    let empty = json!({});
    let payload = row.get("payload").unwrap_or(&empty);
    if row.get("type").and_then(Value::as_str) == Some("response_item")
        && object(payload)?.get("role").and_then(Value::as_str) == Some("user")
    {
        let text = message_text(payload)?;
        let pat = format!("\\A(?:{})\\z", p::HOOK_PROMPTS[0]);
        return Ok(captures(&pat, &text, false)?
            .into_iter()
            .map(|m| {
                (
                    m.groups[1].clone().unwrap_or_default(),
                    m.groups[2].clone().unwrap_or_default(),
                )
            })
            .collect());
    }
    if row.get("type").and_then(Value::as_str) == Some("event_msg")
        && object(payload)?.get("type").and_then(Value::as_str) == Some("item_completed")
    {
        let item = object(object(payload)?.get("item").unwrap_or(&empty))?;
        if item.get("type").and_then(Value::as_str) == Some("HookPrompt") {
            let empty = json!([]);
            let fragments = item
                .get("fragments")
                .unwrap_or(&empty)
                .as_array()
                .ok_or(Error::Shape)?;
            return fragments
                .iter()
                .map(|item| {
                    let m = object(item)?;
                    Ok((
                        m.get("hookRunId")
                            .map_or(Ok(""), |v| v.as_str().ok_or(Error::Shape))?
                            .to_owned(),
                        m.get("text")
                            .map_or(Ok(""), |v| v.as_str().ok_or(Error::Shape))?
                            .to_owned(),
                    ))
                })
                .collect();
        }
    }
    Ok(vec![])
}
fn transcript_records(event: &Value) -> Result<Vec<Value>> {
    let path = Path::new(event["transcript_path"].as_str().ok_or(Error::Shape)?);
    let mut options = File::options();
    options.read(true);
    // Native O_NOFOLLOW | O_NONBLOCK constants; safe std open, no libc dependency.
    #[cfg(target_os = "macos")]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(0x100 | 0x4);
    }
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(0x20000 | 0x800);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.custom_flags(0x00200000);
    }
    let mut file = options.open(path)?;
    if !file.metadata()?.is_file() || std::fs::symlink_metadata(path)?.file_type().is_symlink() {
        return Err(Error::Shape);
    }
    let len = file.seek(SeekFrom::End(0))?;
    let start = len.saturating_sub(LIMIT as u64);
    file.seek(SeekFrom::Start(start))?;
    let mut tail = Vec::new();
    file.take(LIMIT as u64).read_to_end(&mut tail)?;
    let tail = if start > 0 {
        tail.iter()
            .position(|b| *b == b'\n')
            .map_or(&[][..], |i| &tail[i + 1..])
    } else {
        &tail
    };
    let text = std::str::from_utf8(tail).map_err(|_| Error::Shape)?;
    lines(text)
        .filter(|line| !line.trim().is_empty())
        .map(|line| Ok(serde_json::from_str(line)?))
        .collect()
}
fn current_turn(event: &Value) -> Result<(String, Vec<Value>)> {
    let mut prompt = None;
    let mut rows = Vec::new();
    for row in transcript_records(event)? {
        let r = object(&row)?;
        let empty = json!({});
        let payload = r.get("payload").unwrap_or(&empty);
        let kind = r.get("type").and_then(Value::as_str);
        let mut found = None;
        if kind == Some("user") && !r.get("isMeta").is_some_and(truthy) {
            let message = r.get("message").ok_or(Error::Shape)?;
            let m = object(message)?;
            let content = m.get("content").cloned().unwrap_or(json!([]));
            let text = if content.is_string() {
                true
            } else {
                let mut text = false;
                for item in content.as_array().ok_or(Error::Shape)? {
                    if object(item)?.get("type").and_then(Value::as_str) == Some("text") {
                        text = true;
                        break;
                    }
                }
                text
            };
            if text {
                found = Some(Value::String(message_text(message)?));
            }
        } else if kind == Some("response_item")
            && object(payload)?.get("role").and_then(Value::as_str) == Some("user")
            && hook_prompts(&row)?.is_empty()
        {
            found = Some(Value::String(message_text(payload)?));
        } else if kind == Some("event_msg")
            && object(payload)?.get("type").and_then(Value::as_str) == Some("user_message")
        {
            found = Some(object(payload)?.get("message").ok_or(Error::Shape)?.clone());
        }
        if let Some(value) = found {
            prompt = Some(value);
            rows.clear();
        }
        rows.push(row);
    }
    Ok((
        prompt
            .and_then(|p| p.as_str().map(str::to_owned))
            .ok_or(Error::Shape)?,
        rows,
    ))
}
pub(super) fn transcript_turn(event: &Value) -> Result<(String, String)> {
    let (prompt, rows) = current_turn(event)?;
    let mut body = String::new();
    for row in rows {
        let r = object(&row)?;
        let kind = r.get("type").and_then(Value::as_str);
        let empty = json!({});
        let message = r
            .get(if kind == Some("assistant") {
                "message"
            } else {
                "payload"
            })
            .unwrap_or(&empty);
        if kind == Some("assistant")
            || (kind == Some("response_item")
                && object(message)?.get("role").and_then(Value::as_str) == Some("assistant")
                && (object(message)?.get("phase").is_none_or(Value::is_null)
                    || object(message)?.get("phase").and_then(Value::as_str)
                        == Some("final_answer")))
        {
            let text = message_text(message)?;
            if !text.is_empty() {
                body = text;
            }
        }
    }
    Ok((prompt, body))
}
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64() != Some(0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(m) => !m.is_empty(),
    }
}
