//! Pure parity with memory/sanitize.py; None has the default ephemeral behavior.
//! BORROWED-FROM: claude_memory@d0e523cd06d6adeae4744d89736f79564d9db41d
//! lib/claude_memory/{privacy_tag,content_sanitizer}.rb (MIT).
use crate::{Result, captures};
// Python re.DOTALL | re.IGNORECASE; shared by every block pattern.
const _FLAGS: u32 = 18;
const _PRIVATE: &str = r"<private>(.+?)</private>";
const _SECRET: &str = r"<secret>(.+?)</secret>";
const _NOINDEX: &str = r"<noindex>(.+?)</noindex>";
const _ALWAYS_REDACT: &[&str] = &[_SECRET, _NOINDEX];
fn redact(pattern: &str, src: &str) -> Result<String> {
    let pattern = format!("{}{pattern}", if _FLAGS & 16 != 0 { "(?s)" } else { "" });
    let mut out = String::new();
    let mut end = 0;
    // Use the shared adapter for Python case-insensitive Unicode behavior.
    for m in captures(&pattern, src, _FLAGS & 2 != 0)? {
        out.push_str(&src[end..m.start]);
        out.push_str("[REDACTED]");
        end = m.end;
    }
    out.push_str(&src[end..]);
    Ok(out)
}
pub fn sanitize(src: &str, consent_scope: Option<&str>) -> Result<String> {
    let mut out = if consent_scope == Some("persistent") {
        src.to_owned()
    } else {
        redact(_PRIVATE, src)?
    };
    for pattern in _ALWAYS_REDACT {
        out = redact(pattern, &out)?;
    }
    Ok(out)
}
