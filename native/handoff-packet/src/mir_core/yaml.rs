//! YAML 1.1 Reader -> Scanner -> Parser/Composer -> Resolver, without construction.
use std::collections::BTreeMap;
use std::sync::OnceLock;

#[derive(Clone, Copy)]
pub enum Input<'a> {
    Text(&'a str),
    Bytes(&'a [u8]),
}
#[derive(Debug)]
pub struct YamlError {
    pub class: &'static str,
    pub message: String,
}
type Result<T> = std::result::Result<T, YamlError>;
fn error(class: &'static str) -> YamlError {
    YamlError {
        class,
        message: format!("invalid YAML ({class})"),
    }
}
#[derive(Debug)]
pub enum Kind {
    Scalar(String),
    Sequence(Vec<usize>),
    Mapping(Vec<(usize, usize)>),
}
#[derive(Debug)]
pub struct NodeData {
    pub kind: Kind,
    pub tag: String,
    pub style: Option<char>,
    pub line: usize,
    pub column: usize,
    pub end_line: usize,
}
/// Arena indices preserve shared and cyclic aliases without reference-count cycles.
#[derive(Debug)]
pub struct Node {
    pub arena: Vec<NodeData>,
    pub root: usize,
}
const PREFIX: &str = "tag:yaml.org,2002:";
// PyYAML raises RecursionError near 490 levels, a threshold that moves with the caller's
// Python stack. The records pin 450 levels as accepted and 600 as rejected; 451-490 is a
// known divergence band (PyYAML accepts from a shallow caller, this rejects).
const DEPTH_LIMIT: usize = 450;
fn reader(input: Input<'_>) -> Result<Vec<char>> {
    let text = match input {
        Input::Text(s) => s.to_owned(),
        Input::Bytes(b) => {
            if b.starts_with(&[0xff, 0xfe]) || b.starts_with(&[0xfe, 0xff]) {
                if b.len() % 2 != 0 {
                    return Err(error("ReaderError"));
                }
                let le = b[0] == 0xff;
                let units = b.as_chunks::<2>().0.iter().map(|p| {
                    if le {
                        u16::from_le_bytes([p[0], p[1]])
                    } else {
                        u16::from_be_bytes([p[0], p[1]])
                    }
                });
                char::decode_utf16(units)
                    .collect::<std::result::Result<String, _>>()
                    .map_err(|_| error("ReaderError"))?
            } else {
                std::str::from_utf8(b)
                    .map_err(|_| error("ReaderError"))?
                    .to_owned()
            }
        }
    };
    let chars: Vec<_> = text.chars().collect();
    if chars.iter().any(|&c| {
        !matches!(c as u32,
        0x9 | 0xa | 0xd | 0x20..=0x7e | 0x85 | 0xa0..=0xd7ff |
        0xe000..=0xfffd | 0x10000..=0x10ffff)
    }) {
        return Err(error("ReaderError"));
    }
    Ok(chars)
}
#[derive(Clone, Copy, Debug, Default)]
struct Mark {
    index: usize,
    line: usize,
    column: usize,
}
// PyYAML Mark.get_snippet uses character offsets, including a leading BOM.
impl Mark {
    fn render(self, chars: &[char]) -> String {
        let (mut start, mut end) = (self.index, self.index);
        let (mut head, mut tail) = ("", "");
        while start > 0 && chars[start - 1] != '\0' && !br(chars[start - 1]) {
            start -= 1;
            if self.index - start > 36 {
                head = " ... ";
                start += 5;
                break;
            }
        }
        while end < chars.len() && chars[end] != '\0' && !br(chars[end]) {
            end += 1;
            if end - self.index > 36 {
                tail = " ... ";
                end -= 5;
                break;
            }
        }
        format!(
            "  in \"<unicode string>\", line {}, column {}:\n    {head}{}{tail}\n{}^",
            self.line + 1,
            self.column + 1,
            chars[start..end].iter().collect::<String>(),
            " ".repeat(4 + self.index - start + head.len())
        )
    }
}
fn marked(
    class: &'static str,
    chars: &[char],
    context: Option<(&str, Mark)>,
    problem: &str,
    mark: Mark,
) -> YamlError {
    let mut lines = Vec::new();
    if let Some((text, start)) = context {
        lines.push(text.to_owned());
        if (start.line, start.column) != (mark.line, mark.column) {
            lines.push(start.render(chars));
        }
    }
    lines.push(problem.to_owned());
    lines.push(mark.render(chars));
    YamlError {
        class,
        message: lines.join("\n"),
    }
}
#[derive(Clone, Debug, PartialEq)]
enum TokenKind {
    End,
    Doc,
    DocEnd,
    Directive(String),
    Seq,
    Map,
    BlockEnd,
    Dash,
    Key,
    Value,
    OpenSeq,
    CloseSeq,
    OpenMap,
    CloseMap,
    Comma,
    Scalar(String, Option<char>),
    Anchor(String),
    Alias(String),
    Tag(String, String),
}
impl TokenKind {
    fn name(&self) -> &'static str {
        match self {
            Self::End => "<stream end>",
            Self::Doc => "<document start>",
            Self::DocEnd => "<document end>",
            Self::Directive(_) => "<directive>",
            Self::Seq => "<block sequence start>",
            Self::Map => "<block mapping start>",
            Self::BlockEnd => "<block end>",
            Self::Dash => "-",
            Self::Key => "?",
            Self::Value => ":",
            Self::OpenSeq => "[",
            Self::CloseSeq => "]",
            Self::OpenMap => "{",
            Self::CloseMap => "}",
            Self::Comma => ",",
            Self::Scalar(..) => "<scalar>",
            Self::Anchor(_) => "<anchor>",
            Self::Alias(_) => "<alias>",
            Self::Tag(..) => "<tag>",
        }
    }
}
#[derive(Clone, Debug)]
struct Token {
    kind: TokenKind,
    start: Mark,
    end: Mark,
}
#[derive(Clone, Copy)]
struct SimpleKey {
    token: usize,
    index: usize,
    mark: Mark,
    required: bool,
}
struct Scanner {
    chars: Vec<char>,
    pos: usize,
    mark: Mark,
    flow: usize,
    indent: isize,
    indents: Vec<isize>,
    allow: bool,
    keys: BTreeMap<usize, SimpleKey>,
    tokens: Vec<Token>,
}
fn br(c: char) -> bool {
    "\r\n\u{85}\u{2028}\u{2029}".contains(c)
}
fn blank(c: char) -> bool {
    c == '\0' || c == ' ' || c == '\t' || br(c)
}
impl Scanner {
    fn peek(&self, n: usize) -> char {
        self.chars.get(self.pos + n).copied().unwrap_or('\0')
    }
    fn advance(&mut self) {
        let c = self.peek(0);
        self.pos += 1;
        self.mark.index = self.pos;
        if c == '\n'
            || c == '\u{85}'
            || c == '\u{2028}'
            || c == '\u{2029}'
            || (c == '\r' && self.peek(0) != '\n')
        {
            self.mark.line += 1;
            self.mark.column = 0;
        } else if c != '\u{feff}' {
            self.mark.column += 1;
        }
    }
    fn line_break(&mut self) -> String {
        let c = self.peek(0);
        if !br(c) {
            return String::new();
        }
        self.advance();
        if c == '\r' && self.peek(0) == '\n' {
            self.advance();
        }
        if c == '\u{2028}' || c == '\u{2029}' {
            c.to_string()
        } else {
            "\n".into()
        }
    }
    fn emit(&mut self, kind: TokenKind, start: Mark) {
        self.tokens.push(Token {
            kind,
            start,
            end: self.mark,
        });
    }
    fn remove_key(&mut self) -> Result<()> {
        if self.keys.remove(&self.flow).is_some_and(|k| k.required) {
            return Err(error("ScannerError"));
        }
        Ok(())
    }
    fn save_key(&mut self) -> Result<()> {
        if self.allow {
            self.remove_key()?;
            self.keys.insert(
                self.flow,
                SimpleKey {
                    token: self.tokens.len(),
                    index: self.pos,
                    mark: self.mark,
                    required: self.flow == 0 && self.indent == self.mark.column as isize,
                },
            );
        }
        Ok(())
    }
    fn add_indent(&mut self, column: usize) -> bool {
        if self.indent < column as isize {
            self.indents.push(self.indent);
            self.indent = column as isize;
            true
        } else {
            false
        }
    }
    fn unwind(&mut self, col: isize) {
        if self.flow == 0 {
            while self.indent > col {
                self.indent = self.indents.pop().unwrap_or(-1);
                self.emit(TokenKind::BlockEnd, self.mark);
            }
        }
    }
    fn separator(&self) -> bool {
        ((self.peek(0) == '-' && self.peek(1) == '-' && self.peek(2) == '-')
            || (self.peek(0) == '.' && self.peek(1) == '.' && self.peek(2) == '.'))
            && blank(self.peek(3))
    }
    fn scan(mut self) -> Result<Vec<Token>> {
        if self.peek(0) == '\u{feff}' {
            self.advance();
        }
        loop {
            loop {
                while self.peek(0) == ' ' {
                    self.advance();
                }
                if self.peek(0) == '#' {
                    while self.peek(0) != '\0' && !br(self.peek(0)) {
                        self.advance();
                    }
                }
                if !br(self.peek(0)) {
                    break;
                }
                self.line_break();
                if self.flow == 0 {
                    self.allow = true;
                }
            }
            let stale: Vec<_> = self
                .keys
                .iter()
                .filter(|(_, k)| k.mark.line != self.mark.line || self.pos - k.index > 1024)
                .map(|(&level, _)| level)
                .collect();
            for level in stale {
                if self.keys.remove(&level).is_some_and(|k| k.required) {
                    return Err(error("ScannerError"));
                }
            }
            self.unwind(self.mark.column as isize);
            let start = self.mark;
            let c = self.peek(0);
            if c == '\0' {
                self.unwind(-1);
                self.remove_key()?;
                self.emit(TokenKind::End, start);
                break;
            }
            if self.mark.column == 0 && (c == '%' || self.separator()) {
                self.unwind(-1);
                self.remove_key()?;
                self.allow = false;
                if c == '%' {
                    let mut value = String::new();
                    while self.peek(0) != '\0' && !br(self.peek(0)) {
                        value.push(self.peek(0));
                        self.advance();
                    }
                    self.emit(TokenKind::Directive(value), start);
                } else {
                    for _ in 0..3 {
                        self.advance();
                    }
                    self.emit(
                        if c == '-' {
                            TokenKind::Doc
                        } else {
                            TokenKind::DocEnd
                        },
                        start,
                    );
                }
                continue;
            }
            match c {
                '[' | '{' => {
                    self.save_key()?;
                    self.flow += 1;
                    self.allow = true;
                    self.advance();
                    self.emit(
                        if c == '[' {
                            TokenKind::OpenSeq
                        } else {
                            TokenKind::OpenMap
                        },
                        start,
                    );
                }
                ']' | '}' => {
                    self.remove_key()?;
                    self.flow = self.flow.saturating_sub(1);
                    self.allow = false;
                    self.advance();
                    self.emit(
                        if c == ']' {
                            TokenKind::CloseSeq
                        } else {
                            TokenKind::CloseMap
                        },
                        start,
                    );
                }
                ',' => {
                    self.remove_key()?;
                    self.allow = true;
                    self.advance();
                    self.emit(TokenKind::Comma, start);
                }
                '-' | '?' if blank(self.peek(1)) || (c == '?' && self.flow > 0) => {
                    if self.flow == 0 {
                        if !self.allow {
                            return Err(error("ScannerError"));
                        }
                        if self.add_indent(start.column) {
                            self.emit(
                                if c == '-' {
                                    TokenKind::Seq
                                } else {
                                    TokenKind::Map
                                },
                                start,
                            );
                        }
                    }
                    self.remove_key()?;
                    self.allow = c == '-' || self.flow == 0;
                    self.advance();
                    self.emit(
                        if c == '-' {
                            TokenKind::Dash
                        } else {
                            TokenKind::Key
                        },
                        start,
                    );
                }
                ':' if self.flow > 0 || blank(self.peek(1)) => {
                    if let Some(key) = self.keys.remove(&self.flow) {
                        let mut insert = vec![Token {
                            kind: TokenKind::Key,
                            start: key.mark,
                            end: key.mark,
                        }];
                        if self.flow == 0 && self.add_indent(key.mark.column) {
                            insert.insert(
                                0,
                                Token {
                                    kind: TokenKind::Map,
                                    start: key.mark,
                                    end: key.mark,
                                },
                            );
                        }
                        let n = insert.len();
                        for k in self.keys.values_mut() {
                            if k.token >= key.token {
                                k.token += n;
                            }
                        }
                        self.tokens.splice(key.token..key.token, insert);
                        self.allow = false;
                    } else {
                        if self.flow == 0 && !self.allow {
                            return Err(error("ScannerError"));
                        }
                        if self.flow == 0 && self.add_indent(start.column) {
                            self.emit(TokenKind::Map, start);
                        }
                        self.allow = self.flow == 0;
                        self.remove_key()?;
                    }
                    self.advance();
                    self.emit(TokenKind::Value, start);
                }
                '*' | '&' => {
                    self.save_key()?;
                    self.allow = false;
                    self.advance();
                    let mut value = String::new();
                    while self.peek(0).is_ascii_alphanumeric() || "-_".contains(self.peek(0)) {
                        value.push(self.peek(0));
                        self.advance();
                    }
                    if value.is_empty()
                        || !(blank(self.peek(0)) || "?:,]}%@`".contains(self.peek(0)))
                    {
                        return Err(error("ScannerError"));
                    }
                    self.emit(
                        if c == '*' {
                            TokenKind::Alias(value)
                        } else {
                            TokenKind::Anchor(value)
                        },
                        start,
                    );
                }
                '!' => {
                    self.save_key()?;
                    self.allow = false;
                    let (handle, suffix) = self.tag()?;
                    self.emit(TokenKind::Tag(handle, suffix), start);
                }
                '|' | '>' if self.flow == 0 => {
                    self.allow = true;
                    self.remove_key()?;
                    let value = self.block_scalar(c)?;
                    self.emit(TokenKind::Scalar(value, Some(c)), start);
                }
                '\'' | '"' => {
                    self.save_key()?;
                    self.allow = false;
                    let value = self.quoted(c)?;
                    self.emit(TokenKind::Scalar(value, Some(c)), start);
                }
                _ => {
                    if blank(c)
                        || "-?:,[]{}#&*!|>'\"%@`".contains(c)
                            && !("-?:".contains(c) && !blank(self.peek(1)))
                    {
                        return Err(error("ScannerError"));
                    }
                    self.save_key()?;
                    self.allow = false;
                    let (value, end) = self.plain();
                    self.tokens.push(Token {
                        kind: TokenKind::Scalar(value, None),
                        start,
                        end,
                    });
                }
            }
        }
        Ok(self.tokens)
    }
    fn plain(&mut self) -> (String, Mark) {
        let mut value = String::new();
        let mut spaces = String::new();
        let mut end = self.mark;
        let indent = self.indent + 1;
        loop {
            if self.peek(0) == '#' {
                break;
            }
            let begin = self.pos;
            loop {
                let c = self.peek(0);
                if blank(c)
                    || (c == ':'
                        && (blank(self.peek(1))
                            || (self.flow > 0 && ",[]{}".contains(self.peek(1)))))
                    || (self.flow > 0 && ",?[]{}".contains(c))
                {
                    break;
                }
                self.advance();
            }
            if self.pos == begin {
                break;
            }
            self.allow = false;
            value.push_str(&spaces);
            value.extend(&self.chars[begin..self.pos]);
            end = self.mark;
            spaces.clear();
            while self.peek(0) == ' ' {
                spaces.push(' ');
                self.advance();
            }
            if br(self.peek(0)) {
                let first = self.line_break();
                self.allow = true;
                if self.separator() {
                    break;
                }
                let mut breaks = String::new();
                loop {
                    while self.peek(0) == ' ' {
                        self.advance();
                    }
                    if br(self.peek(0)) {
                        breaks.push_str(&self.line_break());
                        if self.separator() {
                            return (value, end);
                        }
                    } else {
                        break;
                    }
                }
                spaces = if first != "\n" {
                    first + &breaks
                } else if breaks.is_empty() {
                    " ".into()
                } else {
                    breaks
                };
            }
            if spaces.is_empty()
                || self.peek(0) == '#'
                || (self.flow == 0 && (self.mark.column as isize) < indent)
            {
                break;
            }
        }
        (value, end)
    }
    fn quoted_breaks(&mut self) -> Result<String> {
        let mut s = String::new();
        loop {
            if self.separator() {
                return Err(error("ScannerError"));
            }
            while " \t".contains(self.peek(0)) {
                self.advance();
            }
            if !br(self.peek(0)) {
                break;
            }
            s.push_str(&self.line_break());
        }
        Ok(s)
    }
    fn quoted(&mut self, quote: char) -> Result<String> {
        self.advance();
        let mut value = String::new();
        loop {
            let c = self.peek(0);
            if c == '\0' {
                return Err(error("ScannerError"));
            }
            if c == quote {
                self.advance();
                if quote == '\'' && self.peek(0) == '\'' {
                    value.push('\'');
                    self.advance();
                } else {
                    return Ok(value);
                }
            } else if c == '\\' && quote == '"' {
                self.advance();
                let c = self.peek(0);
                if br(c) {
                    self.line_break();
                    value.push_str(&self.quoted_breaks()?);
                    continue;
                }
                let replacement = match c {
                    '0' => '\0',
                    'a' => '\x07',
                    'b' => '\x08',
                    't' | '\t' => '\t',
                    'n' => '\n',
                    'v' => '\x0b',
                    'f' => '\x0c',
                    'r' => '\r',
                    'e' => '\x1b',
                    ' ' => ' ',
                    '"' => '"',
                    '\\' => '\\',
                    '/' => '/',
                    'N' => '\u{85}',
                    '_' => '\u{a0}',
                    'L' => '\u{2028}',
                    'P' => '\u{2029}',
                    'x' | 'u' | 'U' => {
                        self.advance();
                        let n = if c == 'x' {
                            2
                        } else if c == 'u' {
                            4
                        } else {
                            8
                        };
                        let mut code = 0u32;
                        for _ in 0..n {
                            code = code
                                .checked_mul(16)
                                .and_then(|v| self.peek(0).to_digit(16).map(|d| v + d))
                                .ok_or_else(|| error("ScannerError"))?;
                            self.advance();
                        }
                        value.push(char::from_u32(code).ok_or_else(|| error("ScannerError"))?);
                        continue;
                    }
                    _ => return Err(error("ScannerError")),
                };
                value.push(replacement);
                self.advance();
            } else if c == ' ' || c == '\t' || br(c) {
                let mut spaces = String::new();
                while " \t".contains(self.peek(0)) {
                    spaces.push(self.peek(0));
                    self.advance();
                }
                if br(self.peek(0)) {
                    let first = self.line_break();
                    let rest = self.quoted_breaks()?;
                    if first != "\n" {
                        value.push_str(&first);
                    } else if rest.is_empty() {
                        value.push(' ');
                    }
                    value.push_str(&rest);
                } else {
                    value.push_str(&spaces);
                }
            } else {
                value.push(c);
                self.advance();
            }
        }
    }
    fn block_breaks(&mut self, indent: usize) -> String {
        let mut s = String::new();
        while self.mark.column < indent && self.peek(0) == ' ' {
            self.advance();
        }
        while br(self.peek(0)) {
            s.push_str(&self.line_break());
            while self.mark.column < indent && self.peek(0) == ' ' {
                self.advance();
            }
        }
        s
    }
    fn block_scalar(&mut self, style: char) -> Result<String> {
        self.advance();
        let mut chomp = ' ';
        let mut increment = None;
        for _ in 0..2 {
            let c = self.peek(0);
            if "+-".contains(c) && chomp == ' ' {
                chomp = c;
                self.advance();
            } else if c.is_ascii_digit() && increment.is_none() {
                if c == '0' {
                    return Err(error("ScannerError"));
                }
                increment = c.to_digit(10).map(|n| n as usize);
                self.advance();
            } else {
                break;
            }
        }
        if !blank(self.peek(0)) {
            return Err(error("ScannerError"));
        }
        while self.peek(0) == ' ' {
            self.advance();
        }
        if self.peek(0) == '#' {
            while self.peek(0) != '\0' && !br(self.peek(0)) {
                self.advance();
            }
        }
        if self.peek(0) != '\0' && !br(self.peek(0)) {
            return Err(error("ScannerError"));
        }
        self.line_break();
        let minimum = (self.indent + 1).max(1) as usize;
        let mut breaks = String::new();
        let indent = if let Some(n) = increment {
            let indent = minimum + n - 1;
            breaks = self.block_breaks(indent);
            indent
        } else {
            let mut max_indent = 0;
            while self.peek(0) == ' ' || br(self.peek(0)) {
                if self.peek(0) == ' ' {
                    self.advance();
                    max_indent = max_indent.max(self.mark.column);
                } else {
                    breaks.push_str(&self.line_break());
                }
            }
            minimum.max(max_indent)
        };
        let mut value = String::new();
        let mut last = String::new();
        while self.mark.column == indent && self.peek(0) != '\0' {
            value.push_str(&breaks);
            let leading = !" \t".contains(self.peek(0));
            while self.peek(0) != '\0' && !br(self.peek(0)) {
                value.push(self.peek(0));
                self.advance();
            }
            last = self.line_break();
            breaks = self.block_breaks(indent);
            if self.mark.column != indent || self.peek(0) == '\0' {
                break;
            }
            if style == '>' && last == "\n" && leading && !" \t".contains(self.peek(0)) {
                if breaks.is_empty() {
                    value.push(' ');
                }
            } else {
                value.push_str(&last);
            }
        }
        if chomp != '-' {
            value.push_str(&last);
        }
        if chomp == '+' {
            value.push_str(&breaks);
        }
        Ok(value)
    }
    fn tag(&mut self) -> Result<(String, String)> {
        self.advance();
        let mut raw = String::new();
        if self.peek(0) == '<' {
            self.advance();
            while self.peek(0) != '>' {
                if blank(self.peek(0)) {
                    return Err(error("ScannerError"));
                }
                raw.push(self.peek(0));
                self.advance();
            }
            self.advance();
            return Ok((String::new(), uri(&raw)?));
        }
        while !blank(self.peek(0)) {
            raw.push(self.peek(0));
            self.advance();
        }
        if raw.is_empty() {
            return Ok((String::new(), "!".into()));
        }
        if let Some(i) = raw.find('!') {
            Ok((format!("!{}!", &raw[..i]), uri(&raw[i + 1..])?))
        } else {
            Ok(("!".into(), uri(&raw)?))
        }
    }
}
fn uri(s: &str) -> Result<String> {
    let mut bytes = Vec::new();
    let mut chars = s.bytes();
    while let Some(c) = chars.next() {
        if c == b'%' {
            let hi = chars.next().and_then(|c| (c as char).to_digit(16));
            let lo = chars.next().and_then(|c| (c as char).to_digit(16));
            bytes.push(
                (hi.zip(lo)
                    .map(|(a, b)| a * 16 + b)
                    .ok_or_else(|| error("ScannerError"))?) as u8,
            );
        } else {
            bytes.push(c);
        }
    }
    String::from_utf8(bytes).map_err(|_| error("ScannerError"))
}

// First-character dispatch and order are PyYAML Resolver's YAML 1.1 table.
fn resolve(value: &str) -> Result<String> {
    type Rule = (&'static str, &'static str, &'static str);
    static RULES: OnceLock<std::result::Result<Vec<(Rule, regex::Regex)>, regex::Error>> =
        OnceLock::new();
    let rules = RULES
        .get_or_init(|| {
            [
                (
                    "bool",
                    "yYnNtTfFoO",
                    concat!(
                        "^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|",
                        "on|On|ON|off|Off|OFF)$"
                    ),
                ),
                (
                    "float",
                    "-+0123456789.",
                    concat!(
                        r"^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|",
                        r"\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|",
                        r"[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|",
                        r"[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
                    ),
                ),
                (
                    "int",
                    "-+0123456789",
                    concat!(
                        r"^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|",
                        r"[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$"
                    ),
                ),
                ("merge", "<", r"^(?:<<)$"),
                ("null", "~nN\0", r"^(?:~|null|Null|NULL|)$"),
                (
                    "timestamp",
                    "0123456789",
                    concat!(
                        r"^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}",
                        r"(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?",
                        r"(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?)$"
                    ),
                ),
                ("value", "=", r"^(?:=)$"),
            ]
            .into_iter()
            .map(|rule| regex::Regex::new(rule.2).map(|re| (rule, re)))
            .collect()
        })
        .as_ref()
        .map_err(|_| error("ResolverError"))?;
    let first = value.chars().next().unwrap_or('\0');
    let tag = rules
        .iter()
        .find(|((_, chars, _), re)| chars.contains(first) && re.is_match(value))
        .map_or("str", |((tag, _, _), _)| *tag);
    Ok(format!("{PREFIX}{tag}"))
}
struct Composer {
    chars: Vec<char>,
    tokens: Vec<Token>,
    pos: usize,
    arena: Vec<NodeData>,
    anchors: BTreeMap<String, (usize, Mark)>,
    tags: BTreeMap<String, String>,
}
impl Composer {
    fn failure(&self, context: Option<(&str, Mark)>, problem: &str) -> YamlError {
        marked(
            "ParserError",
            &self.chars,
            context,
            problem,
            self.token().start,
        )
    }
    fn token(&self) -> &Token {
        &self.tokens[self.pos.min(self.tokens.len() - 1)]
    }
    fn at(&self, kind: &TokenKind) -> bool {
        &self.token().kind == kind
    }
    fn take(&mut self) -> Token {
        let t = self.token().clone();
        self.pos += 1;
        t
    }
    fn eat(&mut self, kind: &TokenKind) -> bool {
        if self.at(kind) {
            self.take();
            true
        } else {
            false
        }
    }
    fn alloc(&mut self, kind: Kind, tag: String, style: Option<char>, mark: Mark) -> usize {
        let id = self.arena.len();
        self.arena.push(NodeData {
            kind,
            tag,
            style,
            end_line: mark.line,
            line: mark.line,
            column: mark.column,
        });
        id
    }
    fn empty(&mut self, mark: Mark) -> Result<usize> {
        Ok(self.alloc(Kind::Scalar(String::new()), resolve("")?, None, mark))
    }
    fn absent(&self, flow: bool) -> bool {
        matches!(
            self.token().kind,
            TokenKind::Key
                | TokenKind::Value
                | TokenKind::BlockEnd
                | TokenKind::End
                | TokenKind::Doc
                | TokenKind::DocEnd
        ) || (flow
            && matches!(
                self.token().kind,
                TokenKind::Comma | TokenKind::CloseMap | TokenKind::CloseSeq
            ))
    }
    fn node(&mut self, depth: usize, indentless: bool, block: bool) -> Result<usize> {
        if depth > DEPTH_LIMIT {
            return Err(error("RecursionError"));
        }
        let start = self.token().start;
        if let TokenKind::Alias(name) = self.token().kind.clone() {
            self.take();
            return self.anchors.get(&name).map(|(id, _)| *id).ok_or_else(|| {
                marked(
                    "ComposerError",
                    &self.chars,
                    None,
                    &format!("found undefined alias '{name}'"),
                    start,
                )
            });
        }
        let mut anchor = None;
        let mut tag = None;
        loop {
            match self.token().kind.clone() {
                TokenKind::Anchor(name) if anchor.is_none() => {
                    self.take();
                    anchor = Some(name);
                }
                TokenKind::Tag(handle, suffix) if tag.is_none() => {
                    let tag_mark = self.take().start;
                    tag = Some(if handle.is_empty() {
                        suffix
                    } else {
                        format!(
                            "{}{}",
                            self.tags.get(&handle).ok_or_else(|| marked(
                                "ParserError",
                                &self.chars,
                                Some(("while parsing a node", start)),
                                &format!("found undefined tag handle '{handle}'"),
                                tag_mark
                            ))?,
                            suffix
                        )
                    });
                }
                _ => break,
            }
        }
        if let Some(name) = &anchor
            && let Some((_, first)) = self.anchors.get(name)
        {
            return Err(marked(
                "ComposerError",
                &self.chars,
                Some((
                    &format!("found duplicate anchor '{name}'; first occurrence"),
                    *first,
                )),
                "second occurrence",
                start,
            ));
        }
        let token = self.token().clone();
        let (kind, style, default_tag) = match &token.kind {
            TokenKind::Scalar(s, style) => {
                self.take();
                let tag = if style.is_none() {
                    resolve(s)?
                } else {
                    format!("{PREFIX}str")
                };
                (Kind::Scalar(s.clone()), *style, tag)
            }
            TokenKind::OpenSeq | TokenKind::Seq => {
                (Kind::Sequence(vec![]), None, format!("{PREFIX}seq"))
            }
            TokenKind::Dash if indentless => (Kind::Sequence(vec![]), None, format!("{PREFIX}seq")),
            TokenKind::OpenMap | TokenKind::Map => {
                (Kind::Mapping(vec![]), None, format!("{PREFIX}map"))
            }
            _ if anchor.is_some() || tag.is_some() => {
                (Kind::Scalar(String::new()), None, resolve("")?)
            }
            _ => {
                return Err(self.failure(
                    Some((
                        if block {
                            "while parsing a block node"
                        } else {
                            "while parsing a flow node"
                        },
                        start,
                    )),
                    &format!(
                        "expected the node content, but found '{}'",
                        token.kind.name()
                    ),
                ));
            }
        };
        let tag = match tag {
            Some(s) if s != "!" => s,
            Some(_) => match kind {
                Kind::Scalar(ref text) => resolve(text)?,
                _ => default_tag,
            },
            None => default_tag,
        };
        let id = self.alloc(kind, tag, style, start);
        if let Some(name) = anchor {
            self.anchors.insert(name, (id, start));
        }
        match token.kind {
            TokenKind::OpenSeq => {
                self.take();
                let mut items = Vec::new();
                while !self.at(&TokenKind::CloseSeq) {
                    if !items.is_empty() && !self.eat(&TokenKind::Comma) {
                        return Err(self.failure(
                            Some(("while parsing a flow sequence", token.start)),
                            &format!(
                                "expected ',' or ']', but got '{}'",
                                self.token().kind.name()
                            ),
                        ));
                    }
                    if self.at(&TokenKind::CloseSeq) {
                        break;
                    }
                    if self.at(&TokenKind::Key) {
                        let mark = self.take().start;
                        let map =
                            self.alloc(Kind::Mapping(vec![]), format!("{PREFIX}map"), None, mark);
                        let pair = self.pair(depth + 1, true, mark)?;
                        self.arena[map].kind = Kind::Mapping(vec![pair]);
                        items.push(map);
                    } else {
                        items.push(self.node(depth + 1, false, false)?);
                    }
                }
                self.take();
                self.arena[id].kind = Kind::Sequence(items);
            }
            TokenKind::OpenMap => {
                self.take();
                let mut pairs = Vec::new();
                while !self.at(&TokenKind::CloseMap) {
                    if !pairs.is_empty() && !self.eat(&TokenKind::Comma) {
                        return Err(self.failure(
                            Some(("while parsing a flow mapping", token.start)),
                            &format!(
                                "expected ',' or '}}', but got '{}'",
                                self.token().kind.name()
                            ),
                        ));
                    }
                    if self.at(&TokenKind::CloseMap) {
                        break;
                    }
                    if self.at(&TokenKind::Key) {
                        let mark = self.take().end;
                        pairs.push(self.pair(depth + 1, true, mark)?);
                    } else {
                        let key = self.node(depth + 1, false, false)?;
                        let value = self.empty(self.token().start)?;
                        pairs.push((key, value));
                    }
                }
                self.take();
                self.arena[id].kind = Kind::Mapping(pairs);
            }
            TokenKind::Seq | TokenKind::Dash => {
                let indentless = token.kind == TokenKind::Dash;
                if !indentless {
                    self.take();
                }
                let mut items = Vec::new();
                while self.at(&TokenKind::Dash) {
                    let mark = self.take().end;
                    items.push(if self.absent(false) || self.at(&TokenKind::Dash) {
                        self.empty(mark)?
                    } else {
                        self.node(depth + 1, false, true)?
                    });
                }
                if !indentless && !self.eat(&TokenKind::BlockEnd) {
                    return Err(self.failure(
                        Some(("while parsing a block collection", token.start)),
                        &format!(
                            "expected <block end>, but found '{}'",
                            self.token().kind.name()
                        ),
                    ));
                }
                self.arena[id].kind = Kind::Sequence(items);
            }
            TokenKind::Map => {
                self.take();
                let mut pairs = Vec::new();
                while self.at(&TokenKind::Key) {
                    let mark = self.take().end;
                    pairs.push(self.pair(depth + 1, false, mark)?);
                }
                if !self.eat(&TokenKind::BlockEnd) {
                    return Err(self.failure(
                        Some(("while parsing a block mapping", token.start)),
                        &format!(
                            "expected <block end>, but found '{}'",
                            self.token().kind.name()
                        ),
                    ));
                }
                self.arena[id].kind = Kind::Mapping(pairs);
            }
            _ => {}
        }
        self.arena[id].end_line = self.tokens[self.pos - 1].end.line;
        Ok(id)
    }
    fn pair(&mut self, depth: usize, flow: bool, mark: Mark) -> Result<(usize, usize)> {
        let key = if self.absent(flow) {
            self.empty(mark)?
        } else {
            self.node(depth, !flow, !flow)?
        };
        let value = if self.at(&TokenKind::Value) {
            let mark = self.take().end;
            if self.absent(flow) {
                self.empty(mark)?
            } else {
                self.node(depth, !flow, !flow)?
            }
        } else {
            self.empty(self.token().start)?
        };
        Ok((key, value))
    }
}
// Composition recurses once per nesting level: about 1 KiB of stack per level in release
// builds and several KiB in debug builds. A dedicated reserved stack keeps the accepted
// 450 levels independent of the caller's stack (a Windows main thread has 1 MiB).
const COMPOSE_STACK: usize = 16 << 20;
pub fn compose(input: Input<'_>) -> Result<Option<Node>> {
    std::thread::scope(|scope| {
        match std::thread::Builder::new()
            .stack_size(COMPOSE_STACK)
            .spawn_scoped(scope, || compose_on_stack(input))
        {
            Ok(handle) => handle
                .join()
                .unwrap_or_else(|panic| std::panic::resume_unwind(panic)),
            // Without a new thread, compose on the caller's stack.
            Err(_) => compose_on_stack(input),
        }
    })
}
fn compose_on_stack(input: Input<'_>) -> Result<Option<Node>> {
    let chars = reader(input)?;
    let tokens = Scanner {
        chars: chars.clone(),
        pos: 0,
        mark: Mark::default(),
        flow: 0,
        indent: -1,
        indents: vec![],
        allow: true,
        keys: BTreeMap::new(),
        tokens: vec![],
    }
    .scan()?;
    let mut c = Composer {
        chars,
        tokens,
        pos: 0,
        arena: vec![],
        anchors: BTreeMap::new(),
        tags: BTreeMap::from([("!".into(), "!".into()), ("!!".into(), PREFIX.into())]),
    };
    if c.at(&TokenKind::End) {
        return Ok(None);
    }
    let mut directives = false;
    let mut version = false;
    let mut handles = BTreeMap::new();
    while let TokenKind::Directive(text) = c.token().kind.clone() {
        let directive = c.take().start;
        directives = true;
        let parts: Vec<_> = text
            .split('#')
            .next()
            .unwrap_or("")
            .split_whitespace()
            .collect();
        match parts.first().copied() {
            Some("%YAML") => {
                if version {
                    return Err(marked(
                        "ParserError",
                        &c.chars,
                        None,
                        "found duplicate YAML directive",
                        directive,
                    ));
                }
                let v = parts.get(1).ok_or_else(|| error("ScannerError"))?;
                let (major, minor) = v.split_once('.').ok_or_else(|| error("ScannerError"))?;
                if minor.parse::<u32>().is_err() {
                    return Err(error("ScannerError"));
                }
                if major != "1" {
                    return Err(marked(
                        "ParserError",
                        &c.chars,
                        None,
                        "found incompatible YAML document (version 1.* is required)",
                        directive,
                    ));
                }
                version = true;
            }
            Some("%TAG") => {
                if parts.len() != 3 {
                    return Err(error("ScannerError"));
                }
                if handles.insert(parts[1].to_string(), ()).is_some() {
                    return Err(marked(
                        "ParserError",
                        &c.chars,
                        None,
                        &format!("duplicate tag handle '{}'", parts[1]),
                        directive,
                    ));
                }
                c.tags.insert(parts[1].into(), uri(parts[2])?);
            }
            _ => {}
        }
    }
    let explicit = c.eat(&TokenKind::Doc);
    if directives && !explicit {
        return Err(c.failure(
            None,
            &format!(
                "expected '<document start>', but found '{}'",
                c.token().kind.name()
            ),
        ));
    }
    let root_start = c.token().start;
    let root = if explicit && c.absent(false) {
        c.empty(c.token().start)?
    } else {
        c.node(0, false, true)?
    };
    c.eat(&TokenKind::DocEnd);
    if !c.at(&TokenKind::End) {
        return Err(if c.at(&TokenKind::Doc) {
            marked(
                "ComposerError",
                &c.chars,
                Some(("expected a single document in the stream", root_start)),
                "but found another document",
                c.token().start,
            )
        } else {
            c.failure(
                None,
                &format!(
                    "expected '<document start>', but found '{}'",
                    c.token().kind.name()
                ),
            )
        });
    }
    Ok(Some(Node {
        arena: c.arena,
        root,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn resolver_dispatch_and_depth() {
        assert_eq!(resolve("yes").unwrap(), format!("{PREFIX}bool"));
        assert_eq!(resolve("1e3").unwrap(), format!("{PREFIX}str"));
        let input = format!("{}0{}", "[".repeat(2000), "]".repeat(2000));
        assert_eq!(
            compose(Input::Text(&input)).unwrap_err().class,
            "RecursionError"
        );
    }
    #[test]
    fn self_alias_is_an_arena_reference() {
        let n = compose(Input::Text("&loop [*loop]")).unwrap().unwrap();
        assert!(matches!(&n.arena[n.root].kind, Kind::Sequence(v) if v == &[n.root]));
    }
}
