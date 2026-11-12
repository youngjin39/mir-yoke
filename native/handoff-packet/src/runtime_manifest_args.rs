//! Compatibility parser for the pinned runtime-manifest argparse entry point.
use std::{collections::BTreeMap, ffi::OsString};

const OPTIONS: [&str; 5] = [
    "--runtime-root",
    "--manifest",
    "--source-url",
    "--source-commit",
    "--constraints-sha256",
];

pub enum Parsed {
    Run {
        command: String,
        options: BTreeMap<String, OsString>,
    },
    Exit {
        code: i32,
        stdout: String,
        stderr: String,
    },
}

fn usage(command: &str) -> String {
    if command.is_empty() {
        "usage: mir runtime-manifest [-h] {create,verify} ...\n".into()
    } else {
        // Both subcommand names have the same width in argparse's formatter.
        format!(
            "usage: mir runtime-manifest {command} [-h] --runtime-root RUNTIME_ROOT --manifest\n                                   MANIFEST --source-url SOURCE_URL\n                                   --source-commit SOURCE_COMMIT\n                                   --constraints-sha256 CONSTRAINTS_SHA256\n"
        )
    }
}

fn error(command: &str, message: String) -> Parsed {
    let program = if command.is_empty() {
        "mir runtime-manifest".into()
    } else {
        format!("mir runtime-manifest {command}")
    };
    Parsed::Exit {
        code: 2,
        stdout: String::new(),
        stderr: format!("{}{program}: error: {message}\n", usage(command)),
    }
}

fn help(command: &str) -> Parsed {
    let detail = if command.is_empty() {
        "\npositional arguments:\n  {create,verify}\n\noptions:\n  -h, --help       show this help message and exit\n"
    } else {
        "\noptions:\n  -h, --help            show this help message and exit\n  --runtime-root RUNTIME_ROOT\n  --manifest MANIFEST\n  --source-url SOURCE_URL\n  --source-commit SOURCE_COMMIT\n  --constraints-sha256 CONSTRAINTS_SHA256\n"
    };
    Parsed::Exit {
        code: 0,
        stdout: usage(command) + detail,
        stderr: String::new(),
    }
}

// Decode argv like Python's surrogateescape, preserving undecodable native bytes.
fn codepoints(value: &std::ffi::OsStr) -> Vec<u32> {
    let mut remaining = value.as_encoded_bytes();
    let mut result = Vec::new();
    while !remaining.is_empty() {
        match std::str::from_utf8(remaining) {
            Ok(valid) => {
                result.extend(valid.chars().map(u32::from));
                break;
            }
            Err(err) => {
                let (valid, tail) = remaining.split_at(err.valid_up_to());
                if let Ok(valid) = std::str::from_utf8(valid) {
                    result.extend(valid.chars().map(u32::from));
                }
                let count = err.error_len().unwrap_or(tail.len());
                result.extend(tail[..count].iter().map(|byte| 0xdc00 + u32::from(*byte)));
                remaining = &tail[count..];
            }
        }
    }
    result
}

fn text(value: &std::ffi::OsStr) -> String {
    codepoints(value)
        .into_iter()
        .map(|cp| char::from_u32(cp).map_or_else(|| format!("\\u{cp:04x}"), |c| c.to_string()))
        .collect()
}

fn repr(value: &std::ffi::OsStr) -> String {
    // Reuse the library's frozen Python printable table and surrogate handling.
    let mut json = String::from("\"");
    for cp in codepoints(value) {
        if cp <= 0xffff {
            json.push_str(&format!("\\u{cp:04x}"));
        } else if let Some(ch) = char::from_u32(cp) {
            json.push(ch);
        }
    }
    json.push('"');
    match handoff_packet::python_json::parse(&json) {
        Ok(value) => value.repr(),
        // The escaped string constructed above is always valid JSON.
        Err(_) => "'<invalid argv>'".into(),
    }
}

enum Token {
    Value,
    End,
    Unknown,
    Option {
        matches: Vec<&'static str>,
        explicit: Option<OsString>,
        short_tail: bool,
    },
}

fn suffix(value: &std::ffi::OsStr, offset: usize) -> OsString {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStringExt;
        OsString::from_vec(value.as_encoded_bytes()[offset..].to_vec())
    }
    #[cfg(not(unix))]
    {
        OsString::from(&text(value)[offset..])
    }
}

fn classify(value: &std::ffi::OsStr, child: bool) -> Token {
    let raw = value;
    let display = text(value);
    let value = display.as_str();
    if value == "--" {
        return Token::End;
    }
    if !value.starts_with('-') || value == "-" {
        return Token::Value;
    }
    let (name, explicit) = match value.split_once('=') {
        Some((name, _)) => {
            let bytes = raw.as_encoded_bytes();
            let offset = bytes.iter().position(|b| *b == b'=').unwrap_or(bytes.len());
            // The split is at an ASCII delimiter in the original native string.
            (name, Some(suffix(raw, offset + 1)))
        }
        None => (value, None),
    };
    let known = std::iter::once("--help").chain(OPTIONS.into_iter().filter(|_| child));
    if name == "-h" || name == "--help" || (child && OPTIONS.contains(&name)) {
        return Token::Option {
            matches: vec![if name == "-h" {
                "--help"
            } else {
                // All supported names are static strings.
                known.clone().find(|n| *n == name).unwrap_or("--help")
            }],
            explicit,
            short_tail: false,
        };
    }
    let matches: Vec<_> = if name.starts_with("--") {
        known.filter(|option| option.starts_with(name)).collect()
    } else {
        Vec::new()
    };
    if !matches.is_empty() {
        return Token::Option {
            matches,
            explicit,
            short_tail: false,
        };
    }
    if let Some(mut tail) = value.strip_prefix("-h") {
        // Validate the complete cluster before taking the first help action.
        let mut offset = 2;
        loop {
            if tail.starts_with('=') {
                return Token::Option {
                    matches: vec!["--help"],
                    explicit: Some(suffix(raw, offset + 1)),
                    short_tail: false,
                };
            }
            if tail.starts_with('-') {
                return Token::Option {
                    matches: vec!["--help"],
                    explicit: Some(suffix(raw, offset)),
                    short_tail: false,
                };
            }
            if let Some(rest) = tail.strip_prefix('h') {
                tail = rest;
                offset += 1;
            } else {
                break;
            }
        }
        return Token::Option {
            matches: vec!["--help"],
            explicit: None,
            short_tail: true,
        };
    }
    let negative = value.strip_prefix('-').is_some_and(|number| {
        let number = number.strip_suffix('\n').unwrap_or(number);
        let mut parts = number.split('.');
        let first = parts.next().unwrap_or_default();
        match parts.next() {
            None => !first.is_empty() && first.chars().all(decimal),
            Some(second) => {
                first.chars().all(decimal)
                    && !second.is_empty()
                    && second.chars().all(decimal)
                    && parts.next().is_none()
            }
        }
    });
    if negative || value.contains(' ') {
        Token::Value
    } else {
        Token::Unknown
    }
}

fn normalized(value: OsString) -> OsString {
    // pathlib.Path removes empty and dot components but preserves exactly two
    // leading slashes. Work on native bytes to preserve surrogateescaped argv.
    #[cfg(unix)]
    {
        use std::os::unix::ffi::{OsStrExt, OsStringExt};
        let bytes = value.as_os_str().as_bytes();
        let prefix = if bytes.starts_with(b"//") && !bytes.starts_with(b"///") {
            b"//".as_slice()
        } else if bytes.starts_with(b"/") {
            b"/".as_slice()
        } else {
            b"".as_slice()
        };
        let mut result = prefix.to_vec();
        for part in bytes
            .split(|b| *b == b'/')
            .filter(|p| !p.is_empty() && *p != b".")
        {
            if !result.is_empty() && !result.ends_with(b"/") {
                result.push(b'/');
            }
            result.extend_from_slice(part);
        }
        if result.is_empty() {
            result.push(b'.');
        }
        OsString::from_vec(result)
    }
    #[cfg(not(unix))]
    {
        std::path::PathBuf::from(value)
            .components()
            .collect::<std::path::PathBuf>()
            .into_os_string()
    }
}

pub fn parse(args: Vec<OsString>) -> Parsed {
    let mut command = String::new();
    let mut options = BTreeMap::new();
    let mut extras = Vec::new();
    let mut index = 0;
    let mut ended = false;
    while index < args.len() {
        let token = if ended {
            Token::Value
        } else {
            classify(&args[index], !command.is_empty())
        };
        match token {
            Token::End => {
                ended = true;
                if !command.is_empty() {
                    extras.push(text(&args[index]));
                }
                index += 1;
            }
            Token::Value if command.is_empty() => {
                let candidate = text(&args[index]);
                if candidate != "create" && candidate != "verify" {
                    return error(
                        "",
                        format!(
                            "argument command: invalid choice: {} (choose from create, verify)",
                            repr(&args[index])
                        ),
                    );
                }
                command = candidate;
                ended = false;
                index += 1;
            }
            Token::Value | Token::Unknown => {
                extras.push(text(&args[index]));
                index += 1;
            }
            Token::Option {
                matches,
                explicit,
                short_tail,
            } => {
                if matches.len() > 1 {
                    return error(
                        &command,
                        format!(
                            "ambiguous option: {} could match {}",
                            text(&args[index]),
                            matches.join(", ")
                        ),
                    );
                }
                let name = matches[0];
                if name == "--help" {
                    if let Some(value) = explicit
                        && !short_tail
                    {
                        return error(
                            &command,
                            format!(
                                "argument -h/--help: ignored explicit argument {}",
                                repr(&value)
                            ),
                        );
                    }
                    return help(&command);
                }
                let value = if let Some(value) = explicit {
                    index += 1;
                    value
                } else {
                    if index + 1 >= args.len()
                        || !matches!(classify(&args[index + 1], true), Token::Value)
                    {
                        return error(&command, format!("argument {name}: expected one argument"));
                    }
                    index += 2;
                    args[index - 1].clone()
                };
                options.insert(
                    name.to_string(),
                    if name == "--runtime-root" || name == "--manifest" {
                        normalized(value)
                    } else {
                        value
                    },
                );
            }
        }
    }
    if command.is_empty() {
        return error("", "the following arguments are required: command".into());
    }
    let missing: Vec<_> = OPTIONS
        .into_iter()
        .filter(|name| !options.contains_key(*name))
        .collect();
    if !missing.is_empty() {
        return error(
            &command,
            format!(
                "the following arguments are required: {}",
                missing.join(", ")
            ),
        );
    }
    if !extras.is_empty() {
        return error("", format!("unrecognized arguments: {}", extras.join(" ")));
    }
    Parsed::Run { command, options }
}

fn decimal(c: char) -> bool {
    const ZEROES: &[u32] = &[
        0x30, 0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6, 0xd66,
        0xde6, 0xe50, 0xed0, 0xf20, 0x1040, 0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0, 0x1a80, 0x1a90,
        0x1b50, 0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0, 0xaa50, 0xabf0,
        0xff10, 0x104a0, 0x10d30, 0x11066, 0x110f0, 0x11136, 0x111d0, 0x112f0, 0x11450, 0x114d0,
        0x11650, 0x116c0, 0x11730, 0x118e0, 0x11950, 0x11c50, 0x11d50, 0x11da0, 0x11f50, 0x16a60,
        0x16ac0, 0x16b50, 0x1d7ce, 0x1d7d8, 0x1d7e2, 0x1d7ec, 0x1d7f6, 0x1e140, 0x1e2f0, 0x1e4f0,
        0x1e950, 0x1fbf0,
    ];
    let cp = c as u32;
    ZEROES
        .partition_point(|zero| *zero <= cp)
        .checked_sub(1)
        .is_some_and(|index| cp - ZEROES[index] < 10)
}
