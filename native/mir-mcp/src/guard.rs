//! Read-only target access. Unix paths are opened relative to a pinned root,
//! refusing symlinks at every step. Unsupported platforms fail closed.
use serde_json::{Map, Value, json};
use std::collections::HashSet;
#[cfg(unix)]
use std::fs::Metadata;
use std::fs::{self, File};
use std::io::Read;
#[cfg(unix)]
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant};

type Result<T> = std::result::Result<T, &'static str>;
const FILE_LIMIT: usize = 1_048_576;
const READ_LIMIT: usize = 4_194_304;
const FILE_COUNT: usize = 256;
const PROTECTED: &[&str] = &[
    ".env*",
    "*.db*",
    "*.sqlite*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    "credentials*",
    "token.json",
    "tokens.json",
    "id_rsa*",
    "id_ed25519*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
];

pub fn relative_path(value: &str, pattern: bool) -> Result<String> {
    if value.is_empty()
        || value.len() > 4096
        || value.chars().any(|c| c < ' ' || c == '\u{7f}')
        || value.contains('\\')
        || value.starts_with('-')
        || value.starts_with('/')
        || (value.as_bytes().get(1) == Some(&b':') && value.as_bytes()[0].is_ascii_alphabetic())
        || value.split('/').any(|p| p == "..")
    {
        return Err("E_PATH");
    }
    let normalized = value
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect::<Vec<_>>()
        .join("/");
    if normalized.is_empty() {
        return Err("E_PATH");
    }
    #[cfg(windows)]
    windows_components(normalized.split('/'), pattern)?;
    #[cfg(not(windows))]
    let _ = pattern;
    Ok(normalized)
}

#[derive(Clone, PartialEq, Eq)]
struct Stamp {
    device: u64,
    inode: u64,
    size: u64,
    modified: i128,
    changed: i128,
}
impl Stamp {
    #[cfg(unix)]
    fn new(info: &Metadata) -> Self {
        Self {
            device: info.dev(),
            inode: info.ino(),
            size: info.len(),
            modified: i128::from(info.mtime()) * 1_000_000_000 + i128::from(info.mtime_nsec()),
            changed: i128::from(info.ctime()) * 1_000_000_000 + i128::from(info.ctime_nsec()),
        }
    }
    fn identity(&self) -> (u64, u64) {
        (self.device, self.inode)
    }
    fn value(&self) -> Value {
        // JSON numbers preserve nanosecond timestamps without floating-point loss.
        json!([
            self.device,
            self.inode,
            self.size,
            self.modified,
            self.changed
        ])
    }
}

struct PinnedFile {
    file: File,
    _ancestors: Vec<File>,
}
impl std::ops::Deref for PinnedFile {
    type Target = File;
    fn deref(&self) -> &File {
        &self.file
    }
}
impl std::ops::DerefMut for PinnedFile {
    fn deref_mut(&mut self) -> &mut File {
        &mut self.file
    }
}

pub struct Guard {
    pub root: PathBuf,
    pub sources: Map<String, Value>,
    pub source_digests: Map<String, Value>,
    pub deadline: Instant,
    pub profile_protections: &'static str,
    // Unix walks from this descriptor; Windows only holds it to keep the root open.
    #[cfg_attr(windows, allow(dead_code))]
    directory: File,
    identity: (u64, u64),
    profile_stamp: Option<Stamp>,
    profile_pinned: bool,
    patterns: Vec<String>,
    accessed: HashSet<String>,
    files: usize,
    total: usize,
}

impl Guard {
    pub fn new(raw: &str) -> Result<Self> {
        #[cfg(not(any(unix, windows)))]
        {
            let _ = raw;
            Err("E_PATH")
        }
        #[cfg(any(unix, windows))]
        {
            let deadline = Instant::now() + Duration::from_secs(10);
            if raw.len() > 4096
                || !Path::new(raw).is_absolute()
                || Path::new(raw)
                    .components()
                    .any(|c| c == Component::ParentDir)
            {
                return Err("E_PATH");
            }
            #[cfg(windows)]
            windows_root(raw)?;
            protected(&posix_text(raw), &[], deadline)?;
            // Python's path resolver reports an embedded NUL as ValueError,
            // which the tool boundary maps to E_FORMAT after protection checks.
            #[cfg(unix)]
            if raw.contains('\0') {
                return Err("E_FORMAT");
            }
            let root = normalized_root(fs::canonicalize(raw).map_err(|_| "E_IO")?)?;
            let root_text = root.to_str().ok_or("E_PATH")?;
            if cloud_reason(&root)?.is_some() {
                return Err("E_CLOUD_SYNC");
            }
            protected(&posix_text(root_text), &[], deadline)?;
            let before = platform::path_stamp(&root)?;
            if !fs::metadata(&root).map_err(|_| "E_IO")?.is_dir() {
                return Err("E_IO");
            }
            let directory = platform::open_root(&root)?;
            let identity = platform::stamp(&directory)?.identity();
            if before.identity() != identity {
                return Err("E_PATH");
            }
            let mut guard = Self {
                root,
                directory,
                identity,
                deadline,
                sources: Map::new(),
                source_digests: Map::new(),
                profile_protections: "available",
                profile_stamp: None,
                profile_pinned: false,
                patterns: Vec::new(),
                accessed: HashSet::new(),
                files: 0,
                total: 0,
            };
            guard.profile_stamp = guard.current_profile_stamp()?;
            if guard.exists(".mir/repo-profile.toml")? {
                let raw = guard.read(".mir/repo-profile.toml")?;
                let text = std::str::from_utf8(&raw).map_err(|_| "E_FORMAT")?;
                let profile: toml::Value = toml::from_str(text).map_err(|_| "E_FORMAT")?;
                bounded_toml(&profile, 0)?;
                let table = profile.as_table().ok_or("E_FORMAT")?;
                guard.add_patterns(table, &["protected_paths", "secret_paths"])?;
                for (name, keys) in [
                    ("paths", &["protected_paths", "secret_paths"][..]),
                    ("boundaries", &["secrets"][..]),
                    ("safety", &["protected_paths", "secret_paths"][..]),
                ] {
                    if let Some(section) = table.get(name) {
                        guard.add_patterns(section.as_table().ok_or("E_FORMAT")?, keys)?;
                    }
                }
            }
            if guard.current_profile_stamp()? != guard.profile_stamp {
                return Err("E_PATH");
            }
            guard.profile_pinned = true;
            Ok(guard)
        }
    }

    fn add_patterns(
        &mut self,
        table: &toml::map::Map<String, toml::Value>,
        keys: &[&str],
    ) -> Result<()> {
        for key in keys {
            if let Some(value) = table.get(*key) {
                let patterns = value.as_array().ok_or("E_FORMAT")?;
                if patterns.len() > FILE_COUNT {
                    return Err("E_FORMAT");
                }
                for pattern in patterns {
                    self.patterns.push(
                        relative_path(pattern.as_str().ok_or("E_FORMAT")?, true)
                            .map_err(|_| "E_FORMAT")?
                            .to_lowercase(),
                    );
                }
            }
        }
        Ok(())
    }

    pub fn tick(&self) -> Result<()> {
        if Instant::now() >= self.deadline {
            return Err("E_TIMEOUT");
        }
        let current = platform::path_stamp(&self.root).map_err(|_| "E_PATH")?;
        if current.identity() != self.identity {
            return Err("E_PATH");
        }
        if self.profile_pinned && self.current_profile_stamp()? != self.profile_stamp {
            return Err("E_PATH");
        }
        Ok(())
    }

    #[cfg(unix)]
    fn walk(&self, relative: &str) -> Result<Option<PinnedFile>> {
        let mut directory = self.directory.try_clone().map_err(|_| "E_PATH")?;
        let parts: Vec<_> = relative.split('/').collect();
        for (index, part) in parts.iter().enumerate() {
            directory = match platform::open_child(&directory, part, index + 1 < parts.len())? {
                Some(file) => file,
                None => return Ok(None),
            };
        }
        let info = directory.metadata().map_err(|_| "E_PATH")?;
        if !info.is_file() && !info.is_dir() {
            return Err("E_PATH");
        }
        Ok(Some(PinnedFile {
            file: directory,
            _ancestors: Vec::new(),
        }))
    }
    #[cfg(not(any(unix, windows)))]
    fn walk(&self, _relative: &str) -> Result<Option<PinnedFile>> {
        Err("E_PATH")
    }

    #[cfg(windows)]
    fn walk(&self, relative: &str) -> Result<Option<PinnedFile>> {
        self.walk_windows(relative, true)
    }
    #[cfg(windows)]
    fn walk_windows(&self, relative: &str, check_protected: bool) -> Result<Option<PinnedFile>> {
        let mut ancestors = vec![platform::open_root(&self.root)?];
        let mut path = self.root.clone();
        let parts: Vec<_> = relative.split('/').collect();
        for (index, part) in parts.iter().enumerate() {
            path.push(part);
            let file = match platform::open_path(&path, index + 1 < parts.len()) {
                Ok(file) => file,
                Err("E_IO_MISSING") => return Ok(None),
                Err(code) => return Err(code),
            };
            let final_path = platform::final_path(&file)?;
            if check_protected {
                protected(
                    &final_path.to_str().ok_or("E_PATH")?.replace('\\', "/"),
                    &self.patterns,
                    self.deadline,
                )?;
                let suffix = final_path.strip_prefix(&self.root).map_err(|_| "E_PATH")?;
                protected(
                    &suffix.to_str().ok_or("E_PATH")?.replace('\\', "/"),
                    &self.patterns,
                    self.deadline,
                )?;
            }
            platform::validate_final_path(&final_path, &path)?;
            if index + 1 == parts.len() {
                return Ok(Some(PinnedFile {
                    file,
                    _ancestors: ancestors,
                }));
            }
            ancestors.push(file);
        }
        Err("E_PATH")
    }

    fn current_profile_stamp(&self) -> Result<Option<Stamp>> {
        #[cfg(windows)]
        let handle = self.walk_windows(".mir/repo-profile.toml", false)?;
        #[cfg(not(windows))]
        let handle = self.walk(".mir/repo-profile.toml")?;
        handle
            .map(|file| {
                let info = file.metadata().map_err(|_| "E_PATH")?;
                if !info.is_file() {
                    return Err("E_PATH");
                }
                platform::stamp(&file.file)
            })
            .transpose()
    }

    fn open(&mut self, relative: &str, allow_missing: bool) -> Result<Option<PinnedFile>> {
        self.tick()?;
        protected(relative, &self.patterns, self.deadline)?;
        let resolved = resolve_missing(&self.root.join(relative))?;
        let resolved_relative = resolved
            .strip_prefix(&self.root)
            .map_err(|_| "E_PATH")?
            .to_str()
            .ok_or("E_PATH")?;
        protected(
            &posix_text(resolved_relative),
            &self.patterns,
            self.deadline,
        )?;
        let Some(file) = self.walk(relative)? else {
            self.sources
                .insert(relative.to_owned(), Value::String("missing".into()));
            return if allow_missing { Ok(None) } else { Err("E_IO") };
        };
        let info = file.metadata().map_err(|_| "E_PATH")?;
        if info.is_file() {
            self.accessed.insert(relative.to_owned());
            if self.accessed.len() > FILE_COUNT {
                return Err("E_LIMIT");
            }
        }
        self.sources
            .insert(relative.to_owned(), platform::stamp(&file.file)?.value());
        Ok(Some(file))
    }

    pub fn exists(&mut self, raw: &str) -> Result<bool> {
        let relative = relative_path(raw, false)?;
        Ok(self.open(&relative, true)?.is_some())
    }
    pub fn path(&mut self, raw: &str, allow_missing: bool) -> Result<PathBuf> {
        let relative = relative_path(raw, false)?;
        self.open(&relative, allow_missing)?;
        Ok(self.root.join(relative))
    }
    pub fn read(&mut self, raw: &str) -> Result<Vec<u8>> {
        let relative = relative_path(raw, false)?;
        let mut file = self.open(&relative, false)?.ok_or("E_IO")?;
        let info = file.metadata().map_err(|_| "E_PATH")?;
        if !info.is_file() {
            return Err("E_PATH");
        }
        let before = platform::stamp(&file.file)?;
        self.files += 1;
        if self.files > FILE_COUNT || before.size > FILE_LIMIT as u64 {
            return Err("E_LIMIT");
        }
        let mut payload = Vec::new();
        loop {
            self.tick()?;
            let length = 65_536
                .min(FILE_LIMIT + 1 - payload.len())
                .min(READ_LIMIT + 1 - self.total);
            let mut chunk = vec![0; length];
            let count = file.read(&mut chunk).map_err(|_| "E_IO")?;
            self.total += count;
            if payload.len() + count > FILE_LIMIT || self.total > READ_LIMIT {
                return Err("E_LIMIT");
            }
            if count == 0 {
                break;
            }
            payload.extend_from_slice(&chunk[..count]);
        }
        let after = platform::stamp(&file.file)?;
        if before.identity() != after.identity()
            || before.size != after.size
            || before.modified != after.modified
        {
            return Err("E_PATH");
        }
        let check = self.open(&relative, false)?.ok_or("E_IO")?;
        if platform::stamp(&check.file)?.identity() != after.identity() {
            return Err("E_PATH");
        }
        let hash = crate::digest::sha256(&payload);
        self.sources
            .insert(relative.clone(), Value::String(hash.clone()));
        self.source_digests.insert(relative, Value::String(hash));
        Ok(payload)
    }
}

fn resolve_missing(path: &Path) -> Result<PathBuf> {
    let mut ancestor = path;
    let mut missing = Vec::new();
    loop {
        match fs::canonicalize(ancestor) {
            Ok(resolved) => {
                let mut resolved = normalized_root(resolved)?;
                for part in missing.iter().rev() {
                    resolved.push(part);
                }
                return Ok(resolved);
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                missing.push(ancestor.file_name().ok_or("E_PATH")?.to_owned());
                ancestor = ancestor.parent().ok_or("E_PATH")?;
            }
            Err(_) => return Err("E_PATH"),
        }
    }
}

fn normalized_root(path: PathBuf) -> Result<PathBuf> {
    #[cfg(windows)]
    {
        let text = path.to_str().ok_or("E_PATH")?;
        let text = text.strip_prefix("\\\\?\\").unwrap_or(text);
        windows_root(text)?;
        Ok(PathBuf::from(text))
    }
    #[cfg(not(windows))]
    {
        Ok(path)
    }
}

fn posix_text(text: &str) -> String {
    #[cfg(windows)]
    {
        text.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        text.to_owned()
    }
}

pub fn cloud_reason(root: &Path) -> Result<Option<&'static str>> {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        for component in root.ancestors() {
            let info = fs::symlink_metadata(component).map_err(|_| "E_IO")?;
            if info.file_attributes() & (0x80000 | 0x100000 | 0x40000 | 0x400000 | 0x1000) != 0 {
                return Ok(Some("Windows cloud files"));
            }
        }
    }
    let text = root.to_str().ok_or("E_PATH")?;
    let parts: Vec<_> = text.split('/').map(str::to_lowercase).collect();
    if parts.len() >= 5 && parts[0].is_empty() && parts[1] == "users" && parts[3] == "library" {
        return Ok(match parts[4].as_str() {
            "cloudstorage" => Some("macOS CloudStorage"),
            "mobile documents" => Some("iCloud Drive"),
            _ => None,
        });
    }
    Ok(None)
}

#[cfg(any(windows, test))]
fn windows_root(text: &str) -> Result<()> {
    let raw = text.as_bytes();
    if raw.len() < 3
        || !raw[0].is_ascii_alphabetic()
        || raw[1] != b':'
        || !matches!(raw[2], b'/' | b'\\')
        || text.chars().any(|c| c < ' ' || c == '\u{7f}')
    {
        return Err("E_PATH");
    }
    let parts: Vec<_> = text[3..]
        .split(['/', '\\'])
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    if parts.contains(&"..") {
        return Err("E_PATH");
    }
    windows_components(parts.into_iter(), false)
}

#[cfg(any(windows, test))]
fn windows_components<'a>(parts: impl Iterator<Item = &'a str>, pattern: bool) -> Result<()> {
    for part in parts {
        let device = part.split('.').next().unwrap_or("").to_uppercase();
        let numbered = device
            .strip_prefix("COM")
            .or_else(|| device.strip_prefix("LPT"));
        if part.chars().any(|c| {
            if pattern {
                ":\"<>|".contains(c)
            } else {
                ":*?\"<>|".contains(c)
            }
        }) || part.ends_with(['.', ' '])
            || matches!(
                device.as_str(),
                "CON" | "PRN" | "AUX" | "NUL" | "CONIN$" | "CONOUT$"
            )
            || numbered.is_some_and(|suffix| {
                suffix.chars().count() == 1 && "0123456789¹²³".contains(suffix)
            })
        {
            return Err("E_PATH");
        }
    }
    Ok(())
}

#[cfg(test)]
mod windows_syntax_tests {
    use super::{windows_components, windows_root};
    #[test]
    fn device_stream_namespace_and_normalization_rules() {
        for part in [
            "NUL.txt",
            "CON",
            "COM0",
            "LPT³.log",
            "a:b",
            "name.",
            "name ",
            "a?b",
            "a*b",
        ] {
            assert_eq!(
                windows_components([part].into_iter(), false),
                Err("E_PATH"),
                "{part}"
            );
        }
        for root in [
            r"\\server\share",
            r"\\?\C:\root",
            r"C:relative",
            r"C:\root\..\other",
            "C:/NUL",
        ] {
            assert_eq!(windows_root(root), Err("E_PATH"), "{root}");
        }
        assert_eq!(windows_root(r"C:\Local Folder\repo"), Ok(()));
        assert_eq!(
            windows_components(["private/*.txt"].into_iter(), true),
            Ok(())
        );
    }
}

fn bounded_toml(value: &toml::Value, depth: usize) -> Result<()> {
    if depth > 32 {
        return Err("E_LIMIT");
    }
    match value {
        toml::Value::String(value) if value.len() > 4096 => return Err("E_LIMIT"),
        toml::Value::Array(values) => {
            for item in values {
                bounded_toml(item, depth + 1)?;
            }
        }
        toml::Value::Table(values) => {
            for (key, item) in values {
                if key.len() > 4096 || depth + 1 > 32 {
                    return Err("E_LIMIT");
                }
                bounded_toml(item, depth + 1)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn protected(value: &str, patterns: &[String], deadline: Instant) -> Result<()> {
    let folded = value.to_lowercase();
    for part in folded.split('/').filter(|p| !p.is_empty() && *p != ".") {
        if matches!(part, "secrets" | ".ssh" | ".aws" | ".gnupg") {
            return Err("E_PROTECTED");
        }
        for pattern in PROTECTED {
            if glob(part, pattern, deadline)? {
                return Err("E_PROTECTED");
            }
        }
    }
    for pattern in patterns {
        let prefix = pattern
            .strip_suffix("/**")
            .unwrap_or_else(|| pattern.trim_end_matches('/'));
        if glob(&folded, pattern, deadline)?
            || folded == prefix
            || folded.starts_with(&format!("{prefix}/"))
        {
            return Err("E_PROTECTED");
        }
    }
    Ok(())
}

// fnmatchcase semantics: '*' spans '/', '?' matches one Unicode scalar, and
// bracket sets accept '!' negation, literal initial ']', and inclusive ranges.
fn glob(text: &str, pattern: &str, deadline: Instant) -> Result<bool> {
    let text: Vec<char> = text.chars().collect();
    let pattern: Vec<char> = pattern.chars().collect();
    let mut matches = vec![false; text.len() + 1];
    matches[0] = true;
    let mut index = 0;
    while index < pattern.len() {
        if Instant::now() >= deadline {
            return Err("E_TIMEOUT");
        }
        let token = pattern[index];
        if token == '*' {
            for pos in 1..matches.len() {
                matches[pos] |= matches[pos - 1];
            }
            index += 1;
            continue;
        }
        let mut end = index + 1;
        if token == '[' {
            if pattern.get(end) == Some(&'!') {
                end += 1;
            }
            if pattern.get(end) == Some(&']') {
                end += 1;
            }
            while end < pattern.len() && pattern[end] != ']' {
                end += 1;
            }
        }
        let set = token == '[' && end < pattern.len();
        for pos in (1..matches.len()).rev() {
            let accepted = if set {
                bracket(text[pos - 1], &pattern[index + 1..end])
            } else {
                token == '?' || token == text[pos - 1]
            };
            matches[pos] = matches[pos - 1] && accepted;
        }
        matches[0] = false;
        index = if set { end + 1 } else { index + 1 };
    }
    Ok(matches[text.len()])
}

fn bracket(value: char, set: &[char]) -> bool {
    let negate = set.first() == Some(&'!');
    let mut index = usize::from(negate);
    let mut found = false;
    while index < set.len() {
        if index + 2 < set.len() && set[index + 1] == '-' {
            found |= set[index] <= value && value <= set[index + 2];
            index += 3;
        } else {
            found |= value == set[index];
            index += 1;
        }
    }
    found != negate
}

// std exposes descriptor ownership and root flags safely, but no openat API.
// This boundary does only descriptor-relative open and immediately transfers
// successful descriptor ownership to File. No target pointer is dereferenced.
#[cfg(all(unix, any(target_os = "macos", target_os = "linux")))]
#[allow(unsafe_code)]
mod platform {
    use super::{File, Path, Result, Stamp};
    use std::ffi::{CString, c_char, c_int};
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::unix::fs::OpenOptionsExt;
    #[cfg(target_os = "macos")]
    const NOFOLLOW: c_int = 0x100;
    #[cfg(target_os = "macos")]
    const DIRECTORY: c_int = 0x100000;
    #[cfg(target_os = "macos")]
    const NONBLOCK: c_int = 4;
    #[cfg(target_os = "macos")]
    const CLOEXEC: c_int = 0x1000000;
    #[cfg(target_os = "linux")]
    const NOFOLLOW: c_int = 0x20000;
    #[cfg(target_os = "linux")]
    const DIRECTORY: c_int = 0x10000;
    #[cfg(target_os = "linux")]
    const NONBLOCK: c_int = 0x800;
    #[cfg(target_os = "linux")]
    const CLOEXEC: c_int = 0x80000;
    unsafe extern "C" {
        fn openat(directory: c_int, path: *const c_char, flags: c_int, ...) -> c_int;
    }
    pub fn stamp(file: &File) -> Result<Stamp> {
        Ok(Stamp::new(&file.metadata().map_err(|_| "E_PATH")?))
    }
    pub fn path_stamp(path: &Path) -> Result<Stamp> {
        Ok(Stamp::new(&std::fs::metadata(path).map_err(|_| "E_PATH")?))
    }
    pub fn open_root(path: &Path) -> Result<File> {
        File::options()
            .read(true)
            .custom_flags(DIRECTORY | NOFOLLOW | CLOEXEC)
            .open(path)
            .map_err(|_| "E_PATH")
    }
    pub fn open_child(parent: &File, part: &str, directory: bool) -> Result<Option<File>> {
        let part = CString::new(part).map_err(|_| "E_PATH")?;
        let flags = NOFOLLOW | NONBLOCK | CLOEXEC | if directory { DIRECTORY } else { 0 };
        // SAFETY: parent remains live; part is a terminated CString. No O_CREAT
        // flag is passed, so openat does not consume a variadic mode argument.
        let descriptor = unsafe { openat(parent.as_raw_fd(), part.as_ptr(), flags) };
        if descriptor < 0 {
            return if std::io::Error::last_os_error().kind() == std::io::ErrorKind::NotFound {
                Ok(None)
            } else {
                Err("E_PATH")
            };
        }
        // SAFETY: openat returned a new owned descriptor. File closes it once.
        Ok(Some(unsafe { File::from_raw_fd(descriptor) }))
    }
}

#[cfg(all(test, unix))]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    static NEXT: AtomicUsize = AtomicUsize::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "guard-test-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir_all(&root).unwrap();
            Self(root)
        }
        fn guard(&self) -> Guard {
            Guard::new(self.0.to_str().unwrap()).unwrap()
        }
        fn write(&self, relative: &str, raw: &[u8]) {
            let path = self.0.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, raw).unwrap();
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    #[test]
    fn read_count_and_unique_access_count_are_independently_bounded() {
        let fixture = Fixture::new();
        fixture.write("empty", b"");
        let mut guard = fixture.guard();
        for _ in 0..FILE_COUNT {
            assert_eq!(guard.read("empty"), Ok(Vec::new()));
        }
        assert_eq!(guard.read("empty"), Err("E_LIMIT"));
        let mut guard = fixture.guard();
        for index in 0..=FILE_COUNT {
            fixture.write(&format!("file-{index}"), b"");
            let result = guard.exists(&format!("file-{index}"));
            assert_eq!(
                result,
                if index < FILE_COUNT {
                    Ok(true)
                } else {
                    Err("E_LIMIT")
                }
            );
        }
    }
    #[test]
    fn exact_file_and_cumulative_byte_limits() {
        let fixture = Fixture::new();
        fixture.write("full", &vec![b'x'; FILE_LIMIT]);
        fixture.write("extra", b"x");
        fixture.write("too-large", &vec![b'x'; FILE_LIMIT + 1]);
        let mut guard = fixture.guard();
        for _ in 0..4 {
            assert_eq!(guard.read("full").unwrap().len(), FILE_LIMIT);
        }
        assert_eq!(guard.read("extra"), Err("E_LIMIT"));
        assert_eq!(fixture.guard().read("too-large"), Err("E_LIMIT"));
    }
    #[test]
    fn deadline_and_profile_replacement_refuse_further_access() {
        let fixture = Fixture::new();
        fixture.write(".mir/repo-profile.toml", b"protected_paths = []\n");
        fixture.write("readme", b"ok");
        let mut guard = fixture.guard();
        guard.deadline = Instant::now();
        assert_eq!(guard.read("readme"), Err("E_TIMEOUT"));
        let mut guard = fixture.guard();
        fixture.write(".mir/new-profile.toml", b"secret_paths = [\"readme\"]\n");
        fs::rename(
            fixture.0.join(".mir/new-profile.toml"),
            fixture.0.join(".mir/repo-profile.toml"),
        )
        .unwrap();
        assert_eq!(guard.read("readme"), Err("E_PATH"));
    }
    #[test]
    fn missing_profile_creation_invalidates_pinned_guard() {
        let fixture = Fixture::new();
        let guard = fixture.guard();
        fixture.write(".mir/repo-profile.toml", b"protected_paths = []\n");
        assert_eq!(guard.tick(), Err("E_PATH"));
    }
    #[test]
    fn profile_stamp_check_bypasses_its_own_protection_patterns() {
        let fixture = Fixture::new();
        fixture.write(
            ".mir/repo-profile.toml",
            b"protected_paths = [\"*.toml\"]\n",
        );
        fixture.write("readme", b"ok");
        let mut guard = fixture.guard();
        assert_eq!(guard.tick(), Ok(()));
        assert_eq!(guard.read("readme"), Ok(b"ok".to_vec()));
        assert_eq!(guard.read(".mir/repo-profile.toml"), Err("E_PROTECTED"));
    }
    #[test]
    fn root_replacement_and_symlink_components_refuse_access() {
        use std::os::unix::fs::symlink;
        let fixture = Fixture::new();
        fixture.write("allowed", b"ok");
        symlink("allowed", fixture.0.join("alias")).unwrap();
        let mut guard = fixture.guard();
        assert_eq!(guard.read("alias"), Err("E_PATH"));
        let moved = fixture.0.with_extension("moved");
        fs::rename(&fixture.0, &moved).unwrap();
        fs::create_dir(&fixture.0).unwrap();
        assert_eq!(guard.tick(), Err("E_PATH"));
        fs::remove_dir_all(moved).unwrap();
    }
    #[test]
    fn profile_sections_globs_and_provenance_are_enforced() {
        let fixture = Fixture::new();
        fixture.write(
            ".mir/repo-profile.toml",
            b"[boundaries]\nsecrets = [\"private/**\", \"file-[a-c].txt\"]\n",
        );
        fixture.write("private/inside", b"private");
        fixture.write("file-b.txt", b"private");
        fixture.write("public", b"hello");
        let mut guard = fixture.guard();
        assert_eq!(guard.read("private/inside"), Err("E_PROTECTED"));
        assert_eq!(guard.read("file-b.txt"), Err("E_PROTECTED"));
        assert_eq!(guard.read("public"), Ok(b"hello".to_vec()));
        assert_eq!(
            guard.source_digests["public"],
            Value::String(crate::digest::sha256(b"hello"))
        );
        assert_eq!(guard.exists("missing"), Ok(false));
        assert_eq!(guard.sources["missing"], Value::String("missing".into()));
    }
}

#[cfg(all(unix, not(any(target_os = "macos", target_os = "linux"))))]
mod platform {
    use super::{File, Path, Result, Stamp};
    pub fn stamp(_file: &File) -> Result<Stamp> {
        Err("E_PATH")
    }
    pub fn path_stamp(_path: &Path) -> Result<Stamp> {
        Err("E_PATH")
    }
    pub fn open_root(_path: &Path) -> Result<File> {
        Err("E_PATH")
    }
    pub fn open_child(_parent: &File, _part: &str, _directory: bool) -> Result<Option<File>> {
        Err("E_PATH")
    }
}

// Win32 calls operate only on owned File handles. Ancestors are held without
// FILE_SHARE_DELETE until the terminal handle is dropped, preventing rename or
// reparse replacement during the complete read and verification interval.
#[cfg(windows)]
#[allow(unsafe_code)]
mod platform {
    use super::{File, Path, PathBuf, Result, Stamp, windows_root};
    use std::ffi::c_void;
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::{AsRawHandle, FromRawHandle};
    #[repr(C)]
    #[derive(Default)]
    struct FileTime {
        low: u32,
        high: u32,
    }
    #[repr(C)]
    #[derive(Default)]
    struct Information {
        attributes: u32,
        created: FileTime,
        accessed: FileTime,
        modified: FileTime,
        serial: u32,
        size_high: u32,
        size_low: u32,
        links: u32,
        index_high: u32,
        index_low: u32,
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CreateFileW(
            name: *const u16,
            access: u32,
            share: u32,
            security: *mut c_void,
            creation: u32,
            flags: u32,
            template: *mut c_void,
        ) -> *mut c_void;
        fn GetFileInformationByHandle(handle: *mut c_void, info: *mut Information) -> i32;
        fn GetFinalPathNameByHandleW(
            handle: *mut c_void,
            buffer: *mut u16,
            size: u32,
            flags: u32,
        ) -> u32;
        fn GetFileType(handle: *mut c_void) -> u32;
    }
    fn information(file: &File) -> Result<Information> {
        let mut info = Information::default();
        // SAFETY: the handle remains owned by File and info is writable and has
        // the exact BY_HANDLE_FILE_INFORMATION C layout.
        if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0 {
            return Err("E_PATH");
        }
        Ok(info)
    }
    fn nanos(time: &FileTime) -> i128 {
        (i128::from((u64::from(time.high) << 32) | u64::from(time.low)) - 116_444_736_000_000_000)
            * 100
    }
    pub fn stamp(file: &File) -> Result<Stamp> {
        let info = information(file)?;
        Ok(Stamp {
            device: u64::from(info.serial),
            inode: (u64::from(info.index_high) << 32) | u64::from(info.index_low),
            size: (u64::from(info.size_high) << 32) | u64::from(info.size_low),
            modified: nanos(&info.modified),
            changed: nanos(&info.created),
        })
    }
    pub fn path_stamp(path: &Path) -> Result<Stamp> {
        let file = open_path(path, false).map_err(|_| "E_PATH")?;
        validate_final_path(&final_path(&file)?, path)?;
        stamp(&file)
    }
    pub fn open_root(path: &Path) -> Result<File> {
        let file = open_path(path, true).map_err(|_| "E_PATH")?;
        validate_final_path(&final_path(&file)?, path)?;
        Ok(file)
    }
    pub fn final_path(file: &File) -> Result<PathBuf> {
        let mut buffer = vec![0u16; 32_768];
        // SAFETY: valid live handle, writable buffer and matching capacity.
        let count = unsafe {
            GetFinalPathNameByHandleW(
                file.as_raw_handle(),
                buffer.as_mut_ptr(),
                buffer.len() as u32,
                0,
            )
        };
        if count == 0 || count as usize >= buffer.len() {
            return Err("E_PATH");
        }
        let text = String::from_utf16(&buffer[..count as usize]).map_err(|_| "E_PATH")?;
        let text = text.strip_prefix("\\\\?\\").ok_or("E_PATH")?;
        windows_root(text)?;
        Ok(PathBuf::from(text))
    }
    pub fn open_path(path: &Path, directory: bool) -> Result<File> {
        let text = path.to_str().ok_or("E_PATH")?;
        windows_root(text)?;
        let mut wide: Vec<_> = path.as_os_str().encode_wide().collect();
        if wide.contains(&0) {
            return Err("E_PATH");
        }
        wide.push(0);
        // SAFETY: wide is terminated and live; null security/template arguments
        // are documented defaults. The returned handle is immediately owned.
        let handle = unsafe {
            CreateFileW(
                wide.as_ptr(),
                0x80000000,
                1 | 2,
                std::ptr::null_mut(),
                3,
                0x00200000 | 0x02000000,
                std::ptr::null_mut(),
            )
        };
        if handle as isize == -1 {
            return if std::io::Error::last_os_error().kind() == std::io::ErrorKind::NotFound {
                Err("E_IO_MISSING")
            } else {
                Err("E_PATH")
            };
        }
        // SAFETY: CreateFileW returned a fresh handle; File owns its sole close.
        let file = unsafe { File::from_raw_handle(handle) };
        let info = information(&file)?;
        // SAFETY: File owns a valid live handle and GetFileType borrows it.
        let disk = unsafe { GetFileType(file.as_raw_handle()) } == 1;
        if info.attributes & 0x400 != 0 || !disk || (directory && info.attributes & 0x10 == 0) {
            return Err("E_PATH");
        }
        Ok(file)
    }
    pub fn validate_final_path(final_path: &Path, requested: &Path) -> Result<()> {
        if final_path.to_str().ok_or("E_PATH")?.to_lowercase()
            != requested
                .to_str()
                .ok_or("E_PATH")?
                .replace('/', "\\")
                .to_lowercase()
        {
            return Err("E_PATH");
        }
        Ok(())
    }
}
