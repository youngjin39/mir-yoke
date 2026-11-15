//! Shared Python path, exception and text-stream compatibility.
use crate::executor_registry::Error as RegistryError;
use std::{ffi::OsStr, io, path::Path};
type Result<T> = std::result::Result<T, String>;

/// The deliberately bounded stream family shared with the public facade.
pub fn supported_streams() -> bool {
    let setting = std::env::var("PYTHONIOENCODING").unwrap_or_default();
    let (encoding, errors) = setting.split_once(':').unwrap_or((&setting, "strict"));
    ["MIR_EXECUTOR_STDOUT", "MIR_EXECUTOR_STDERR"]
        .into_iter()
        .all(|prefix| {
            let encoding =
                std::env::var(format!("{prefix}_ENCODING")).unwrap_or_else(|_| encoding.into());
            let errors = std::env::var(format!("{prefix}_ERRORS")).unwrap_or_else(|_| {
                if prefix.ends_with("STDERR") {
                    "backslashreplace".into()
                } else {
                    errors.into()
                }
            });
            let normalized = encoding.to_ascii_lowercase().replace(['-', ' ', '_'], "");
            matches!(
                normalized.as_str(),
                "" | "utf8"
                    | "u8"
                    | "utf"
                    | "utf8sig"
                    | "ascii"
                    | "usascii"
                    | "646"
                    | "ansix3.41968"
                    | "latin1"
                    | "latin"
                    | "iso88591"
                    | "isoir100"
                    | "l1"
                    | "cp1252"
                    | "windows1252"
                    | "utf16"
                    | "utf16le"
                    | "utf16be"
                    | "utf32"
                    | "utf32le"
                    | "utf32be"
            ) && matches!(
                errors.as_str(),
                "" | "strict"
                    | "ignore"
                    | "replace"
                    | "backslashreplace"
                    | "xmlcharrefreplace"
                    | "surrogateescape"
                    | "surrogatepass"
            )
        })
}

pub fn codepoints(bytes: &[u8]) -> Vec<u32> {
    let mut out = Vec::new();
    let mut rest = bytes;
    loop {
        match std::str::from_utf8(rest) {
            Ok(text) => {
                out.extend(text.chars().map(u32::from));
                break;
            }
            Err(error) => {
                out.extend(
                    String::from_utf8_lossy(&rest[..error.valid_up_to()])
                        .chars()
                        .map(u32::from),
                );
                let count = error
                    .error_len()
                    .unwrap_or(rest.len() - error.valid_up_to());
                out.extend(
                    rest[error.valid_up_to()..error.valid_up_to() + count]
                        .iter()
                        .map(|b| 0xdc00 + u32::from(*b)),
                );
                rest = &rest[error.valid_up_to() + count..];
            }
        }
    }
    out
}
pub fn os_text(value: &OsStr) -> String {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        points_text(&codepoints(value.as_bytes()))
    }
    #[cfg(not(unix))]
    {
        value.to_string_lossy().into_owned()
    }
}
pub fn points_text(points: &[u32]) -> String {
    points
        .iter()
        .map(|&n| char::from_u32(n).map_or_else(|| format!("\\u{n:04x}"), |c| c.to_string()))
        .collect()
}
pub fn text_points(text: &str) -> Vec<u32> {
    text.chars().map(u32::from).collect()
}
/// JSON string spelling with ensure_ascii=False; surrogate scalars stay typed.
pub fn json_quote_points(points: &[u32]) -> Vec<u32> {
    let mut out = vec![34];
    for &point in points {
        match point {
            34 => out.extend([92, 34]),
            92 => out.extend([92, 92]),
            8 => out.extend([92, 98]),
            9 => out.extend([92, 116]),
            10 => out.extend([92, 110]),
            12 => out.extend([92, 102]),
            13 => out.extend([92, 114]),
            0..=31 => out.extend(format!("\\u{point:04x}").chars().map(u32::from)),
            _ => out.push(point),
        }
    }
    out.push(34);
    out
}
pub fn os_points(value: &OsStr) -> Vec<u32> {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        codepoints(value.as_bytes())
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        char::decode_utf16(value.encode_wide())
            .map(|point| {
                point
                    .map(u32::from)
                    .unwrap_or_else(|error| u32::from(error.unpaired_surrogate()))
            })
            .collect()
    }
    #[cfg(not(any(unix, windows)))]
    {
        value.to_string_lossy().chars().map(u32::from).collect()
    }
}
pub fn path_scalar(path: &Path) -> serde_json::Value {
    if let Some(text) = path.to_str() {
        serde_json::Value::String(text.into())
    } else {
        serde_json::json!({"__native_string":os_points(path.as_os_str())})
    }
}
pub fn repr_points(points: &[u32]) -> String {
    let mut encoded = String::from("\"");
    for &n in points {
        if let Some(c) = char::from_u32(n) {
            let escaped = serde_json::to_string(&c.to_string()).unwrap_or_else(|_| "\"\"".into());
            encoded.push_str(&escaped[1..escaped.len() - 1]);
        } else {
            encoded.push_str(&format!("\\u{n:04x}"));
        }
    }
    encoded.push('"');
    crate::python_json::parse(&encoded)
        .map(|v| v.repr())
        .unwrap_or(encoded)
}
pub fn repr(text: &str) -> String {
    repr_points(&text_points(text))
}
pub fn io_error(error: io::Error, path: &Path, operation: IoOperation) -> String {
    io_operation(error, Some(path), None, operation)
}

#[cfg(all(test, windows))]
pub(crate) fn windows_frozen_error(name: &str, path: &Path) -> String {
    let corpus: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/user_runtime_install/installer-windows.json"
    ))
    .unwrap();
    let error = &corpus["records"][name]["error"];
    let rendered = error["rendered"]
        .as_str()
        .unwrap()
        .split(": '")
        .next()
        .unwrap();
    format!(
        "{}: {rendered}: {}",
        error["class"].as_str().unwrap(),
        repr_points(&os_points(path.as_os_str()))
    )
}
#[derive(Clone, Copy, Debug)]
pub enum IoOperation {
    Win32,
    Read,
    Handle,
}
pub(crate) fn io_operation(
    error: io::Error,
    path: Option<&Path>,
    destination: Option<&Path>,
    operation: IoOperation,
) -> String {
    #[cfg(windows)]
    {
        crate::adoption_fs::windows_error(&error, path, destination, operation)
    }
    #[cfg(not(windows))]
    {
        let _ = operation;
        let mut rendered = unix_io_error(error, path.unwrap_or_else(|| Path::new("")));
        if path.is_none() {
            rendered.truncate(rendered.len() - 4);
        }
        if let Some(destination) = destination {
            rendered.push_str(&format!(
                " -> {}",
                repr_points(&os_points(destination.as_os_str()))
            ));
        }
        rendered
    }
}
#[cfg(not(windows))]
fn unix_io_error(error: io::Error, path: &Path) -> String {
    let kind = match error.kind() {
        io::ErrorKind::NotFound => "FileNotFoundError",
        io::ErrorKind::AlreadyExists => "FileExistsError",
        io::ErrorKind::PermissionDenied => "PermissionError",
        io::ErrorKind::NotADirectory => "NotADirectoryError",
        io::ErrorKind::IsADirectory => "IsADirectoryError",
        _ => "OSError",
    };
    let platform_message = crate::executor_brief_profile::python_os_error_text(&error);
    let message = match error.kind() {
        io::ErrorKind::NotFound => "No such file or directory",
        io::ErrorKind::AlreadyExists => "File exists",
        io::ErrorKind::PermissionDenied if error.raw_os_error() == Some(1) => {
            "Operation not permitted"
        }
        io::ErrorKind::PermissionDenied => "Permission denied",
        io::ErrorKind::NotADirectory => "Not a directory",
        io::ErrorKind::IsADirectory => "Is a directory",
        _ => &platform_message,
    };
    format!(
        "{kind}: [Errno {}] {message}: {}",
        error.raw_os_error().unwrap_or(22),
        repr_points(&os_points(path.as_os_str()))
    )
}
pub fn sql_error(error: rusqlite::Error) -> String {
    if let rusqlite::Error::SqlInputError { msg, .. } = error {
        return format!("sqlite3.OperationalError: {msg}");
    }
    if let rusqlite::Error::SqliteFailure(code, message) = error {
        let kind = match code.code {
            rusqlite::ErrorCode::DatabaseCorrupt | rusqlite::ErrorCode::NotADatabase => {
                "DatabaseError"
            }
            rusqlite::ErrorCode::ConstraintViolation => "IntegrityError",
            _ => "OperationalError",
        };
        format!(
            "sqlite3.{kind}: {}",
            message.unwrap_or_else(|| code.to_string())
        )
    } else {
        format!("sqlite3.OperationalError: {error}")
    }
}
pub fn registry_error(error: RegistryError, path: &Path) -> String {
    match error {
        RegistryError::Io(error, operation) => {
            let target = if error.kind() == io::ErrorKind::AlreadyExists {
                path.parent().unwrap_or(path)
            } else {
                path
            };
            io_error(error, target, operation)
        }
        RegistryError::Sql(error) => sql_error(error),
        RegistryError::Shape => format!(
            "ValueError: jobs database must be a regular file: {}",
            os_text(path.as_os_str())
        ),
        RegistryError::Text(error) => format!("ValueError: {error:?}"),
    }
}
pub fn encode_error(
    encoding: &str,
    points: &[u32],
    start: usize,
    end: usize,
    reason: &str,
) -> String {
    let subject = if end > start + 1 {
        format!("characters in position {start}-{}", end - 1)
    } else {
        format!(
            "character {} in position {start}",
            ascii_repr(&points[start..end])
        )
    };
    format!("UnicodeEncodeError: '{encoding}' codec can't encode {subject}: {reason}")
}
fn ascii_repr(points: &[u32]) -> String {
    let mut out = String::from("'");
    for &n in points {
        if n >= 128 {
            out.push_str(&escaped(n));
        } else if let Some(c) = char::from_u32(n) {
            out.push(c);
        }
    }
    out.push('\'');
    out
}
fn escaped(n: u32) -> String {
    if n <= 0xff {
        format!("\\x{n:02x}")
    } else if n <= 0xffff {
        format!("\\u{n:04x}")
    } else {
        format!("\\U{n:08x}")
    }
}
pub fn encode(text: &str, error: bool, bom: bool) -> Result<Vec<u8>> {
    if text.is_empty() {
        return Ok(Vec::new());
    }
    let setting = std::env::var_os("PYTHONIOENCODING")
        .map(|s| os_text(&s))
        .unwrap_or_default();
    let (default_encoding, default_handler) =
        setting.split_once(':').unwrap_or((&setting, "strict"));
    let prefix = if error {
        "MIR_EXECUTOR_STDERR"
    } else {
        "MIR_EXECUTOR_STDOUT"
    };
    let encoding_override = std::env::var(format!("{prefix}_ENCODING")).ok();
    let errors_override = std::env::var(format!("{prefix}_ERRORS")).ok();
    let encoding = encoding_override.as_deref().unwrap_or(default_encoding);
    let handler = errors_override.as_deref().unwrap_or(default_handler);
    let normalized = encoding.to_ascii_lowercase().replace(['-', ' ', '_'], "");
    let name = match normalized.as_str() {
        "" | "utf8" | "u8" | "utf" | "utf8sig" => "utf-8",
        "ascii" | "usascii" | "646" | "ansix3.41968" => "ascii",
        "latin1" | "latin" | "iso88591" | "isoir100" | "l1" => "latin-1",
        "cp1252" | "windows1252" => "charmap",
        "utf16" | "utf16le" => "utf-16-le",
        "utf16be" => "utf-16-be",
        "utf32" | "utf32le" => "utf-32-le",
        "utf32be" => "utf-32-be",
        _ => return Err(format!("LookupError: unknown encoding: {encoding}")),
    };
    let handler = if error && errors_override.is_none() {
        "backslashreplace"
    } else if handler.is_empty() {
        "strict"
    } else {
        handler
    };
    let mut out = Vec::new();
    if bom && normalized == "utf8sig" {
        out.extend([0xef, 0xbb, 0xbf]);
    }
    if bom && normalized == "utf16" {
        out.extend([0xff, 0xfe]);
    }
    if bom && normalized == "utf32" {
        out.extend([0xff, 0xfe, 0, 0]);
    }
    {
        let points = text_points(text);
        let mut index = 0;
        while index < points.len() {
            let n = points[index];
            let surrogate = (0xd800..=0xdfff).contains(&n);
            let cp1252 = [
                0x20ac, 0x81, 0x201a, 0x192, 0x201e, 0x2026, 0x2020, 0x2021, 0x2c6, 0x2030, 0x160,
                0x2039, 0x152, 0x8d, 0x17d, 0x8f, 0x90, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022,
                0x2013, 0x2014, 0x2dc, 0x2122, 0x161, 0x203a, 0x153, 0x9d, 0x17e, 0x178,
            ];
            let byte = if name == "charmap" && (128..160).contains(&n) {
                None
            } else if name == "charmap" && n > 255 {
                cp1252.iter().position(|&x| x == n).map(|i| 128 + i as u8)
            } else if n <= 255 {
                Some(n as u8)
            } else {
                None
            };
            let invalid = match name {
                "ascii" => n > 127,
                "latin-1" => n > 255,
                "charmap" => byte.is_none(),
                _ => surrogate && handler != "surrogatepass",
            };
            if invalid {
                let replacement = match handler {
                    "ignore" => String::new(),
                    "replace" => {
                        if name.starts_with("utf") {
                            "\u{fffd}".into()
                        } else {
                            "?".into()
                        }
                    }
                    "backslashreplace" => escaped(n),
                    "xmlcharrefreplace" => format!("&#{n};"),
                    "surrogateescape" if (0xdc80..=0xdcff).contains(&n) => {
                        out.push((n - 0xdc00) as u8);
                        index += 1;
                        continue;
                    }
                    "strict" | "surrogateescape" | "surrogatepass" => {
                        let mut end = index + 1;
                        while end < points.len()
                            && match name {
                                "ascii" => points[end] > 127,
                                "latin-1" => points[end] > 255,
                                "charmap" => {
                                    !(points[end] <= 127
                                        || (160..=255).contains(&points[end])
                                        || (points[end] > 255 && cp1252.contains(&points[end])))
                                }
                                _ => (0xd800..=0xdfff).contains(&points[end]),
                            }
                        {
                            end += 1;
                        }
                        return Err(encode_error(
                            name,
                            &points,
                            index,
                            end,
                            if name == "ascii" {
                                "ordinal not in range(128)"
                            } else if name == "latin-1" {
                                "ordinal not in range(256)"
                            } else if name == "charmap" {
                                "character maps to <undefined>"
                            } else {
                                "surrogates not allowed"
                            },
                        ));
                    }
                    _ => {
                        return Err(format!(
                            "LookupError: unknown error handler name '{}'",
                            handler
                        ));
                    }
                };
                if name.starts_with("utf-16") {
                    for u in replacement.encode_utf16() {
                        out.extend(if name.ends_with("be") {
                            u.to_be_bytes()
                        } else {
                            u.to_le_bytes()
                        });
                    }
                } else if name.starts_with("utf-32") {
                    for c in replacement.chars() {
                        out.extend(if name.ends_with("be") {
                            u32::from(c).to_be_bytes()
                        } else {
                            u32::from(c).to_le_bytes()
                        });
                    }
                } else {
                    out.extend(replacement.as_bytes());
                }
            } else if name.starts_with("utf-16") {
                if n <= 0xffff {
                    let u = n as u16;
                    out.extend(if name.ends_with("be") {
                        u.to_be_bytes()
                    } else {
                        u.to_le_bytes()
                    });
                } else {
                    for u in [
                        0xd800 + ((n - 0x10000) >> 10) as u16,
                        0xdc00 + ((n - 0x10000) & 0x3ff) as u16,
                    ] {
                        out.extend(if name.ends_with("be") {
                            u.to_be_bytes()
                        } else {
                            u.to_le_bytes()
                        });
                    }
                }
            } else if name.starts_with("utf-32") {
                out.extend(if name.ends_with("be") {
                    n.to_be_bytes()
                } else {
                    n.to_le_bytes()
                });
            } else if name == "utf-8" {
                if let Some(c) = char::from_u32(n) {
                    out.extend(c.encode_utf8(&mut [0; 4]).as_bytes());
                } else {
                    out.extend([
                        0xe0 | ((n >> 12) as u8),
                        0x80 | (((n >> 6) & 63) as u8),
                        0x80 | ((n & 63) as u8),
                    ]);
                }
            } else if let Some(b) = byte {
                out.push(b);
            }
            index += 1;
        }
    }
    Ok(out)
}
