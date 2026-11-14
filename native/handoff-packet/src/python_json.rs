//! Python JSON admission without serde's number, Unicode or nesting restrictions.
//! Keep Python-only scalar values typed until the consuming protocol inspects them.
pub use crate::mir_cli::bootstrap_adoption::{is_python_space, python_splitlines};
use std::fmt;
use std::ops::Index;
pub fn python_strip(text: &str) -> &str {
    text.trim_matches(crate::mir_cli::bootstrap_adoption::is_python_space)
}

#[derive(Clone, Debug, PartialEq)]
pub struct Text {
    pub codepoints: Vec<u32>,
    text: Option<String>,
}
impl Text {
    pub(crate) fn new(codepoints: Vec<u32>) -> Self {
        let text = codepoints.iter().map(|c| char::from_u32(*c)).collect();
        Self { codepoints, text }
    }
    pub fn as_str(&self) -> Option<&str> {
        self.text.as_deref()
    }
    pub fn has_surrogates(&self) -> bool {
        self.text.is_none()
    }
    pub fn is_empty(&self) -> bool {
        self.codepoints.is_empty()
    }
    pub fn py_str(&self) -> String {
        self.codepoints
            .iter()
            .map(|c| char::from_u32(*c).map_or_else(|| format!("\\u{c:04x}"), |c| c.to_string()))
            .collect()
    }
    pub fn repr(&self) -> String {
        if let Some(text) = self.as_str() {
            return crate::executor_development_packet::py_repr(text);
        }
        let quote = if self.codepoints.contains(&u32::from('\''))
            && !self.codepoints.contains(&u32::from('"'))
        {
            '"'
        } else {
            '\''
        };
        let mut out = quote.to_string();
        for cp in &self.codepoints {
            match char::from_u32(*cp) {
                Some(c) if c == quote || c == '\\' => {
                    out.push('\\');
                    out.push(c);
                }
                Some(c) => {
                    // Reuse the frozen Python 3.12 printable table, including
                    // format/private/unassigned scalars next to lone surrogates.
                    let escaped = crate::executor_development_packet::py_repr(&c.to_string());
                    out.push_str(&escaped[1..escaped.len() - 1]);
                }
                None => out.push_str(&format!("\\u{cp:04x}")),
            }
        }
        out.push(quote);
        out
    }
}
#[derive(Clone, Debug, PartialEq)]
pub struct Number {
    pub token: String,
}
impl Number {
    pub fn is_integer(&self) -> bool {
        !self.token.contains(['.', 'e', 'E'])
            && !matches!(self.token.as_str(), "NaN" | "Infinity" | "-Infinity")
    }
    pub fn py_str(&self) -> String {
        match self.token.as_str() {
            "NaN" => "nan".into(),
            "Infinity" => "inf".into(),
            "-Infinity" => "-inf".into(),
            _ if self.is_integer() => {
                if self.token == "-0" {
                    "0".into()
                } else {
                    self.token.clone()
                }
            }
            _ => match self.token.parse::<f64>() {
                Ok(n) if n.is_infinite() => {
                    if n.is_sign_negative() {
                        "-inf".into()
                    } else {
                        "inf".into()
                    }
                }
                Ok(n) => {
                    let mut value = format!("{n:?}");
                    if let Some((m, e)) = value.split_once('e')
                        && let Ok(e) = e.parse::<i32>()
                    {
                        value = format!("{m}e{e:+03}");
                    }
                    value
                }
                Err(_) => self.token.clone(),
            },
        }
    }
}
#[derive(Clone, Debug, PartialEq, Default)]
pub struct Object(Vec<(Text, Value)>);
impl Object {
    pub fn into_entries(self) -> Vec<(Text, Value)> {
        self.0
    }
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.0
            .iter()
            .find(|(k, _)| k.as_str() == Some(key))
            .map(|(_, v)| v)
    }
    pub fn iter(&self) -> impl Iterator<Item = (&Text, &Value)> {
        self.0.iter().map(|(k, v)| (k, v))
    }
    pub fn keys(&self) -> impl Iterator<Item = &Text> {
        self.0.iter().map(|(k, _)| k)
    }
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
    pub fn len(&self) -> usize {
        self.0.len()
    }
    pub(crate) fn get_mut(&mut self, key: &str) -> Option<&mut Value> {
        self.0
            .iter_mut()
            .find(|(name, _)| name.as_str() == Some(key))
            .map(|(_, value)| value)
    }
    pub(crate) fn insert(&mut self, key: Text, value: Value) {
        if let Some((_, v)) = self.0.iter_mut().find(|(k, _)| *k == key) {
            discard(std::mem::replace(v, value));
        } else {
            self.0.push((key, value));
        }
    }
}
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Number(Number),
    String(Text),
    Array(Vec<Value>),
    Object(Object),
}
impl Value {
    pub fn get(&self, key: &str) -> Option<&Self> {
        self.as_object()?.get(key)
    }
    pub fn as_str(&self) -> Option<&str> {
        if let Self::String(s) = self {
            s.as_str()
        } else {
            None
        }
    }
    pub fn as_text(&self) -> Option<&Text> {
        if let Self::String(s) = self {
            Some(s)
        } else {
            None
        }
    }
    pub fn as_array(&self) -> Option<&Vec<Self>> {
        if let Self::Array(a) = self {
            Some(a)
        } else {
            None
        }
    }
    pub fn as_object(&self) -> Option<&Object> {
        if let Self::Object(o) = self {
            Some(o)
        } else {
            None
        }
    }
    pub fn is_null(&self) -> bool {
        matches!(self, Self::Null)
    }
    pub fn is_object(&self) -> bool {
        matches!(self, Self::Object(_))
    }
    pub fn is_array(&self) -> bool {
        matches!(self, Self::Array(_))
    }
    pub fn type_name(&self) -> &'static str {
        match self {
            Self::Null => "NoneType",
            Self::Bool(_) => "bool",
            Self::Number(n) if n.is_integer() => "int",
            Self::Number(_) => "float",
            Self::String(_) => "str",
            Self::Array(_) => "list",
            Self::Object(_) => "dict",
        }
    }
    pub fn truthy(&self) -> bool {
        match self {
            Self::Null => false,
            Self::Bool(b) => *b,
            Self::Number(n) => n.token.parse::<f64>() != Ok(0.0),
            Self::String(s) => !s.is_empty(),
            Self::Array(a) => !a.is_empty(),
            Self::Object(o) => !o.is_empty(),
        }
    }
    pub fn py_str(&self) -> String {
        match self {
            Self::String(s) => s.py_str(),
            _ => self.repr(),
        }
    }
    pub fn repr(&self) -> String {
        match self {
            Self::Null => "None".into(),
            Self::Bool(b) => if *b { "True" } else { "False" }.into(),
            Self::Number(n) => n.py_str(),
            Self::String(s) => s.repr(),
            Self::Array(a) => format!(
                "[{}]",
                a.iter().map(Self::repr).collect::<Vec<_>>().join(", ")
            ),
            Self::Object(o) => format!(
                "{{{}}}",
                o.iter()
                    .map(|(k, v)| format!("{}: {}", k.repr(), v.repr()))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
        }
    }
    /// The lifecycle guard consumes string/bool/container shapes, not numeric
    /// magnitudes. Unsupported numbers remain scalar numbers. Surrogates become
    /// input-absent nonword/nonspace scalars, never a string supplied by a caller.
    pub fn to_serde(&self) -> serde_json::Value {
        let mut used = std::collections::HashSet::new();
        let mut pending = vec![self];
        while let Some(value) = pending.pop() {
            match value {
                Self::String(t) => used.extend(t.codepoints.iter().copied()),
                Self::Array(a) => pending.extend(a),
                Self::Object(o) => {
                    for (k, v) in o.iter() {
                        used.extend(k.codepoints.iter().copied());
                        pending.push(v);
                    }
                }
                _ => (),
            }
        }
        let mut replacements = std::collections::HashMap::new();
        let mut candidates = (0..=0x10ffff)
            .rev()
            .filter_map(char::from_u32)
            .filter(|c| !c.is_alphanumeric() && !c.is_whitespace());
        for cp in 0xd800..=0xdfff {
            if used.contains(&cp)
                && let Some(c) = candidates.find(|c| !used.contains(&u32::from(*c)))
            {
                replacements.insert(cp, c);
            }
        }
        enum Work<'a> {
            Node(&'a Value),
            Array(usize),
            Object(Vec<String>),
        }
        let text = |t: &Text| {
            t.codepoints
                .iter()
                .filter_map(|c| char::from_u32(*c).or_else(|| replacements.get(c).copied()))
                .collect::<String>()
        };
        let mut work = vec![Work::Node(self)];
        let mut output = Vec::new();
        while let Some(item) = work.pop() {
            match item {
                Work::Node(Self::Array(a)) => {
                    work.push(Work::Array(a.len()));
                    work.extend(a.iter().rev().map(Work::Node));
                }
                Work::Node(Self::Object(o)) => {
                    work.push(Work::Object(o.keys().map(&text).collect()));
                    work.extend(
                        o.iter()
                            .map(|(_, v)| v)
                            .collect::<Vec<_>>()
                            .into_iter()
                            .rev()
                            .map(Work::Node),
                    );
                }
                Work::Node(v) => output.push(match v {
                    Self::Null => serde_json::Value::Null,
                    Self::Bool(b) => (*b).into(),
                    Self::Number(n) => serde_json::Value::Number(
                        serde_json::from_str::<serde_json::Number>(&n.token)
                            .unwrap_or_else(|_| serde_json::Number::from(1)),
                    ),
                    Self::String(t) => text(t).into(),
                    Self::Array(_) | Self::Object(_) => unreachable!(),
                }),
                Work::Array(len) => {
                    let children = output.split_off(output.len() - len);
                    output.push(serde_json::Value::Array(children));
                }
                Work::Object(keys) => {
                    let children = output.split_off(output.len() - keys.len());
                    output.push(serde_json::Value::Object(
                        keys.into_iter().zip(children).collect(),
                    ));
                }
            }
        }
        output.pop().unwrap_or(serde_json::Value::Null)
    }
}
/// Dispose of Python-depth JSON without recursive Rust enum destruction.
pub(crate) fn discard(value: Value) {
    let mut pending = vec![value];
    while let Some(value) = pending.pop() {
        match value {
            Value::Array(values) => pending.extend(values),
            Value::Object(fields) => {
                pending.extend(fields.into_entries().into_iter().map(|(_, v)| v))
            }
            _ => (),
        }
    }
}
impl Index<&str> for Value {
    type Output = Self;
    fn index(&self, key: &str) -> &Self {
        static NULL: Value = Value::Null;
        self.get(key).unwrap_or(&NULL)
    }
}
impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.py_str())
    }
}
impl fmt::Display for Text {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.py_str())
    }
}
impl PartialEq<str> for Text {
    fn eq(&self, other: &str) -> bool {
        self.as_str() == Some(other)
    }
}

#[derive(Debug)]
pub struct Error {
    pub exception: &'static str,
    pub message: String,
    pub line: usize,
    pub column: usize,
    pub position: usize,
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.exception == "JSONDecodeError" {
            write!(
                f,
                "{}: line {} column {} (char {})",
                self.message, self.line, self.column, self.position
            )
        } else {
            f.write_str(&self.message)
        }
    }
}
struct Reader {
    chars: Vec<u32>,
    offset: usize,
}
impl Reader {
    fn error(&self, message: &str, position: usize) -> Error {
        let prefix = &self.chars[..position.min(self.chars.len())];
        Error {
            exception: "JSONDecodeError",
            message: message.into(),
            line: 1 + prefix.iter().filter(|c| **c == 10).count(),
            column: prefix
                .iter()
                .rposition(|c| *c == 10)
                .map_or(position + 1, |n| position - n),
            position,
        }
    }
    fn peek(&self) -> Option<u32> {
        self.chars.get(self.offset).copied()
    }
    fn space(&mut self) {
        while self.peek().is_some_and(|c| matches!(c, 9 | 10 | 13 | 32)) {
            self.offset += 1;
        }
    }
    fn take(&mut self, s: &str) -> bool {
        if self
            .chars
            .get(self.offset..self.offset + s.len())
            .is_some_and(|chars| chars.iter().copied().eq(s.chars().map(u32::from)))
        {
            self.offset += s.len();
            true
        } else {
            false
        }
    }
    fn string(&mut self) -> Result<Text, Error> {
        let start = self.offset;
        self.offset += 1;
        let mut out = Vec::new();
        while let Some(cp) = self.peek() {
            self.offset += 1;
            match cp {
                34 => return Ok(Text::new(out)),
                92 => {
                    let slash = self.offset - 1;
                    let Some(escape) = self.peek() else {
                        return Err(self.error("Unterminated string starting at", start));
                    };
                    self.offset += 1;
                    let decoded = match escape {
                        34 | 47 | 92 => escape,
                        98 => 8,
                        102 => 12,
                        110 => 10,
                        114 => 13,
                        116 => 9,
                        117 => {
                            let position = self.offset - 1;
                            let mut unit = 0;
                            for _ in 0..4 {
                                let digit = self
                                    .peek()
                                    .and_then(char::from_u32)
                                    .and_then(|c| c.to_digit(16))
                                    .ok_or_else(|| {
                                        self.error("Invalid \\uXXXX escape", position)
                                    })?;
                                unit = unit * 16 + digit;
                                self.offset += 1;
                            }
                            if (0xd800..=0xdbff).contains(&unit)
                                && self.chars.get(self.offset..self.offset + 2) == Some(&[92, 117])
                            {
                                let low = self
                                    .chars
                                    .get(self.offset + 2..self.offset + 6)
                                    .and_then(|s| {
                                        s.iter().try_fold(0u32, |a, c| {
                                            Some(a * 16 + char::from_u32(*c)?.to_digit(16)?)
                                        })
                                    });
                                if let Some(low) = low.filter(|n| (0xdc00..=0xdfff).contains(n)) {
                                    self.offset += 6;
                                    unit = 0x10000 + ((unit - 0xd800) << 10) + low - 0xdc00;
                                }
                            }
                            unit
                        }
                        _ => return Err(self.error("Invalid \\escape", slash)),
                    };
                    out.push(decoded);
                }
                0..=31 => return Err(self.error("Invalid control character at", self.offset - 1)),
                _ => out.push(cp),
            }
        }
        Err(self.error("Unterminated string starting at", start))
    }
    fn scalar(&mut self) -> Result<Value, Error> {
        if self.peek() == Some(34) {
            return self.string().map(Value::String);
        }
        for (token, value) in [
            ("null", Value::Null),
            ("true", Value::Bool(true)),
            ("false", Value::Bool(false)),
        ] {
            if self.take(token) {
                return Ok(value);
            }
        }
        for token in ["NaN", "Infinity", "-Infinity"] {
            if self.take(token) {
                return Ok(Value::Number(Number {
                    token: token.into(),
                }));
            }
        }
        let start = self.offset;
        if self.peek() == Some(45) {
            self.offset += 1;
        }
        match self.peek() {
            Some(48) => self.offset += 1,
            Some(49..=57) => {
                while self.peek().is_some_and(|c| (48..=57).contains(&c)) {
                    self.offset += 1;
                }
            }
            _ => return Err(self.error("Expecting value", start)),
        }
        if self.peek() == Some(46)
            && self
                .chars
                .get(self.offset + 1)
                .is_some_and(|c| (48..=57).contains(c))
        {
            self.offset += 2;
            while self.peek().is_some_and(|c| (48..=57).contains(&c)) {
                self.offset += 1;
            }
        }
        if matches!(self.peek(), Some(69 | 101)) {
            let exponent = self.offset;
            self.offset += 1;
            if matches!(self.peek(), Some(43 | 45)) {
                self.offset += 1;
            }
            let digits = self.offset;
            while self.peek().is_some_and(|c| (48..=57).contains(&c)) {
                self.offset += 1;
            }
            if self.offset == digits {
                self.offset = exponent;
            }
        }
        let number = Number {
            token: self.chars[start..self.offset]
                .iter()
                .filter_map(|c| char::from_u32(*c))
                .collect(),
        };
        let digits = number.token.len() - usize::from(number.token.starts_with('-'));
        if number.is_integer() && digits > 4300 {
            let mut e=self.error(&format!("Exceeds the limit (4300 digits) for integer string conversion: value has {digits} digits; use sys.set_int_max_str_digits() to increase the limit"),start);
            e.exception = "ValueError";
            return Err(e);
        }
        Ok(Value::Number(number))
    }
}
enum Frame {
    Array(Vec<Value>, bool),
    Object(Object, Option<Text>, bool),
}
impl Drop for Frame {
    fn drop(&mut self) {
        discard(match self {
            Frame::Array(values, _) => Value::Array(std::mem::take(values)),
            Frame::Object(fields, _, _) => Value::Object(std::mem::take(fields)),
        });
    }
}
fn parse_codes(chars: Vec<u32>) -> Result<Value, Error> {
    let mut r = Reader { chars, offset: 0 };
    if r.peek() == Some(0xfeff) {
        return Err(r.error("Unexpected UTF-8 BOM (decode using utf-8-sig)", 0));
    }
    let mut stack = Vec::new();
    let mut value = None;
    loop {
        if let Some(v) = value.take() {
            match stack.last_mut() {
                Some(Frame::Array(a, after)) => {
                    a.push(v);
                    *after = true;
                }
                Some(Frame::Object(o, key, after)) => {
                    if let Some(key) = key.take() {
                        o.insert(key, v);
                    }
                    *after = true;
                }
                None => {
                    r.space();
                    return if r.peek().is_none() {
                        Ok(v)
                    } else {
                        discard(v);
                        Err(r.error("Extra data", r.offset))
                    };
                }
            }
        }
        r.space();
        let mut close = false;
        match stack.last_mut() {
            Some(Frame::Array(_, after)) if *after => match r.peek() {
                Some(93) => close = true,
                Some(44) => {
                    r.offset += 1;
                    r.space();
                    *after = false;
                    if r.peek() == Some(93) {
                        return Err(r.error("Expecting value", r.offset));
                    }
                }
                _ => return Err(r.error("Expecting ',' delimiter", r.offset)),
            },
            Some(Frame::Array(a, _)) if a.is_empty() && r.peek() == Some(93) => close = true,
            Some(Frame::Object(_, _, after)) if *after => match r.peek() {
                Some(125) => close = true,
                Some(44) => {
                    r.offset += 1;
                    r.space();
                    *after = false;
                    if r.peek() != Some(34) {
                        return Err(r.error(
                            "Expecting property name enclosed in double quotes",
                            r.offset,
                        ));
                    }
                }
                _ => return Err(r.error("Expecting ',' delimiter", r.offset)),
            },
            Some(Frame::Object(o, _, _)) if o.is_empty() && r.peek() == Some(125) => close = true,
            _ => (),
        }
        if close {
            r.offset += 1;
            value = stack.pop().map(|mut frame| match &mut frame {
                Frame::Array(a, _) => Value::Array(std::mem::take(a)),
                Frame::Object(o, _, _) => Value::Object(std::mem::take(o)),
            });
            continue;
        }
        if let Some(Frame::Object(_, key, _)) = stack.last_mut() {
            if r.peek() != Some(34) {
                return Err(r.error(
                    "Expecting property name enclosed in double quotes",
                    r.offset,
                ));
            }
            *key = Some(r.string()?);
            r.space();
            if r.peek() != Some(58) {
                return Err(r.error("Expecting ':' delimiter", r.offset));
            }
            r.offset += 1;
            r.space();
        }
        match r.peek() {
            Some(91 | 123) => {
                let object = r.peek() == Some(123);
                if stack.len() >= 9997 {
                    let mut e=r.error(if object {"maximum recursion depth exceeded while decoding a JSON object from a unicode string"} else {"maximum recursion depth exceeded while decoding a JSON array from a unicode string"},r.offset);
                    e.exception = "RecursionError";
                    return Err(e);
                }
                r.offset += 1;
                stack.push(if object {
                    Frame::Object(Object::default(), None, false)
                } else {
                    Frame::Array(Vec::new(), false)
                });
            }
            _ => value = Some(r.scalar()?),
        }
    }
}
pub fn parse(text: &str) -> Result<Value, Error> {
    parse_codes(text.chars().map(u32::from).collect())
}

/// Parse already decoded Python text without losing lone surrogate code points.
pub fn parse_codepoints(codepoints: Vec<u32>) -> Result<Value, Error> {
    parse_codes(codepoints)
}

/// sys.stdin uses UTF-8 with surrogateescape: undecodable bytes remain codepoints.
pub fn parse_stdin(bytes: &[u8]) -> Result<Value, Error> {
    let mut chars = Vec::new();
    let mut remaining = bytes;
    while !remaining.is_empty() {
        match std::str::from_utf8(remaining) {
            Ok(s) => {
                chars.extend(s.chars().map(u32::from));
                break;
            }
            Err(e) => {
                let valid = e.valid_up_to();
                if let Ok(s) = std::str::from_utf8(&remaining[..valid]) {
                    chars.extend(s.chars().map(u32::from));
                }
                let count = e.error_len().unwrap_or(remaining.len() - valid);
                chars.extend(
                    remaining[valid..valid + count]
                        .iter()
                        .map(|b| 0xdc00 + u32::from(*b)),
                );
                remaining = &remaining[valid + count..];
            }
        }
    }
    // TextIOWrapper's universal newline translation precedes read(LIMIT+1).
    let mut normalized = Vec::with_capacity(chars.len());
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == 13 {
            normalized.push(10);
            i += 1;
            if chars.get(i) == Some(&10) {
                i += 1;
            }
        } else {
            normalized.push(chars[i]);
            i += 1;
        }
    }
    let chars = normalized;
    if chars.len() > crate::LIMIT {
        let r = Reader { chars, offset: 0 };
        return Err(r.error("oversized hook payload", 0));
    }
    parse_codes(chars)
}
