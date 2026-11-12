//! Descriptor-relative adoption mutations; never follow substituted parent symlinks.
#[cfg(unix)]
use std::ffi::CString;
#[cfg(unix)]
use std::os::{
    fd::{AsRawFd, FromRawFd},
    unix::ffi::OsStrExt,
};
use std::{
    ffi::{OsStr, OsString},
    fs::File,
    io,
    path::{Component, Path},
};

pub(crate) struct Parent {
    pub(crate) directory: File,
    pub(crate) name: OsString,
}

#[cfg(unix)]
fn c_name(name: &OsStr) -> io::Result<CString> {
    CString::new(name.as_bytes())
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "embedded null byte"))
}
#[cfg(unix)]
fn opened(descriptor: libc::c_int) -> io::Result<File> {
    if descriptor < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: a successful open/openat returned a new owned descriptor. File
    // takes its ownership exactly once and closes it on every return path.
    Ok(unsafe { File::from_raw_fd(descriptor) })
}

pub(crate) fn parent(root: &Path, path: &Path) -> io::Result<Parent> {
    let relative = path.strip_prefix(root).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "mutation path must be below its root",
        )
    })?;
    let mut parts = relative.components().peekable();
    if parts.peek().is_none()
        || relative
            .components()
            .any(|p| !matches!(p, Component::Normal(_)))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "mutation path must be below its root",
        ));
    }
    #[cfg(unix)]
    {
        #[cfg(target_vendor = "apple")]
        let access = libc::O_SEARCH;
        #[cfg(target_os = "linux")]
        let access = libc::O_PATH;
        #[cfg(not(any(target_vendor = "apple", target_os = "linux")))]
        let access = libc::O_RDONLY;
        let flags = access | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC;
        if !root.is_absolute() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "mutation root must be absolute",
            ));
        }
        let anchor = c_name(OsStr::new("/"))?;
        // SAFETY: anchor is NUL terminated and lives through open. No creation
        // flag is set. The returned descriptor is immediately owned by File.
        let mut directory = opened(unsafe { libc::open(anchor.as_ptr(), flags) })?;
        // Canonical roots have no symlink components. Traverse from / so a
        // substituted ancestor above the root cannot redirect any mutation.
        for part in root.components() {
            match part {
                Component::RootDir => continue,
                Component::Normal(name) => {
                    let name = c_name(name)?;
                    // SAFETY: live directory fd and valid component. Each step
                    // requires a directory and refuses symlinks independently.
                    directory = opened(unsafe {
                        libc::openat(directory.as_raw_fd(), name.as_ptr(), flags)
                    })?;
                }
                _ => {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "mutation root must be canonical",
                    ));
                }
            }
        }
        while let Some(part) = parts.next() {
            let name = part.as_os_str();
            if parts.peek().is_none() {
                return Ok(Parent {
                    directory,
                    name: name.to_owned(),
                });
            }
            let name = c_name(name)?;
            // SAFETY: directory owns a live fd and name lives through openat.
            // O_DIRECTORY|O_NOFOLLOW rejects a symlink at each traversal step.
            directory =
                opened(unsafe { libc::openat(directory.as_raw_fd(), name.as_ptr(), flags) })?;
        }
    }
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "descriptor-relative adoption requires Unix",
    ))
}
impl Parent {
    pub(crate) fn sync_file(&self) -> io::Result<File> {
        #[cfg(unix)]
        {
            let name = c_name(OsStr::new("."))?;
            // SAFETY: live pinned directory and static basename. Journal fsync
            // needs a normal readable handle, preserving its permission contract.
            opened(unsafe {
                libc::openat(
                    self.directory.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                )
            })
        }
        #[cfg(not(unix))]
        self.directory.try_clone()
    }
    pub(crate) fn create(&self, name: &OsStr, mode: u32) -> io::Result<File> {
        #[cfg(unix)]
        {
            let name = c_name(name)?;
            // SAFETY: live parent descriptor, valid name and mode; create_new
            // and NOFOLLOW prevent replacing or opening an existing symlink.
            opened(unsafe {
                libc::openat(
                    self.directory.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_WRONLY
                        | libc::O_CREAT
                        | libc::O_EXCL
                        | libc::O_NOFOLLOW
                        | libc::O_CLOEXEC,
                    mode as libc::c_uint,
                )
            })
        }
        #[cfg(not(unix))]
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "descriptor-relative adoption requires Unix",
        ))
    }
    pub(crate) fn unlink(&self, name: &OsStr, directory: bool) -> io::Result<()> {
        #[cfg(unix)]
        {
            let name = c_name(name)?;
            // SAFETY: live parent descriptor and valid name, no borrowed memory
            // escapes unlinkat; it never follows the final symlink.
            let result = unsafe {
                libc::unlinkat(
                    self.directory.as_raw_fd(),
                    name.as_ptr(),
                    if directory { libc::AT_REMOVEDIR } else { 0 },
                )
            };
            if result == 0 {
                return Ok(());
            }
            Err(io::Error::last_os_error())
        }
        #[cfg(not(unix))]
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "descriptor-relative adoption requires Unix",
        ))
    }
}
pub(crate) fn mkdir(root: &Path, path: &Path, mode: u32) -> io::Result<()> {
    let parent = parent(root, path)?;
    #[cfg(unix)]
    {
        let name = c_name(&parent.name)?;
        // SAFETY: live parent descriptor and valid name, mkdirat receives only
        // the target basename and cannot traverse a substituted parent.
        if unsafe {
            libc::mkdirat(
                parent.directory.as_raw_fd(),
                name.as_ptr(),
                mode as libc::mode_t,
            )
        } == 0
        {
            return Ok(());
        }
        Err(io::Error::last_os_error())
    }
    #[cfg(not(unix))]
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "descriptor-relative adoption requires Unix",
    ))
}
pub(crate) struct Move {
    source: Parent,
    destination: Parent,
}
impl Move {
    pub(crate) fn prepare(root: &Path, source: &Path, destination: &Path) -> io::Result<Self> {
        let source = parent(root, source)?;
        let destination = parent(root, destination)?;
        #[cfg(unix)]
        {
            let name = c_name(&source.name)?;
            let mut metadata = std::mem::MaybeUninit::<libc::stat>::uninit();
            // SAFETY: live parent descriptor, valid basename and writable stat
            // allocation. Read metadata only after fstatat reports success.
            // NOFOLLOW refuses leaf symlinks without requiring file read access.
            let status = unsafe {
                libc::fstatat(
                    source.directory.as_raw_fd(),
                    name.as_ptr(),
                    metadata.as_mut_ptr(),
                    libc::AT_SYMLINK_NOFOLLOW,
                )
            };
            if status != 0 {
                return Err(io::Error::last_os_error());
            }
            // SAFETY: fstatat successfully initialized the whole stat record.
            let metadata = unsafe { metadata.assume_init() };
            if metadata.st_mode & libc::S_IFMT != libc::S_IFREG {
                return Err(io::Error::other("source is not a regular file"));
            }
            Ok(Self {
                source,
                destination,
            })
        }
        #[cfg(not(unix))]
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "descriptor-relative adoption requires Unix",
        ))
    }
    pub(crate) fn rename(&self) -> io::Result<()> {
        #[cfg(unix)]
        {
            let source = c_name(&self.source.name)?;
            let destination = c_name(&self.destination.name)?;
            // SAFETY: both parent descriptors stay live throughout renameat;
            // both names are NUL terminated and contain no path separators.
            let status = unsafe {
                libc::renameat(
                    self.source.directory.as_raw_fd(),
                    source.as_ptr(),
                    self.destination.directory.as_raw_fd(),
                    destination.as_ptr(),
                )
            };
            if status == 0 {
                return Ok(());
            }
            Err(io::Error::last_os_error())
        }
        #[cfg(not(unix))]
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "descriptor-relative adoption requires Unix",
        ))
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    #[test]
    fn unreadable_file_and_search_only_parents_remain_movable() {
        let scratch = Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/stage-e01");
        std::fs::create_dir_all(&scratch).expect("scratch");
        let temp = tempfile::tempdir_in(scratch).expect("synthetic root");
        let root = std::fs::canonicalize(temp.path()).expect("canonical root");
        let source_dir = root.join("source");
        let destination_dir = root.join("destination");
        std::fs::create_dir(&source_dir).expect("source parent");
        std::fs::create_dir(&destination_dir).expect("destination parent");
        let source = source_dir.join("payload");
        let destination = destination_dir.join("payload");
        std::fs::write(&source, b"PAYLOAD").expect("source");
        std::fs::set_permissions(&source, std::fs::Permissions::from_mode(0o0))
            .expect("unreadable file");
        for dir in [&source_dir, &destination_dir] {
            std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o300))
                .expect("search-only parent");
        }
        let result =
            Move::prepare(&root, &source, &destination).and_then(|movement| movement.rename());
        for dir in [&source_dir, &destination_dir] {
            std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o700))
                .expect("restore parent");
        }
        result.expect("rename needs search/write, not read permission");
        assert!(!source.exists());
        assert!(destination.is_file());
    }
}
