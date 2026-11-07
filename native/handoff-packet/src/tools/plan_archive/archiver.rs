//! Reached section parsing and step vocabulary from tools.plan_archive.archiver.
pub const STEP_STATUS_VOCAB: [&str; 5] = ["TODO", "IN_PROGRESS", "DONE", "FAILED", "BLOCKED"];
#[derive(Debug, Clone)]
pub struct Section {
    pub heading: String,
    pub content: String,
    pub done_month: Option<String>,
}
fn section(heading: &str, content: String) -> Section {
    let month = crate::captures(r"\b(\d{4}-\d{2})-\d{2}\b", heading, false)
        .ok()
        .and_then(|c| c.first().and_then(|m| m.groups[1].clone()));
    Section {
        heading: heading.into(),
        content,
        done_month: month,
    }
}
pub fn parse_sections(text: &str) -> Vec<Section> {
    let mut sections = Vec::new();
    let mut heading: Option<&str> = None;
    let mut body = String::new();
    for line in text.split_inclusive('\n') {
        if let Some(next) = line.strip_prefix("## ") {
            if let Some(current) = heading {
                sections.push(section(current, std::mem::take(&mut body)));
            } else if !body.is_empty() {
                sections.push(section("", std::mem::take(&mut body)));
            }
            heading = Some(next.trim_end_matches(['\r', '\n']));
        } else {
            body.push_str(line);
        }
    }
    sections.push(section(heading.unwrap_or(""), body));
    sections
}
pub fn heading_complete(heading: &str) -> Result<bool, crate::Error> {
    crate::has(r"\bCOMPLETE\b", heading, false)
}
/// Status byte range, preserving Python's word-boundary semantics.
pub fn step_match(line: &str) -> Result<Option<(u64, &str, usize, usize)>, crate::Error> {
    let Some(m) = crate::captures(
        r"^Step (\d+): (TODO|IN_PROGRESS|DONE|FAILED|BLOCKED|CLOSED)\b",
        line,
        false,
    )?
    .into_iter()
    .next() else {
        return Ok(None);
    };
    let id = m.groups[1]
        .as_deref()
        .unwrap_or("")
        .parse()
        .map_err(|_| crate::Error::Shape)?;
    let status_start = line.find(": ").ok_or(crate::Error::Shape)? + 2;
    Ok(Some((id, &line[status_start..m.end], status_start, m.end)))
}
