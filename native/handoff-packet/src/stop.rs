//! Stateless native Stop packet checks; Python remains the parity oracle.
use crate::{
    Error, Owner, Result, captures, detect, has, lines, normalized, owner_sections, p, recipient,
    restricted, split, sub,
};
use serde_json::Value;
use std::{
    collections::{BTreeSet, HashMap, HashSet},
    path::Path,
    time::{Duration, Instant},
};

const STAMP: &str = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)";
const CITED: &str = r"(?<![\w./~:-])\.?[\w-][\w.-]*(?:/[\w.-]+)*\.[A-Za-z0-9]+(?![A-Za-z0-9_/-])";
const ACTION: &str = r"\b(?:edit\w*|modif\w*|chang\w*|writ\w*|creat\w*|delet\w*|remov\w*|run\w*|execut\w*|test\w*|check\w*|install\w*|commit\w*|push\w*|network\w*|internet|delegat\w*|spawn\w*|deploy\w*|releas\w*)\b|(?:\uc218\uc815|\ubcc0\uacbd|\ud3b8\uc9d1|\uc4f0\uae30|\uc791\uc131|\uc0dd\uc131|\uc0ad\uc81c|\uc2e4\ud589|\uc218\ud589|\uac80\uc99d|\ud14c\uc2a4\ud2b8|\uc124\uce58|\ucee4\ubc0b|\ud478\uc2dc|\ub124\ud2b8\uc6cc\ud06c|\uc778\ud130\ub137|\uc704\uc784|\uc704\ud0c1|\ud638\ucd9c|\ubc30\ud3ec)";
const READ: &str = r"\b(?:read|inspect)\b|(?:\uc77d|\uc5f4\ub78c)";
const COMPLETE: &str = "Re-send the complete corrected artifact as your final message; it replaces the previous one, so do not send only the changed sections.";
const BASE_PINS: &[&str] = &[
    "repository_root",
    "head",
    "mapping.identity",
    "mapping.version",
    "mapping.digest",
    "contract.identity",
    "contract.version",
    "contract.digest",
];
const PACKET: &str = r#"(?m)qualified target\s*:|handoff pins:|\bmay[ -]not\s*:|"(?:pin_inventory|mapping_sha256)"\s*:|^#{1,6}[^\n]*(?:handoff|brief|\ud578\ub4dc\uc624\ud504|\uc9c0\uc2dc\ubb38|\ube0c\ub9ac\ud504|\uc778\uacc4)"#;

pub struct StopOutput {
    pub output: Option<String>,
    pub warning: Option<String>,
}
fn empty() -> StopOutput {
    StopOutput {
        output: None,
        warning: None,
    }
}
fn quoted(s: &str) -> Result<String> {
    let encoded = serde_json::to_string(s)?;
    let mut out = String::new();
    for ch in encoded.chars() {
        if ch.is_ascii() && ch != '\u{7f}' {
            out.push(ch);
        } else {
            for unit in ch.encode_utf16(&mut [0; 2]) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    Ok(out)
}
fn warning(message: &'static str) -> Result<StopOutput> {
    Ok(StopOutput {
        output: Some(format!(
            "{{\"systemMessage\": {}}}",
            quoted(&format!("Mir handoff WARNING: {message}"))?
        )),
        warning: Some(message.to_owned()),
    })
}
fn items(s: &str) -> impl Iterator<Item = &str> {
    s.split([';', '\n'])
        .map(|v| v.trim().trim_start_matches(['-', '*', ' ']).trim())
        .filter(|v| !v.is_empty())
}
fn matches(pat: &str, text: &str, insensitive: bool) -> Result<Vec<String>> {
    Ok(captures(pat, text, insensitive)?
        .into_iter()
        .map(|m| m.groups[0].clone().unwrap_or_default())
        .collect())
}
fn future_grant(text: &str) -> Result<bool> {
    let mut found = if text.to_lowercase().contains("owner") {
        captures(
            r"\b(?:only after|if|once) (?:a )?(?:separate|explicit|future|new) owner (?:grant|authoriz\w*|approval|permission)\b",
            text,
            true,
        )?
    } else {
        vec![]
    };
    if found.is_empty()
        && (text.contains("\u{bcc4}\u{b3c4}") || text.contains("\u{ba85}\u{c2dc}\u{c801}"))
    {
        found = captures(
            r"(?:\ubcc4\ub3c4|\uba85\uc2dc\uc801)[^.!?;\n]*(?:\uc2b9\uc778|\ud5c8\uac00)[^.!?;\n]*(?:\ud6c4|\uc804|\ud574\uc57c|\uc154\uc57c|\uc788\uc5b4\uc57c)",
            text,
            false,
        )?;
    }
    match found.first() {
        Some(m) => Ok(!has(r"[.!?;](?:\s|$)", &text[..m.start], false)?),
        None => Ok(false),
    }
}
fn action(text: &str) -> Result<bool> {
    let lower = text.to_ascii_lowercase();
    if text.is_ascii()
        && ![
            "edit", "modif", "chang", "writ", "creat", "delet", "remov", "run", "execut", "test",
            "check", "install", "commit", "push", "network", "internet", "delegat", "spawn",
            "deploy", "releas",
        ]
        .iter()
        .any(|stem| lower.contains(stem))
    {
        return Ok(false);
    }
    has(ACTION, text, true)
}
fn read(text: &str) -> Result<bool> {
    if text.is_ascii() {
        let lower = text.to_ascii_lowercase();
        if !lower.contains("read") && !lower.contains("inspect") {
            return Ok(false);
        }
    }
    has(READ, text, true)
}
fn redact(defects: &mut [String], owner: &Owner) {
    for (i, value) in owner.excluded.iter().enumerate() {
        for defect in defects.iter_mut() {
            *defect = defect.replace(value, &format!("[excluded item #{}]", i + 1));
        }
    }
}

pub(crate) fn authority_defects(body: &str, boundary: &Owner) -> Result<Vec<String>> {
    let mut defects: Vec<String> = boundary
        .excluded
        .iter()
        .enumerate()
        .filter(|(_, v)| body.contains(v.as_str()))
        .map(|(i, _)| format!("excluded item #{} appears in forwarded artifact", i + 1))
        .collect();
    let mut plain = sub(r"[*`#]", body, "")?;
    for (pat, label) in [
        (r"(?m)^(\s*(?:[-+]\s*)?)\ud5c8\uc6a9\s*:", "May:"),
        (r"(?m)^(\s*(?:[-+]\s*)?)\uae08\uc9c0\s*:", "May not:"),
    ] {
        if !plain.contains(if label == "May:" {
            "\u{d5c8}\u{c6a9}"
        } else {
            "\u{ae08}\u{c9c0}"
        }) {
            continue;
        }
        let mut out = String::new();
        let mut end = 0;
        for m in captures(pat, &plain, false)? {
            out.push_str(&plain[end..m.start]);
            out.push_str(m.groups[1].as_deref().unwrap_or(""));
            out.push_str(label);
            end = m.end;
        }
        out.push_str(&plain[end..]);
        plain = out;
    }
    let owner = owner_sections(&plain)?;
    let grant = items(&boundary.may)
        .map(normalized)
        .collect::<Result<Vec<_>>>()?
        .join(" ; ");
    let denied = items(&boundary.may_not)
        .map(normalized)
        .collect::<Result<Vec<_>>>()?;
    let korean_grant = plain.contains("\u{b429}\u{b2c8}\u{b2e4}")
        || plain.contains("\u{c788}\u{c2b5}\u{b2c8}\u{b2e4}");
    let possible_inline = plain.to_lowercase().contains(" may ") || korean_grant;
    let mut prose = Vec::new();
    for line in lines(&plain).filter(|_| possible_inline) {
        if has(p::LABEL, line, true)? {
            continue;
        }
        for sentence in split(r"(?<=[.!?])\s+", line)? {
            if !future_grant(&sentence)? {
                prose.push(sentence);
            }
        }
    }
    let prose = prose.join("\n");
    let mut inline = if possible_inline {
        captures(
            r"(?m)\b(?:you|recipient|agent) may (?!not\b)([^\n!?]+)",
            &prose,
            true,
        )?
        .into_iter()
        .map(|m| m.groups[1].clone().unwrap_or_default())
        .collect::<Vec<_>>()
    } else {
        vec![]
    };
    for m in if korean_grant {
        captures(
            r"(?m)^([^\n]*(?:\ud574\ub3c4\s*\ub429\ub2c8\ub2e4|\ud560\s*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4|\ud5c8\uc6a9\ub429\ub2c8\ub2e4)[^\n]*)",
            &prose,
            false,
        )?
    } else {
        vec![]
    } {
        let item = m.groups[1].as_deref().unwrap_or("");
        if !(action(item)? || read(item)?) {
            continue;
        }
        if has(r"(?:\ucd94\uc815|\uc624\ub3c5)\ud560\s*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4[.\s]*$",item,false)? && captures(r"\uc218\s*\uc788\uc2b5\ub2c8\ub2e4|\ud574\ub3c4\s*\ub429\ub2c8\ub2e4|\ud5c8\uc6a9\ub429\ub2c8\ub2e4",item,false)?.len()==1 {continue;}
        if has(
            r"\ud558\uba74[^.!?]*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4",
            item,
            false,
        )? && !has(
            r"\uc218\uc2e0\uc790|\uc5d0\uc774\uc804\ud2b8|\ud5c8\uc6a9|\ud574\ub3c4\s*\ub429\ub2c8\ub2e4",
            item,
            false,
        )? {
            continue;
        }
        inline.push(item.into());
    }
    let mut grants = Vec::new();
    for item in items(&owner.may) {
        grants.extend(split(r"(?<=[.!?])\s+", item)?);
    }
    grants.extend(inline);
    for item in grants {
        let item = item.trim_end_matches('.');
        let candidate = normalized(item)?;
        if ["none", "no permissions", "unavailable"].contains(&candidate.as_str()) {
            continue;
        }
        if has(
            r"^This (?:packet|handoff|document) (?:does not grant|grants no) (?:current )?authority\b",
            item,
            true,
        )? || future_grant(item)?
        {
            continue;
        }
        if (has(
            r"^\s*(?:[-+]\s*)?(?:only the owner\s+(?:can|may)\b|(?:owner|\uc0ac\uc6a9\uc790|\uc18c\uc720\uc790)(?:\([^)]*\))?\s*\ub9cc\s)",
            item,
            true,
        )? || has(
            r"\ub418\uc5b4\uc57c[^.!?]*\ud655\uc778\ud560\s*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4$|\bwould need to be (?:run|executed) to verify\b",
            item,
            true,
        )?) && !has(
            r"\b(?:you|recipient|agent)\b|\uc218\uc2e0\uc790|\uc5d0\uc774\uc804\ud2b8|\ud574\ub3c4\s*\ub429\ub2c8\ub2e4",
            item,
            true,
        )? {
            continue;
        }
        if let Some(scope) = captures(r"^(?:scope|range|\ubc94\uc704)\s*:", item, true)?.first() {
            let nouns = sub(r"[\w.-]+(?:/[\w.*-]*)+", &item[scope.end..], "")?;
            let mut out = String::new();
            let mut end = 0;
            for m in captures(
                r"\ud569\uc131\s*\ud14c\uc2a4\ud2b8|\bsynthetic tests?\b",
                &nouns,
                true,
            )? {
                out.push_str(&nouns[end..m.start]);
                end = m.end;
            }
            out.push_str(&nouns[end..]);
            if !action(&out)? && !read(&out)? {
                continue;
            }
        }
        let mut permitted = if boundary.explicit_authority {
            format!(" {grant} ").contains(&format!(" {candidate} "))
        } else {
            read(item)? && !action(item)?
        };
        let read_item = sub(
            r"\uba85\ub839\uc744\s*\uc2e4\ud589\ud558\uc9c0\s*\uc54a\ub294(?=\s*\uc77d\uae30\s*\ub3c4\uad6c)|\uba85\ub839\s*\uc2e4\ud589\uc774\s*\ud544\uc694\s*\uc5c6\ub294(?=\s*\uc77d\uae30\s*\ub3c4\uad6c)|\ud569\uc131\s*\ud14c\uc2a4\ud2b8",
            item,
            "",
        )?;
        let mut read = String::new();
        let mut end = 0;
        for m in captures(r"[\w.-]+(?:/[\w.*-]*)+", &read_item, false)? {
            read.push_str(&read_item[end..m.start]);
            if read_item[m.start..m.end].to_lowercase() == "read/inspect" {
                read.push_str(&read_item[m.start..m.end]);
            }
            end = m.end;
        }
        read.push_str(&read_item[end..]);
        permitted |= self::read(&read)? && !action(&read)?;
        if candidate.is_empty()
            || !permitted
            || denied.iter().any(|deny| {
                !deny.is_empty() && format!(" {candidate} ").contains(&format!(" {deny} "))
            })
        {
            defects.push(format!("extra may: {item}"));
        }
    }
    redact(&mut defects, boundary);
    Ok(defects)
}

fn decode(raw: &str) -> Result<(Value, usize)> {
    // JSONDecoder.raw_decode starts at byte zero and never skips leading space.
    if raw.starts_with([' ', '\t', '\r', '\n']) {
        return Err(Error::Shape);
    }
    let mut stream = serde_json::Deserializer::from_str(raw).into_iter::<Value>();
    let value = stream.next().ok_or(Error::Shape)??;
    Ok((value, stream.byte_offset()))
}
// Python's float spelling uses scientific notation outside exponents -4..15,
// pads negative exponents and keeps .0 on integral finite floats.
fn python_float(raw: &str) -> Result<String> {
    let value = raw.parse::<f64>().map_err(|_| Error::Shape)?;
    if !value.is_finite() {
        return Ok(if value.is_sign_negative() {
            "-Infinity"
        } else {
            "Infinity"
        }
        .into());
    }
    let encoded = serde_json::to_string(&value)?;
    let sign = if encoded.starts_with('-') { "-" } else { "" };
    let magnitude = encoded.trim_start_matches('-');
    let (mantissa, exponent) = match magnitude.split_once(['e', 'E']) {
        Some((m, e)) => (m, e.parse::<i32>().map_err(|_| Error::Shape)?),
        None => (magnitude, 0),
    };
    let decimal = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let all: String = mantissa.chars().filter(|c| *c != '.').collect();
    let Some(first) = all.find(|c| c != '0') else {
        return Ok(format!("{sign}0.0"));
    };
    let exponent = exponent + decimal - first as i32 - 1;
    let digits = all[first..].trim_end_matches('0');
    if !(-4..16).contains(&exponent) {
        let fraction = if digits.len() > 1 {
            format!(".{}", &digits[1..])
        } else {
            String::new()
        };
        return Ok(format!(
            "{sign}{}{fraction}e{}{:02}",
            &digits[..1],
            if exponent < 0 { '-' } else { '+' },
            exponent.abs()
        ));
    }
    if exponent < 0 {
        return Ok(format!(
            "{sign}0.{}{}",
            "0".repeat((-exponent - 1) as usize),
            digits
        ));
    }
    let decimal = (exponent + 1) as usize;
    if decimal >= digits.len() {
        return Ok(format!(
            "{sign}{digits}{}.0",
            "0".repeat(decimal - digits.len())
        ));
    }
    Ok(format!(
        "{sign}{}.{}",
        &digits[..decimal],
        &digits[decimal..]
    ))
}
enum OrderedJson {
    Object(Vec<(String, OrderedJson)>),
    Array(Vec<OrderedJson>),
    Atom(String),
}
impl OrderedJson {
    fn parse(raw: &str, position: &mut usize) -> Result<Self> {
        while raw
            .as_bytes()
            .get(*position)
            .is_some_and(u8::is_ascii_whitespace)
        {
            *position += 1;
        }
        let start = *position;
        match raw.as_bytes().get(start) {
            Some(b'{') => {
                *position += 1;
                let mut entries: Vec<(String, Self)> = Vec::new();
                loop {
                    while raw
                        .as_bytes()
                        .get(*position)
                        .is_some_and(u8::is_ascii_whitespace)
                    {
                        *position += 1;
                    }
                    if raw.as_bytes().get(*position) == Some(&b'}') {
                        *position += 1;
                        break;
                    }
                    let (key, len) = decode(&raw[*position..])?;
                    let key = key.as_str().ok_or(Error::Shape)?.to_owned();
                    *position += len;
                    while raw
                        .as_bytes()
                        .get(*position)
                        .is_some_and(u8::is_ascii_whitespace)
                    {
                        *position += 1;
                    }
                    if raw.as_bytes().get(*position) != Some(&b':') {
                        return Err(Error::Shape);
                    }
                    *position += 1;
                    let value = Self::parse(raw, position)?;
                    if let Some(entry) = entries.iter_mut().find(|(k, _)| *k == key) {
                        entry.1 = value;
                    } else {
                        entries.push((key, value));
                    }
                    while raw
                        .as_bytes()
                        .get(*position)
                        .is_some_and(u8::is_ascii_whitespace)
                    {
                        *position += 1;
                    }
                    match raw.as_bytes().get(*position) {
                        Some(b',') => *position += 1,
                        Some(b'}') => {
                            *position += 1;
                            break;
                        }
                        _ => return Err(Error::Shape),
                    }
                }
                Ok(Self::Object(entries))
            }
            Some(b'[') => {
                *position += 1;
                let mut entries = Vec::new();
                loop {
                    while raw
                        .as_bytes()
                        .get(*position)
                        .is_some_and(u8::is_ascii_whitespace)
                    {
                        *position += 1;
                    }
                    if raw.as_bytes().get(*position) == Some(&b']') {
                        *position += 1;
                        break;
                    }
                    entries.push(Self::parse(raw, position)?);
                    while raw
                        .as_bytes()
                        .get(*position)
                        .is_some_and(u8::is_ascii_whitespace)
                    {
                        *position += 1;
                    }
                    match raw.as_bytes().get(*position) {
                        Some(b',') => *position += 1,
                        Some(b']') => {
                            *position += 1;
                            break;
                        }
                        _ => return Err(Error::Shape),
                    }
                }
                Ok(Self::Array(entries))
            }
            Some(b'"') => {
                let (value, len) = decode(&raw[start..])?;
                *position += len;
                Ok(Self::Atom(quoted(value.as_str().ok_or(Error::Shape)?)?))
            }
            Some(_) => {
                while raw
                    .as_bytes()
                    .get(*position)
                    .is_some_and(|c| !c.is_ascii_whitespace() && !matches!(c, b',' | b'}' | b']'))
                {
                    *position += 1;
                }
                let token = &raw[start..*position];
                let atom = if !["true", "false", "null"].contains(&token)
                    && token.contains(['.', 'e', 'E'])
                {
                    python_float(token)?
                } else if token == "-0" {
                    "0".into()
                } else {
                    token.into()
                };
                Ok(Self::Atom(atom))
            }
            None => Err(Error::Shape),
        }
    }
    fn pretty(&self, depth: usize) -> Result<String> {
        let (open, close, entries) = match self {
            Self::Atom(value) => return Ok(value.clone()),
            Self::Object(values) => (
                '{',
                '}',
                values
                    .iter()
                    .map(|(key, value)| {
                        Ok(format!("{}: {}", quoted(key)?, value.pretty(depth + 1)?))
                    })
                    .collect::<Result<Vec<_>>>()?,
            ),
            Self::Array(values) => (
                '[',
                ']',
                values
                    .iter()
                    .map(|value| value.pretty(depth + 1))
                    .collect::<Result<Vec<_>>>()?,
            ),
        };
        if entries.is_empty() {
            return Ok(format!("{open}{close}"));
        }
        Ok(format!(
            "{open}\n{}{}\n{}{close}",
            "  ".repeat(depth + 1),
            entries.join(&format!(",\n{}", "  ".repeat(depth + 1))),
            "  ".repeat(depth)
        ))
    }
}
// Preserve Python object insertion order and duplicate-key replacement semantics.
fn pretty(raw: &str, stamp: Option<&str>) -> Result<String> {
    let mut value = OrderedJson::parse(raw, &mut 0)?;
    if let Some(stamp) = stamp {
        let OrderedJson::Object(entries) = &mut value else {
            return Err(Error::Shape);
        };
        let value = OrderedJson::Atom(quoted(stamp)?);
        if let Some(entry) = entries.iter_mut().find(|(key, _)| key == "observed_at") {
            entry.1 = value;
        } else {
            entries.push(("observed_at".into(), value));
        }
    }
    value.pretty(0)
}
pub(crate) fn matching_pins(body: &str, fresh: &str) -> Result<bool> {
    let Some(header) = captures(r"(?m)^handoff pins:\n", body, false)?
        .first()
        .map(|m| m.end)
    else {
        return Ok(false);
    };
    let raw = &body[header..];
    let Ok((supplied, end)) = decode(raw) else {
        return Ok(false);
    };
    let Some(stamp) = supplied.get("observed_at").and_then(Value::as_str) else {
        return Ok(false);
    };
    if !has(&format!(r"\A(?:{STAMP})\z"), stamp, false)? {
        return Ok(false);
    }
    let current = fresh.strip_prefix("handoff pins:\n").ok_or(Error::Shape)?;
    Ok(raw[..end] == pretty(current, Some(stamp))?)
}
fn supplied_json_present(body: &str, fresh: &str) -> Result<bool> {
    let mut current: Value =
        serde_json::from_str(fresh.split_once("handoff pins:\n").ok_or(Error::Shape)?.1)?;
    for m in captures(r#"\{\s*"repository_root"\s*:"#, body, false)? {
        if let Ok((supplied, _)) = decode(&body[m.start..]) {
            current.as_object_mut().ok_or(Error::Shape)?.insert(
                "observed_at".into(),
                supplied.get("observed_at").cloned().unwrap_or(Value::Null),
            );
            if python_equal(&supplied, &current) {
                return Ok(true);
            }
        }
    }
    Ok(false)
}
fn python_equal(left: &Value, right: &Value) -> bool {
    fn integer(value: &Value) -> Option<i128> {
        match value {
            Value::Bool(v) => Some(i128::from(*v)),
            Value::Number(v) => v
                .as_i64()
                .map(i128::from)
                .or_else(|| v.as_u64().map(i128::from)),
            _ => None,
        }
    }
    fn number(value: &Value) -> Option<f64> {
        match value {
            Value::Bool(v) => Some(if *v { 1.0 } else { 0.0 }),
            Value::Number(v) => v.as_f64(),
            _ => None,
        }
    }
    match (left, right) {
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(key, value)| b.get(key).is_some_and(|other| python_equal(value, other)))
        }
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| python_equal(a, b))
        }
        (Value::Bool(_) | Value::Number(_), Value::Bool(_) | Value::Number(_)) => {
            match (integer(left), integer(right)) {
                (Some(a), Some(b)) => a == b,
                (Some(a), None) => number(right).is_some_and(|b| {
                    b.is_finite()
                        && b.fract() == 0.0
                        && b >= i64::MIN as f64
                        && b <= u64::MAX as f64
                        && a == b as i128
                }),
                (None, Some(b)) => number(left).is_some_and(|a| {
                    a.is_finite()
                        && a.fract() == 0.0
                        && a >= i64::MIN as f64
                        && a <= u64::MAX as f64
                        && a as i128 == b
                }),
                (None, None) => number(left) == number(right),
            }
        }
        _ => left == right,
    }
}
fn pin_differences(body: &str, fresh: &str) -> Result<Vec<String>> {
    let values = body
        .split_once("handoff pins:\n")
        .and_then(|(_, raw)| decode(raw).ok())
        .zip(
            fresh
                .split_once("handoff pins:\n")
                .and_then(|(_, raw)| decode(raw).ok()),
        );
    let Some(((supplied, _), (current, _))) = values else {
        return Ok(vec!["entire pin block missing or malformed".into()]);
    };
    fn changed(expected: &Value, actual: &Value, pointer: &str, out: &mut Vec<String>) {
        match (expected, actual) {
            (Value::Object(e), Value::Object(a)) => {
                for key in e.keys().chain(a.keys()).collect::<BTreeSet<_>>() {
                    if key != "observed_at" {
                        changed(
                            e.get(key).unwrap_or(&Value::Null),
                            a.get(key).unwrap_or(&Value::Null),
                            &format!("{pointer}/{key}"),
                            out,
                        );
                    }
                }
            }
            (Value::Array(e), Value::Array(a)) => {
                for i in 0..e.len().max(a.len()) {
                    changed(
                        e.get(i).unwrap_or(&Value::Null),
                        a.get(i).unwrap_or(&Value::Null),
                        &format!("{pointer}/{i}"),
                        out,
                    );
                }
            }
            _ => {
                if !python_equal(expected, actual) {
                    out.push(if pointer.is_empty() {
                        "/".into()
                    } else {
                        pointer.into()
                    });
                }
            }
        }
    }
    let mut out = Vec::new();
    changed(&current, &supplied, "", &mut out);
    if out.is_empty() {
        out.push("pin block formatting or /observed_at".into());
    }
    Ok(out)
}

pub(crate) fn namespace_defects(body: &str, root: &Path) -> Result<Vec<String>> {
    let Ok(raw) = std::fs::read_to_string(root.join(".mir/ontology-map.json")) else {
        return Ok(vec![]);
    };
    let Ok(data) = serde_json::from_str::<Value>(&raw) else {
        return Ok(vec![]);
    };
    let Some(namespace) = data
        .get("namespace")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
    else {
        return Ok(vec![]);
    };
    let aliases = match data.get("namespace_aliases") {
        None => &[][..],
        Some(v) => match v.as_array() {
            Some(v) => v.as_slice(),
            None => return Ok(vec![]),
        },
    };
    let aliases: HashSet<&str> = aliases
        .iter()
        .filter(|entry| {
            entry.get("reviewed") == Some(&Value::Bool(true))
                && entry
                    .get("evidence")
                    .and_then(Value::as_str)
                    .is_some_and(|s| !s.trim().is_empty())
        })
        .filter_map(|entry| entry.get("namespace").and_then(Value::as_str))
        .collect();
    let plain = sub(r"[*`]", body, "")?;
    let mut seen = HashSet::new();
    let mut defects = Vec::new();
    for m in captures(
        &format!(
            r"(?m)^\s*(?:#{{1,6}}\s+|[-+]\s+)?{}\s*:\s*([\w.-]+):[\w./-]+",
            p::TARGET_NAME
        ),
        &plain,
        true,
    )? {
        let target = m.groups[1].as_deref().unwrap_or("");
        if seen.insert(target.to_owned()) && target != namespace && !aliases.contains(target) {
            defects.push(format!(
                "qualified target namespace {target} differs from map namespace {namespace}"
            ));
        }
    }
    Ok(defects)
}

fn check_packet(body: &str, pins: &str, boundary: &Owner, root: &Path) -> Result<Vec<String>> {
    let mut defects = namespace_defects(body, root)?;
    if !has(r"(?m)^handoff pins:$", body, false)? && supplied_json_present(body, pins)? {
        defects.push("supplied pins header altered (keep the literal 'handoff pins:' line)".into());
    }
    if body.matches("handoff pins:").count() > 1 {
        defects.push("duplicate supplied pins blocks".into());
    }
    if !matching_pins(body, pins)? {
        defects.push(format!(
            "missing/changed supplied pins (copy the entire supplied block unchanged): {}",
            pin_differences(body, pins)?.join(", ")
        ));
    }
    let plain = sub(
        r"(?m)^[ \t]*[-+][ \t]+",
        &sub(r"[*`#]", &body.replace(pins, ""), "")?,
        "",
    )?;
    if !has(
        &format!(r"(?m)^\s*{}\s*:\s*[\w.-]+:[\w./-]+", p::TARGET_NAME),
        &plain,
        true,
    )? {
        defects.push("missing qualified target (namespace:local-id)".into());
    }
    for axis in ["lifecycle", "temporal", "epistemic", "verification"] {
        if !has(&format!(r"(?m)^[ \t]*{axis}:[ \t]*\S[^\n]*"), &plain, true)? {
            defects.push(format!("missing {axis} status"));
        }
    }
    let evidence = captures(r"(?m)^[ \t]*evidence:[ \t]*(.+)", &plain, true)?;
    let valid_evidence = match evidence.first().and_then(|m| m.groups[1].as_deref()) {
        Some(e) => {
            has(
                r"\b(?:parent-supplied|verified-in-repo|source|provenance)\b",
                e,
                true,
            )? && has(STAMP, e, false)?
        }
        None => false,
    };
    if !valid_evidence {
        defects
            .push("missing evidence provenance/time (source and ISO-8601 observation time)".into());
    }
    for field in ["unknowns", "self-check"] {
        if !has(&format!(r"(?m)^[ \t]*{field}:[ \t]*\S[^\n]*"), &plain, true)? {
            defects.push(format!("missing {field}"));
        }
    }
    let owner = owner_sections(&sub(r"[`#]", &body.replace(pins, ""), "")?)?;
    for label in ["may", "may not"] {
        if !has(
            &format!(
                r"(?m)^\s*{}\s*(?:\([^\n)]*\)\s*)?:",
                label.replace(' ', "[ -]")
            ),
            &plain,
            true,
        )? {
            defects.push(format!("missing {label}"));
        }
    }
    let owner_deny = normalized(&owner.may_not)?;
    for denied in items(&boundary.may_not) {
        if boundary.excluded.iter().any(|v| denied.contains(v)) {
            continue;
        }
        if !owner_deny.contains(&normalized(denied)?) {
            defects.push(format!("missing owner restriction: {denied}"));
        }
    }
    defects.extend(authority_defects(&body.replace(pins, ""), boundary)?);
    let data: Value =
        serde_json::from_str(pins.split_once("handoff pins:\n").ok_or(Error::Shape)?.1)?;
    let self_check = captures(r"(?ms)^\s*self-check:\s*(.*)", &plain, true)?;
    let inventory = self_check
        .first()
        .and_then(|m| m.groups[1].as_deref())
        .unwrap_or("");
    for field in [
        "qualified target",
        "lifecycle",
        "temporal",
        "epistemic",
        "verification",
        "evidence",
        "unknowns",
        "may",
        "may not",
    ] {
        if !has(
            &format!(
                r"(?<![\w.-])(?:field )?{field}\s*[=:]\s*(?:present|missing|abbreviated|unchecked)\b"
            ),
            inventory,
            true,
        )? {
            defects.push(format!("missing self-check field: {field}"));
        }
    }
    let mut names = Vec::new();
    if let Some(entries) = data.get("pin_inventory") {
        for entry in entries.as_array().ok_or(Error::Shape)? {
            names.push(
                entry
                    .get("pin")
                    .and_then(Value::as_str)
                    .ok_or(Error::Shape)?
                    .to_owned(),
            );
        }
    }
    if names.is_empty() {
        names = BASE_PINS.iter().map(|s| (*s).to_owned()).collect();
        if let Some(sources) = data.get("sources") {
            for (index, _) in sources.as_array().ok_or(Error::Shape)?.iter().enumerate() {
                names.extend([
                    format!("sources[{index}].digest"),
                    format!("sources[{index}].revision"),
                ]);
            }
        }
    }
    for name in names {
        if !has(
            &format!(
                r"(?<![\w.-])(?:pin )?{}\s*[=:]\s*(?:parent-supplied|verified-in-repo|unavailable|missing|abbreviated|unchecked)\b",
                regex::escape(&name)
            ),
            inventory,
            true,
        )? {
            defects.push(format!("missing self-check pin: {name}"));
        }
    }
    if let Some(gaps) = data.get("unknowns") {
        for gap in gaps.as_array().ok_or(Error::Shape)? {
            let gap = gap.as_str().ok_or(Error::Shape)?;
            if !inventory.contains(gap) {
                defects.push(format!("unchecked pin gap: {gap}"));
            }
        }
    }
    redact(&mut defects, boundary);
    Ok(defects)
}

fn protected_patterns(root: &Path) -> Vec<String> {
    let Ok(text) = std::fs::read_to_string(root.join(".mir/repo-profile.toml")) else {
        return vec![];
    };
    let Ok(profile) = text.parse::<toml::Value>() else {
        return vec![];
    };
    let mut result = Vec::new();
    for (section, key) in [
        ("paths", "protected_paths"),
        ("paths", "secret_paths"),
        ("boundaries", "secrets"),
    ] {
        let values = match profile.get(section) {
            None => continue,
            Some(s) => match s.as_table() {
                Some(t) => t.get(key),
                None => return vec![],
            },
        };
        if let Some(values) = values {
            let Some(values) = values.as_array() else {
                return vec![];
            };
            for value in values {
                let Some(value) = value.as_str() else {
                    return vec![];
                };
                result.push(value.to_owned());
            }
        }
    }
    result
}
// fnmatchcase permits '*' across separators and treats an unmatched '[' literally.
fn fnmatch(pattern: &str, text: &str) -> Result<bool> {
    let chars: Vec<char> = pattern.chars().collect();
    let mut out = String::from("\\A(?s:");
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '*' => out.push_str(".*"),
            '?' => out.push('.'),
            '[' => {
                let mut j = i + 1;
                if chars.get(j) == Some(&'!') {
                    j += 1;
                }
                if chars.get(j) == Some(&']') {
                    j += 1;
                }
                while j < chars.len() && chars[j] != ']' {
                    j += 1;
                }
                if j >= chars.len() {
                    out.push_str("\\[");
                } else {
                    let mut chunks: Vec<Vec<char>> = Vec::new();
                    let mut start = i + 1;
                    let mut k = start + if chars[start] == '!' { 2 } else { 1 };
                    while let Some(offset) = chars[k.min(j)..j].iter().position(|c| *c == '-') {
                        k += offset;
                        chunks.push(chars[start..k].to_vec());
                        start = k + 1;
                        k += 3;
                    }
                    if start < j {
                        chunks.push(chars[start..j].to_vec());
                    } else if let Some(last) = chunks.last_mut() {
                        last.push('-');
                    }
                    for index in (1..chunks.len()).rev() {
                        if chunks[index - 1].last() > chunks[index].first() {
                            let next = chunks.remove(index);
                            chunks[index - 1].pop();
                            chunks[index - 1].extend(next.into_iter().skip(1));
                        }
                    }
                    let negate = chunks.first().and_then(|s| s.first()) == Some(&'!');
                    if negate {
                        chunks[0].remove(0);
                    }
                    if chunks.iter().all(Vec::is_empty) {
                        out.push_str(if negate { "." } else { "(?!)" });
                    } else {
                        out.push('[');
                        if negate {
                            out.push('^');
                        }
                        for (index, chunk) in chunks.iter().enumerate() {
                            if index > 0 {
                                out.push('-');
                            }
                            for c in chunk {
                                if matches!(c, '\\' | '-' | '[' | ']' | '^' | '&' | '~' | '|') {
                                    out.push('\\');
                                }
                                out.push(*c);
                            }
                        }
                        out.push(']');
                    }
                    i = j;
                }
            }
            c => out.push_str(&regex::escape(&c.to_string())),
        }
        i += 1;
    }
    out.push_str(")\\z");
    has(&out, text, false)
}

fn cited_paths(body: &str, owner: &Owner, root: &Path) -> Result<Vec<String>> {
    let mut covered: HashSet<String> = crate::supply::source_paths(owner, root)?
        .into_iter()
        .collect();
    covered.extend([
        ".mir/ontology-map.json".into(),
        "scripts/mir_ontology.py".into(),
    ]);
    let mut denied: HashSet<String> = matches(CITED, &owner.may_not, false)?.into_iter().collect();
    denied.extend(matches(CITED, &owner_sections(body)?.may_not, false)?);
    for line in lines(body) {
        if has(
            r"\b(?:not[- ]read|did not read|not opened|protected (?:scope|paths?))\b",
            line,
            true,
        )? {
            denied.extend(matches(CITED, line, false)?);
        }
    }
    let protected = protected_patterns(root);
    let mut paths = Vec::new();
    for raw in matches(CITED, body, false)? {
        if covered.contains(&raw)
            || denied.contains(&raw)
            || paths.contains(&raw)
            || owner.excluded.iter().any(|v| raw.contains(v))
        {
            continue;
        }
        let mut protected_match = false;
        for pattern in &protected {
            if fnmatch(pattern, &raw)? {
                protected_match = true;
                break;
            }
        }
        if protected_match {
            continue;
        }
        if Path::new(&raw).components().any(|part| {
            part.as_os_str()
                .to_str()
                .is_some_and(|s| s.starts_with(".env") || s == "secrets" || s == "..")
        }) || raw.starts_with(".mir/memory.db")
        {
            continue;
        }
        let path = root.join(&raw);
        if path
            .symlink_metadata()
            .is_ok_and(|m| m.file_type().is_symlink())
            || !path.is_file()
        {
            continue;
        }
        paths.push(raw);
    }
    paths.truncate(32);
    Ok(paths)
}

const REPAIR: &str = r"Repair (?:handoff once|recipient accounting once|handoff deterministic defects \(second/final block\)):";
fn prior_blocks(event: &Value) -> Result<Option<usize>> {
    let (_, rows) = crate::transcript::current_turn(event)?;
    let mut count = 0;
    let mut pending: HashMap<(String, String, String), usize> = HashMap::new();
    for row in rows {
        let shape = row
            .get("type")
            .and_then(Value::as_str)
            .ok_or(Error::Shape)?;
        let prompts: HashSet<(String, String)> =
            crate::transcript::hook_prompts(&row)?.into_iter().collect();
        for (run_id, text) in prompts {
            if run_id.to_lowercase().starts_with("stop:")
                && has(&format!("^{REPAIR}"), &text, false)?
            {
                let other = if shape == "response_item" {
                    "event_msg"
                } else {
                    "response_item"
                };
                let paired = (run_id.clone(), text.clone(), other.to_owned());
                if let Some(value) = pending.get_mut(&paired).filter(|value| **value > 0) {
                    *value -= 1;
                } else {
                    *pending.entry((run_id, text, shape.to_owned())).or_default() += 1;
                    count += 1;
                }
            }
        }
        let empty = serde_json::json!({});
        let payload = row.get("payload").unwrap_or(&empty);
        let record = if shape == "system" { &row } else { payload };
        let feedback = (shape == "system"
            && row.get("subtype").and_then(Value::as_str) == Some("hook_response"))
            || (shape == "event_msg"
                && payload.get("type").and_then(Value::as_str) == Some("hook_response"));
        let meta = shape == "user" && row.get("isMeta").is_some_and(crate::transcript::truthy);
        if !feedback && !meta {
            continue;
        }
        let text = if meta {
            crate::transcript::message_text(row.get("message").unwrap_or(&empty))?
        } else {
            match record.get("stdout").or_else(|| record.get("output")) {
                None => String::new(),
                Some(Value::String(s)) => s.clone(),
                Some(Value::Null) => "None".into(),
                Some(Value::Bool(true)) => "True".into(),
                Some(Value::Bool(false)) => "False".into(),
                Some(v) => v.to_string(),
            }
        };
        if has(REPAIR, &text, false)? {
            if feedback
                && record
                    .get("hookName")
                    .or_else(|| record.get("hook_name"))
                    .and_then(Value::as_str)
                    != Some("Stop")
            {
                continue;
            }
            count += 1;
        }
    }
    Ok(if count > 0 { Some(count) } else { None })
}
fn deterministic(defects: Vec<String>) -> Vec<String> {
    const PREFIXES: &[&str] = &[
        "missing cited-source pins",
        "abbreviated hex",
        "missing recipient pin label",
        "excluded item #",
        "qualified target namespace ",
        "command-ban compliance failure",
        "verified-in-repo digest needs",
        "verified-in-repo pin lacks this-turn computation",
        "repository-wide absence claimed",
    ];
    defects
        .into_iter()
        .filter(|d| PREFIXES.iter().any(|p| d.starts_with(p)))
        .collect()
}
fn block(
    mut defects: Vec<String>,
    retry: bool,
    receiving: bool,
    owner: &Owner,
) -> Result<StopOutput> {
    if retry {
        defects = deterministic(defects);
    }
    redact(&mut defects, owner);
    if defects.is_empty() {
        return Ok(empty());
    }
    let prefix = if retry {
        "Repair handoff deterministic defects (second/final block): "
    } else if receiving {
        "Repair recipient accounting once: "
    } else {
        "Repair handoff once: "
    };
    Ok(StopOutput {
        output: Some(format!(
            "{{\"decision\": \"block\", \"reason\": {}}}",
            quoted(&format!("{prefix}{}. {COMPLETE}", defects.join("; ")))?
        )),
        warning: None,
    })
}
fn nested_source_citations(lines: &[&str]) -> Result<HashSet<usize>> {
    let mut parents: Vec<(usize, usize)> = Vec::new();
    let mut children: HashMap<usize, Vec<usize>> = HashMap::new();
    for (index, line) in lines.iter().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let indent = line.chars().take_while(|c| c.is_whitespace()).count();
        while parents.last().is_some_and(|(i, _)| indent <= *i) {
            parents.pop();
        }
        if !has(r"^\s*[-+*]\s+", line, false)? {
            continue;
        }
        if let Some((_, parent)) = parents.last() {
            children.entry(*parent).or_default().push(index);
        }
        parents.push((indent, index));
    }
    let mut cited = HashSet::new();
    for (parent, siblings) in children {
        if !has(r"[\w-]+[./][\w./-]+", lines[parent], false)? {
            continue;
        }
        let mut found = false;
        for index in &siblings {
            if has(
                r"^\s*[-+*]\s+\d+(?:[-\u2013]\d+)?(?:,\s*\d+(?:[-\u2013]\d+)?)*:\s",
                lines[*index],
                false,
            )? {
                found = true;
                break;
            }
        }
        if found {
            cited.extend(siblings);
        }
    }
    Ok(cited)
}
fn source_claim_defects(body: &str) -> Result<Vec<String>> {
    if !body.contains(['`', '"']) {
        return Ok(vec![]);
    }
    let assertion = crate::stop_tools::assertion_text(body)?;
    let source_lines: Vec<&str> = lines(&assertion).collect();
    let nested = nested_source_citations(&source_lines)?;
    for (index, line) in source_lines.iter().enumerate() {
        if !line.contains(['`', '"']) {
            continue;
        }
        if !nested.contains(&index)
            && !line
                .split(':')
                .skip(1)
                .any(|after| after.chars().next().is_some_and(char::is_numeric))
        {
            continue;
        }
        if !nested.contains(&index)
            && !has(r"(?:[\w-]*[./][\w./-]*|\u2026):\d+(?:-\d+)?", line, false)?
        {
            continue;
        }
        if !has(r#"`[^`\n]+`|"[^"\n]+""#, line, false)? {
            continue;
        }
        let prose = sub(r#"`[^`\n]+`|"[^"\n]+""#, line, "")?;
        if has(
            r"\b(?:all|every|always|each of|none)\b|\ubaa8\ub450|\ubaa8\ub4e0|\uc804\ubd80|\ud56d\uc0c1|\uc5b8\uc81c\ub098",
            &prose,
            true,
        )? && has(
            r"\b(?:emit\w*|return\w*|print\w*|report\w*|ends? with|raise\w*|output\w*)\b|\ubcf4\uace0|\ucd9c\ub825|\ubc18\ud658|\ub05d\ub098|\ub05d\ub0a9|\ub0c5\ub2c8\ub2e4|\ub0b8\ub2e4",
            &prose,
            true,
        )? {
            return Ok(vec![format!(
                "universal claim about cited source output: re-read the cited lines; keep the claim only if each case's quoted literal shows it, else narrow it: {}",
                line.trim().chars().take(300).collect::<String>()
            )]);
        }
    }
    Ok(vec![])
}

pub fn stop(event: &Value) -> Result<StopOutput> {
    let started = Instant::now();
    let (prompt, mut body) = crate::transcript::transcript_turn(event)?;
    if let Some(native) = event
        .get("last_assistant_message")
        .and_then(Value::as_str)
        .filter(|v| {
            !v.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
                .is_empty()
        })
    {
        body = native.to_owned();
    }
    let receiving = recipient(&prompt)?;
    if !detect(&prompt)? && !receiving {
        return Ok(empty());
    }
    if !receiving && !has(PACKET, &body, true)? && !recipient(&body)? {
        return Ok(empty());
    }
    let Some(retry) = event.get("stop_hook_active").and_then(Value::as_bool) else {
        return warning("native retry guard unavailable; packet check skipped to prevent a loop.");
    };
    let previous = prior_blocks(event)?;
    if previous.is_some_and(|p| p >= 2) || (retry && previous != Some(1)) {
        return warning("repair already requested; allowing stop without another block.");
    }
    let owner = owner_sections(&prompt)?;
    if receiving {
        let mut defects = crate::stop_tools::recipient_check(&prompt, &body, event)?;
        defects.extend(crate::stop_tools::abbreviated_hex(&body)?);
        defects.extend(authority_defects(&body, &owner)?);
        return block(defects, retry, true, &owner);
    }
    if restricted(&prompt)? {
        let message = "pins/check unavailable: owner forbids commands; no runner performed.";
        let checked = (|| -> Result<StopOutput> {
            let mut defects = crate::stop_tools::no_command_check(&prompt, &body, event)?;
            if !retry {
                defects.extend(source_claim_defects(&body)?);
            }
            if retry {
                defects = deterministic(defects);
            }
            let mut output = if defects.is_empty() {
                warning(message)?
            } else {
                block(defects, retry, false, &owner)?
            };
            output.warning = Some(message.to_owned());
            Ok(output)
        })();
        return checked.or_else(|_| {
            let mut output = warning(crate::supply::UNAVAILABLE)?;
            output.warning = Some(format!(
                "{message}\nMir handoff WARNING: {}",
                crate::supply::UNAVAILABLE
            ));
            Ok(output)
        });
    }
    let guard = captures(r"(?m)^Prompt SHA256: ([0-9a-f]{64})\s*$", &body, true)?;
    if let Some(guard) = guard.first()
        && guard.groups[1].as_deref() != Some(crate::digest::sha256(prompt.as_bytes()).as_str())
    {
        return warning(
            "current prompt hash changed; packet check skipped to avoid stale authority.",
        );
    }
    let root = crate::supply::repository_root(event)?;
    let pins = crate::supply::run_pins(event, &owner, None, Duration::from_secs(5))?;
    let mut defects = check_packet(&body, &pins, &owner, &root)?;
    defects.extend(crate::stop_tools::abbreviated_hex(&body)?);
    let cited = cited_paths(&body, &owner, &root)?;
    if !cited.is_empty() {
        let budget = Duration::from_secs_f64((6.5 - started.elapsed().as_secs_f64()).max(0.5));
        let fresh = crate::supply::run_pins(event, &owner, Some(&cited), budget)?;
        let data: Value =
            serde_json::from_str(fresh.split_once("handoff pins:\n").ok_or(Error::Shape)?.1)?;
        let mut unpinned = Vec::new();
        if let Some(sources) = data.get("sources") {
            for source in sources.as_array().ok_or(Error::Shape)? {
                let sha = source.get("sha256").and_then(Value::as_str).unwrap_or("");
                let revision = source.get("revision").and_then(Value::as_str).unwrap_or("");
                if !sha.is_empty()
                    && (!body.contains(sha)
                        || (has(r"\A[0-9a-f]{40}\z", revision, false)? && !body.contains(revision)))
                {
                    unpinned.push(
                        source
                            .get("path")
                            .and_then(Value::as_str)
                            .ok_or(Error::Shape)?
                            .to_owned(),
                    );
                }
            }
        }
        if !unpinned.is_empty() {
            defects.push(format!("missing cited-source pins (add sha256 and last-change revision for each from `python3 scripts/mir_ontology.py mapping --handoff <paths>` sources; no second pins block): {}",unpinned.join(", ")));
        }
    }
    if guard.is_empty() {
        defects.push("missing Prompt SHA256 (copy the supplied full prompt hash)".into());
    }
    defects.extend(crate::stop_tools::verification_defects(
        &body, &body, event, false,
    )?);
    if !retry {
        defects.extend(source_claim_defects(&body)?);
    }
    block(defects, retry, false, &owner)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(name: &str) -> std::path::PathBuf {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join(format!("stop-core-{name}-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        root
    }
    #[test]
    fn fnmatch_matches_python_fnmatchcase() {
        // Expected values come from Python's fnmatch.fnmatchcase.
        let cases: &[(&str, &str, bool)] = &[
            ("a?c", "abc", true),
            ("a?c", "ac", false),
            ("a?c", "a/c", true),
            ("a?c", "x.env", false),
            ("a?c", ".env.local", false),
            ("a?c", "secrets/a/b", false),
            ("a?c", "bx", false),
            ("a?c", "dx", false),
            ("a?c", "]x", false),
            ("a?c", "-x", false),
            ("a?c", "[x", false),
            ("a?c", "axbyc", false),
            ("a?c", "ex", false),
            ("a?c", "dx", false),
            ("a?c", "a", false),
            ("*.env", "abc", false),
            ("*.env", "ac", false),
            ("*.env", "a/c", false),
            ("*.env", "x.env", true),
            ("*.env", ".env.local", false),
            ("*.env", "secrets/a/b", false),
            ("*.env", "bx", false),
            ("*.env", "dx", false),
            ("*.env", "]x", false),
            ("*.env", "-x", false),
            ("*.env", "[x", false),
            ("*.env", "axbyc", false),
            ("*.env", "ex", false),
            ("*.env", "dx", false),
            ("*.env", "a", false),
            (".env.*", "abc", false),
            (".env.*", "ac", false),
            (".env.*", "a/c", false),
            (".env.*", "x.env", false),
            (".env.*", ".env.local", true),
            (".env.*", "secrets/a/b", false),
            (".env.*", "bx", false),
            (".env.*", "dx", false),
            (".env.*", "]x", false),
            (".env.*", "-x", false),
            (".env.*", "[x", false),
            (".env.*", "axbyc", false),
            (".env.*", "ex", false),
            (".env.*", "dx", false),
            (".env.*", "a", false),
            ("secrets/**", "abc", false),
            ("secrets/**", "ac", false),
            ("secrets/**", "a/c", false),
            ("secrets/**", "x.env", false),
            ("secrets/**", ".env.local", false),
            ("secrets/**", "secrets/a/b", true),
            ("secrets/**", "bx", false),
            ("secrets/**", "dx", false),
            ("secrets/**", "]x", false),
            ("secrets/**", "-x", false),
            ("secrets/**", "[x", false),
            ("secrets/**", "axbyc", false),
            ("secrets/**", "ex", false),
            ("secrets/**", "dx", false),
            ("secrets/**", "a", false),
            ("[abc]x", "abc", false),
            ("[abc]x", "ac", false),
            ("[abc]x", "a/c", false),
            ("[abc]x", "x.env", false),
            ("[abc]x", ".env.local", false),
            ("[abc]x", "secrets/a/b", false),
            ("[abc]x", "bx", true),
            ("[abc]x", "dx", false),
            ("[abc]x", "]x", false),
            ("[abc]x", "-x", false),
            ("[abc]x", "[x", false),
            ("[abc]x", "axbyc", false),
            ("[abc]x", "ex", false),
            ("[abc]x", "dx", false),
            ("[abc]x", "a", false),
            ("[!abc]x", "abc", false),
            ("[!abc]x", "ac", false),
            ("[!abc]x", "a/c", false),
            ("[!abc]x", "x.env", false),
            ("[!abc]x", ".env.local", false),
            ("[!abc]x", "secrets/a/b", false),
            ("[!abc]x", "bx", false),
            ("[!abc]x", "dx", true),
            ("[!abc]x", "]x", true),
            ("[!abc]x", "-x", true),
            ("[!abc]x", "[x", true),
            ("[!abc]x", "axbyc", false),
            ("[!abc]x", "ex", true),
            ("[!abc]x", "dx", true),
            ("[!abc]x", "a", false),
            ("[a-c]x", "abc", false),
            ("[a-c]x", "ac", false),
            ("[a-c]x", "a/c", false),
            ("[a-c]x", "x.env", false),
            ("[a-c]x", ".env.local", false),
            ("[a-c]x", "secrets/a/b", false),
            ("[a-c]x", "bx", true),
            ("[a-c]x", "dx", false),
            ("[a-c]x", "]x", false),
            ("[a-c]x", "-x", false),
            ("[a-c]x", "[x", false),
            ("[a-c]x", "axbyc", false),
            ("[a-c]x", "ex", false),
            ("[a-c]x", "dx", false),
            ("[a-c]x", "a", false),
            ("[]]x", "abc", false),
            ("[]]x", "ac", false),
            ("[]]x", "a/c", false),
            ("[]]x", "x.env", false),
            ("[]]x", ".env.local", false),
            ("[]]x", "secrets/a/b", false),
            ("[]]x", "bx", false),
            ("[]]x", "dx", false),
            ("[]]x", "]x", true),
            ("[]]x", "-x", false),
            ("[]]x", "[x", false),
            ("[]]x", "axbyc", false),
            ("[]]x", "ex", false),
            ("[]]x", "dx", false),
            ("[]]x", "a", false),
            ("[!]]x", "abc", false),
            ("[!]]x", "ac", false),
            ("[!]]x", "a/c", false),
            ("[!]]x", "x.env", false),
            ("[!]]x", ".env.local", false),
            ("[!]]x", "secrets/a/b", false),
            ("[!]]x", "bx", true),
            ("[!]]x", "dx", true),
            ("[!]]x", "]x", false),
            ("[!]]x", "-x", true),
            ("[!]]x", "[x", true),
            ("[!]]x", "axbyc", false),
            ("[!]]x", "ex", true),
            ("[!]]x", "dx", true),
            ("[!]]x", "a", false),
            ("[z-a]x", "abc", false),
            ("[z-a]x", "ac", false),
            ("[z-a]x", "a/c", false),
            ("[z-a]x", "x.env", false),
            ("[z-a]x", ".env.local", false),
            ("[z-a]x", "secrets/a/b", false),
            ("[z-a]x", "bx", false),
            ("[z-a]x", "dx", false),
            ("[z-a]x", "]x", false),
            ("[z-a]x", "-x", false),
            ("[z-a]x", "[x", false),
            ("[z-a]x", "axbyc", false),
            ("[z-a]x", "ex", false),
            ("[z-a]x", "dx", false),
            ("[z-a]x", "a", false),
            ("[a-]x", "abc", false),
            ("[a-]x", "ac", false),
            ("[a-]x", "a/c", false),
            ("[a-]x", "x.env", false),
            ("[a-]x", ".env.local", false),
            ("[a-]x", "secrets/a/b", false),
            ("[a-]x", "bx", false),
            ("[a-]x", "dx", false),
            ("[a-]x", "]x", false),
            ("[a-]x", "-x", true),
            ("[a-]x", "[x", false),
            ("[a-]x", "axbyc", false),
            ("[a-]x", "ex", false),
            ("[a-]x", "dx", false),
            ("[a-]x", "a", false),
            ("[x", "abc", false),
            ("[x", "ac", false),
            ("[x", "a/c", false),
            ("[x", "x.env", false),
            ("[x", ".env.local", false),
            ("[x", "secrets/a/b", false),
            ("[x", "bx", false),
            ("[x", "dx", false),
            ("[x", "]x", false),
            ("[x", "-x", false),
            ("[x", "[x", true),
            ("[x", "axbyc", false),
            ("[x", "ex", false),
            ("[x", "dx", false),
            ("[x", "a", false),
            ("a*b?c", "abc", false),
            ("a*b?c", "ac", false),
            ("a*b?c", "a/c", false),
            ("a*b?c", "x.env", false),
            ("a*b?c", ".env.local", false),
            ("a*b?c", "secrets/a/b", false),
            ("a*b?c", "bx", false),
            ("a*b?c", "dx", false),
            ("a*b?c", "]x", false),
            ("a*b?c", "-x", false),
            ("a*b?c", "[x", false),
            ("a*b?c", "axbyc", true),
            ("a*b?c", "ex", false),
            ("a*b?c", "dx", false),
            ("a*b?c", "a", false),
            ("[a-c-e]x", "abc", false),
            ("[a-c-e]x", "ac", false),
            ("[a-c-e]x", "a/c", false),
            ("[a-c-e]x", "x.env", false),
            ("[a-c-e]x", ".env.local", false),
            ("[a-c-e]x", "secrets/a/b", false),
            ("[a-c-e]x", "bx", true),
            ("[a-c-e]x", "dx", false),
            ("[a-c-e]x", "]x", false),
            ("[a-c-e]x", "-x", true),
            ("[a-c-e]x", "[x", false),
            ("[a-c-e]x", "axbyc", false),
            ("[a-c-e]x", "ex", true),
            ("[a-c-e]x", "dx", false),
            ("[a-c-e]x", "a", false),
        ];
        for (pattern, text, expected) in cases {
            assert_eq!(
                fnmatch(pattern, text).unwrap(),
                *expected,
                "{pattern} {text}"
            );
        }
    }
    #[test]
    fn packet_fields_and_exact_pins_are_checked() {
        let root = fixture("packet");
        let owner = owner_sections("May: read/inspect only\nMay not: no commands").unwrap();
        let pins = "handoff pins:\n{\n  \"repository_root\": \"fixture\",\n  \"observed_at\": \"2026-10-31T00:00:00Z\"\n}";
        let defects = check_packet(
            &format!("{pins}\nQualified target: fixture:item"),
            pins,
            &owner,
            &root,
        )
        .unwrap();
        assert!(defects.contains(&"missing lifecycle status".into()));
        assert!(defects.contains(&"missing self-check pin: head".into()));
        assert!(defects.contains(&"missing owner restriction: no commands".into()));
        assert!(
            !defects
                .iter()
                .any(|s| s.starts_with("missing/changed supplied pins"))
        );
        assert!(!matching_pins(&pins.replace("fixture", "changed"), pins).unwrap());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn authority_exclusions_and_extra_grants_are_checked() {
        let owner =
            owner_sections("May: read/inspect only\nMay not: no commands\nExclude: PRIVATE_MARKER")
                .unwrap();
        assert_eq!(
            authority_defects("May: run tests\nPRIVATE_MARKER", &owner).unwrap(),
            vec![
                "excluded item #1 appears in forwarded artifact",
                "extra may: run tests"
            ]
        );
        assert!(
            authority_defects("May: read/inspect only", &owner)
                .unwrap()
                .is_empty()
        );
        assert_eq!(
            authority_defects("The agent may run tests.", &owner).unwrap(),
            vec!["extra may: run tests"]
        );
        assert!(
            authority_defects(
                "The agent may run tests only after a separate owner approval.",
                &owner
            )
            .unwrap()
            .is_empty()
        );
        assert!(!action("read/inspect only").unwrap());
        assert!(action("RUN tests").unwrap());
    }
    #[test]
    fn namespace_reviewed_aliases_are_local() {
        let root = fixture("namespace");
        std::fs::create_dir_all(root.join(".mir")).unwrap();
        std::fs::write(root.join(".mir/ontology-map.json"),r#"{"namespace":"local","namespace_aliases":[{"namespace":"alias","reviewed":true,"evidence":"review"}]}"#).unwrap();
        assert_eq!(
            namespace_defects(
                "Qualified target: remote:x\nQualified target: alias:y\nQualified target: remote:z",
                &root
            )
            .unwrap(),
            vec!["qualified target namespace remote differs from map namespace local"]
        );
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn source_universal_claims_include_nested_citations() {
        assert_eq!(
            source_claim_defects("src/hook.py:1 all cases return `ok`.")
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            source_claim_defects("- src/hook.py\n  - 1: every case returns `ok`.")
                .unwrap()
                .len(),
            1
        );
        assert!(
            source_claim_defects(
                "> src/hook.py:1 all cases return `ok`.\nAt 10:30 all cases return `ok`."
            )
            .unwrap()
            .is_empty()
        );
        assert_eq!(
            deterministic(vec![
                "missing lifecycle status".into(),
                "missing cited-source pins: a.py".into()
            ]),
            vec!["missing cited-source pins: a.py"]
        );
    }
    #[test]
    fn native_feedback_pairing_controls_retry_count() {
        let root = fixture("prior");
        let transcript = root.join("turn.jsonl");
        let rows = [
            serde_json::json!({"type":"event_msg","payload":{"type":"user_message","message":"write a handoff for another agent"}}),
            serde_json::json!({"type":"response_item","payload":{"role":"user","content":"<hook_prompt hook_run_id=\"Stop:one\">Repair handoff once: missing fields</hook_prompt>"}}),
            serde_json::json!({"type":"event_msg","payload":{"type":"item_completed","item":{"type":"HookPrompt","fragments":[{"hookRunId":"Stop:one","text":"Repair handoff once: missing fields"}]}}}),
            serde_json::json!({"type":"assistant","message":{"content":"Repair handoff once: quoted"}}),
        ];
        std::fs::write(
            &transcript,
            rows.iter()
                .map(Value::to_string)
                .collect::<Vec<_>>()
                .join("\n"),
        )
        .unwrap();
        assert_eq!(
            prior_blocks(&serde_json::json!({"transcript_path":transcript})).unwrap(),
            Some(1)
        );
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn python_fnmatch_ranges_and_escaping() {
        for (pattern, text, expected) in [
            ("[az-a]", "a", true),
            ("[az-a]", "z", false),
            ("[!z-a]", "x", true),
            ("[z-a]", "z", false),
            ("[a-c]", "b", true),
            ("[a&&b]", "&", true),
            ("[[]", "[", true),
            ("[]]", "]", true),
            ("[!]]", "x", true),
            ("[!]", "[!]", true),
            ("a**/?.py", "a/sub/x.py", true),
            ("[a-]", "-", true),
            ("[a\\]", "\\", true),
        ] {
            assert_eq!(
                fnmatch(pattern, text).unwrap(),
                expected,
                "{pattern} {text}"
            );
        }
    }
    #[test]
    fn python_json_order_duplicate_keys_float_and_unicode() {
        let raw = r#"{"z":1,"a":1e-5,"z":2,"b":[1e16,1e15,1e-4,-0.0,0.1],"unicode":"\ud55c","observed_at":"old"}"#;
        assert_eq!(
            pretty(raw, Some("stamp")).unwrap(),
            "{\n  \"z\": 2,\n  \"a\": 1e-05,\n  \"b\": [\n    1e+16,\n    1000000000000000.0,\n    0.0001,\n    -0.0,\n    0.1\n  ],\n  \"unicode\": \"\\ud55c\",\n  \"observed_at\": \"stamp\"\n}"
        );
        assert_eq!(
            pretty(r#"{"v":true,"x":null,"v":false}"#, None).unwrap(),
            "{\n  \"v\": false,\n  \"x\": null\n}"
        );
        assert_eq!(
            pretty(r#"{"v":{}}"#, Some("stamp")).unwrap(),
            "{\n  \"v\": {},\n  \"observed_at\": \"stamp\"\n}"
        );
        assert!(decode(" {} ").is_err());
    }
    #[test]
    fn python_json_numeric_equality_and_pin_differences() {
        for (left, right, expected) in [
            (serde_json::json!(true), serde_json::json!(1.0), true),
            (serde_json::json!(false), serde_json::json!(-0.0), true),
            (
                serde_json::json!([1,{"v":true}]),
                serde_json::json!([1.0,{"v":1}]),
                true,
            ),
            (
                serde_json::json!(9007199254740993u64),
                serde_json::json!(9007199254740992.0),
                false,
            ),
            (
                serde_json::json!(u64::MAX),
                serde_json::json!(18446744073709551616.0),
                false,
            ),
            (
                serde_json::json!(i64::MIN),
                serde_json::json!(-9223372036854775808.0),
                true,
            ),
            (serde_json::json!("1"), serde_json::json!(1), false),
        ] {
            assert_eq!(python_equal(&left, &right), expected, "{left} {right}");
            assert_eq!(python_equal(&right, &left), expected);
        }
        let fresh =
            "handoff pins:\n{\"repository_root\": 1.0, \"observed_at\": \"2026-10-31T00:00:00Z\"}";
        let body =
            "handoff pins:\n{\"repository_root\": true, \"observed_at\": \"2026-10-31T00:00:00Z\"}";
        assert!(supplied_json_present(body, fresh).unwrap());
        assert_eq!(
            pin_differences(body, fresh).unwrap(),
            vec!["pin block formatting or /observed_at"]
        );
        assert!(!matching_pins(body, fresh).unwrap());
    }
    #[test]
    fn command_ban_warning_precedes_generic_error_warning() {
        let root = fixture("exception");
        let transcript = root.join("turn.jsonl");
        let rows = [
            serde_json::json!({"type":"user","message":{"content":"Write a handoff for another agent.\nMay not: no commands"}}),
            serde_json::json!({"type":"assistant","message":{"content":[{"type":"tool_use","input":{}}]}}),
        ];
        std::fs::write(
            &transcript,
            rows.iter()
                .map(Value::to_string)
                .collect::<Vec<_>>()
                .join("\n"),
        )
        .unwrap();
        let output=stop(&serde_json::json!({"transcript_path":transcript,"stop_hook_active":false,"last_assistant_message":"Qualified target: local:item"})).unwrap();
        assert_eq!(
            output.warning,
            Some(format!(
                "pins/check unavailable: owner forbids commands; no runner performed.\nMir handoff WARNING: {}",
                crate::supply::UNAVAILABLE
            ))
        );
        assert_eq!(
            output.output,
            warning(crate::supply::UNAVAILABLE).unwrap().output
        );
        std::fs::remove_dir_all(root).unwrap();
    }
}
