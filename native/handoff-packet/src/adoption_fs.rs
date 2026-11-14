//! Descriptor-relative adoption mutations; never follow substituted parent symlinks.
#[cfg(windows)]
mod windows;
#[cfg(all(test, windows))]
mod windows_entry_tests;
#[cfg(all(test, windows))]
mod windows_mutation_tests;
#[cfg(all(test, windows))]
mod windows_parent_tests;
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

/// Volume and complete object ID; Windows IDs must never be truncated to inode size.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Identity {
    volume: u64,
    id: [u8; 16],
}
#[cfg(unix)]
fn unix_identity(volume: u64, inode: u64) -> Identity {
    let mut id = [0; 16];
    id[..8].copy_from_slice(&inode.to_le_bytes());
    Identity { volume, id }
}
fn file_identity(file: &File) -> io::Result<Identity> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        let metadata = file.metadata()?;
        Ok(unix_identity(metadata.dev(), metadata.ino()))
    }
    #[cfg(windows)]
    windows::file_identity(file)
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

#[cfg(unix)]
pub(crate) fn nonblocking(file: &impl AsRawFd) -> io::Result<()> {
    // std has no nonblocking setter for ChildStdout/ChildStderr. Borrow the live
    // descriptor only for fcntl; ownership stays with the caller's pipe handle.
    let descriptor = file.as_raw_fd();
    // SAFETY: a live borrowed descriptor; F_GETFL consumes no variadic argument.
    let flags = unsafe { libc::fcntl(descriptor, libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: same live descriptor and integer flags from F_GETFL.
    if unsafe { libc::fcntl(descriptor, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

#[cfg(unix)]
pub(crate) fn monotonic_seconds() -> io::Result<f64> {
    #[cfg(target_vendor = "apple")]
    let clock = libc::CLOCK_UPTIME_RAW;
    #[cfg(not(target_vendor = "apple"))]
    let clock = libc::CLOCK_MONOTONIC;
    let mut time = std::mem::MaybeUninit::<libc::timespec>::uninit();
    // SAFETY: clock is a supported monotonic clock and time is writable. On
    // macOS UPTIME_RAW shares CPython's mach_absolute_time epoch (MONOTONIC
    // does not). Match Python's integer nanoseconds -> double seconds conversion.
    if unsafe { libc::clock_gettime(clock, time.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: successful clock_gettime initialized the complete timespec.
    let time = unsafe { time.assume_init() };
    Ok((i128::from(time.tv_sec) * 1_000_000_000 + i128::from(time.tv_nsec)) as f64 / 1e9)
}

pub(crate) fn relative<'a>(root: &Path, path: &'a Path) -> io::Result<&'a Path> {
    let relative = path.strip_prefix(root).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "mutation path must be below its root",
        )
    })?;
    if relative.components().next().is_none()
        || relative
            .components()
            .any(|p| !matches!(p, Component::Normal(_)))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "mutation path must be below its root",
        ));
    }
    Ok(relative)
}

pub(crate) fn parent(root: &Path, path: &Path) -> io::Result<Parent> {
    let relative = relative(root, path)?;
    #[cfg(windows)]
    return windows::parent(root, relative);
    #[cfg(not(windows))]
    let mut parts = relative.components().peekable();
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
    #[cfg(not(windows))]
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "descriptor-relative adoption requires Unix",
    ))
}
impl Parent {
    /// Refuse effects through an old descriptor when its visible parent changed.
    /// Descriptor APIs cannot exclude a rename after this final identity check.
    pub(crate) fn verify_parent(&self, root: &Path, path: &Path) -> io::Result<()> {
        let current = parent(root, path)?;
        if file_identity(&self.directory)? == file_identity(&current.directory)? {
            return Ok(());
        }
        Err(io::Error::other("mutation parent changed"))
    }
    pub(crate) fn open_file(&self) -> io::Result<File> {
        self.open(false, false)
    }

    // Current production callers are Unix-only; Windows exercises the primitive
    // in entry tests until its callers migrate to the shared filesystem layer.
    #[cfg(any(unix, test))]
    pub(crate) fn open_private(&self, append: bool) -> io::Result<File> {
        self.open(true, append)
    }

    fn open(&self, write: bool, append: bool) -> io::Result<File> {
        #[cfg(unix)]
        {
            let name = c_name(&self.name)?;
            let access = if write {
                libc::O_WRONLY | libc::O_CREAT | if append { libc::O_APPEND } else { 0 }
            } else {
                libc::O_RDONLY
            };
            // SAFETY: live pinned parent and valid basename. NOFOLLOW rejects
            // a final link; NONBLOCK lets callers reject a FIFO without waiting.
            // Truncation follows descriptor validation and private permissions.
            opened(unsafe {
                libc::openat(
                    self.directory.as_raw_fd(),
                    name.as_ptr(),
                    access | libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC,
                    0o600 as libc::c_uint,
                )
            })
        }
        #[cfg(windows)]
        windows::open(self, write, append)
    }

    pub(crate) fn directory_empty(&self) -> io::Result<bool> {
        #[cfg(any(target_vendor = "apple", target_os = "linux"))]
        {
            use std::os::fd::IntoRawFd;
            struct Listing(*mut libc::DIR);
            impl Drop for Listing {
                fn drop(&mut self) {
                    // SAFETY: fdopendir gave this guard sole ownership, and no
                    // directory entry pointer outlives the guard.
                    unsafe {
                        libc::closedir(self.0);
                    }
                }
            }
            let name = c_name(&self.name)?;
            // SAFETY: live pinned parent and valid basename; a readable handle
            // preserves listdir permission errors and NOFOLLOW rejects links.
            let file = opened(unsafe {
                libc::openat(
                    self.directory.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                )
            })?;
            let descriptor = file.into_raw_fd();
            // SAFETY: descriptor is an owned readable directory fd. Ownership
            // transfers to the stream only when fdopendir succeeds.
            let stream = unsafe { libc::fdopendir(descriptor) };
            if stream.is_null() {
                let error = io::Error::last_os_error();
                // SAFETY: unsuccessful fdopendir leaves descriptor owned here.
                drop(unsafe { File::from_raw_fd(descriptor) });
                return Err(error);
            }
            let listing = Listing(stream);
            loop {
                #[cfg(target_vendor = "apple")]
                // SAFETY: __error returns this thread's live errno location.
                let errno = unsafe { libc::__error() };
                #[cfg(target_os = "linux")]
                // SAFETY: __errno_location returns this thread's errno location.
                let errno = unsafe { libc::__errno_location() };
                // SAFETY: errno is thread-local; the stream remains owned by
                // listing, and each entry is consumed before the next readdir.
                let entry = unsafe {
                    *errno = 0;
                    libc::readdir(listing.0)
                };
                if entry.is_null() {
                    // SAFETY: same live thread-local errno pointer.
                    let error = unsafe { *errno };
                    return if error == 0 {
                        Ok(true)
                    } else {
                        Err(io::Error::from_raw_os_error(error))
                    };
                }
                // SAFETY: successful readdir returns a valid NUL-terminated
                // d_name until the next call on this stream.
                let name = unsafe { std::ffi::CStr::from_ptr((*entry).d_name.as_ptr()) };
                if !matches!(name.to_bytes(), b"." | b"..") {
                    return Ok(false);
                }
            }
        }
        #[cfg(windows)]
        {
            windows::directory_empty(self)
        }
        #[cfg(not(any(windows, target_vendor = "apple", target_os = "linux")))]
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "descriptor-relative directory listing requires macOS or Linux",
        ))
    }

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
        #[cfg(windows)]
        windows::sync_file(&self.directory)
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
                    libc::O_RDWR
                        | libc::O_CREAT
                        | libc::O_EXCL
                        | libc::O_NOFOLLOW
                        | libc::O_CLOEXEC,
                    mode as libc::c_uint,
                )
            })
        }
        #[cfg(windows)]
        windows::create(self, name, mode)
    }
    pub(crate) fn identity(&self) -> io::Result<Option<Identity>> {
        self.object_identity(false)
    }
    pub(crate) fn object_identity(&self, directory: bool) -> io::Result<Option<Identity>> {
        #[cfg(unix)]
        {
            let name = c_name(&self.name)?;
            let mut metadata = std::mem::MaybeUninit::<libc::stat>::uninit();
            // SAFETY: live directory fd, valid basename, writable stat record.
            if unsafe {
                libc::fstatat(
                    self.directory.as_raw_fd(),
                    name.as_ptr(),
                    metadata.as_mut_ptr(),
                    libc::AT_SYMLINK_NOFOLLOW,
                )
            } != 0
            {
                return Err(io::Error::last_os_error());
            }
            // SAFETY: successful fstatat initialized the complete stat record.
            let metadata = unsafe { metadata.assume_init() };
            Ok((metadata.st_mode & libc::S_IFMT
                == if directory {
                    libc::S_IFDIR
                } else {
                    libc::S_IFREG
                })
            .then_some(unix_identity(metadata.st_dev as u64, metadata.st_ino)))
        }
        #[cfg(windows)]
        windows::object_identity(self, &self.name, directory)
    }
    fn matches(&self, expected: &Identity) -> io::Result<bool> {
        Ok(self.identity()?.as_ref() == Some(expected))
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
        #[cfg(windows)]
        windows::unlink(self, name, directory)
    }
}
#[cfg(unix)]
pub(crate) fn owns_file(pinned: &Parent, name: &std::ffi::OsStr, output: &File) -> bool {
    use std::os::{
        fd::AsRawFd,
        unix::{ffi::OsStrExt, fs::MetadataExt},
    };
    let Ok(created) = output.metadata() else {
        return false;
    };
    let Ok(name) = std::ffi::CString::new(name.as_bytes()) else {
        return false;
    };
    let mut current = std::mem::MaybeUninit::<libc::stat>::uninit();
    // SAFETY: the pinned directory fd, NUL-terminated basename and writable stat
    // allocation stay live. NOFOLLOW compares the entry itself, never its target.
    if unsafe {
        libc::fstatat(
            pinned.directory.as_raw_fd(),
            name.as_ptr(),
            current.as_mut_ptr(),
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } != 0
    {
        return false;
    }
    // SAFETY: successful fstatat initialized the complete record.
    let current = unsafe { current.assume_init() };
    i128::from(created.dev()) == i128::from(current.st_dev)
        && i128::from(created.ino()) == i128::from(current.st_ino)
}

#[cfg(windows)]
pub(crate) fn owns_file(pinned: &Parent, name: &OsStr, output: &File) -> bool {
    file_identity(output).is_ok_and(|created| {
        windows::object_identity(pinned, name, false).is_ok_and(|current| current == Some(created))
    })
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
    #[cfg(windows)]
    windows::mkdir(&parent, mode)
}
pub(crate) struct Move {
    source: Parent,
    destination: Parent,
}
impl Move {
    pub(crate) fn prepare(root: &Path, source: &Path, destination: &Path) -> io::Result<Self> {
        let source = parent(root, source)?;
        let destination = parent(root, destination)?;
        // Generic moves also support unreadable files. Artifact publication
        // supplies identity from its still-open verified descriptor instead.
        source
            .identity()?
            .ok_or_else(|| io::Error::other("source is not a regular file"))?;
        Ok(Self {
            source,
            destination,
        })
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
            if status != 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        }
        #[cfg(windows)]
        windows::rename(&self.source, &self.destination)
    }
}

/// An exclusive destination-directory temporary; one descriptor for byte work.
/// Drop cleans through its pinned descriptor; installers opt into visible-parent checks.
pub(crate) struct StagedFile {
    pub(crate) file: File,
    pub(crate) path: std::path::PathBuf,
    source: Parent,
    root: std::path::PathBuf,
    cleanup_disabled: std::cell::Cell<bool>,
    requires_visible_parent: bool,
}
impl StagedFile {
    // Current production callers use this wrapper only on Unix; Windows uses
    // create_with/create_with_parent_check, with this convenience API in tests.
    #[cfg(any(unix, test))]
    pub(crate) fn create(root: &Path, path: &Path) -> io::Result<Self> {
        Self::create_with(root, path, |_| Ok(()))
    }
    pub(crate) fn create_with(
        root: &Path,
        path: &Path,
        before: impl FnOnce(&Path) -> io::Result<()>,
    ) -> io::Result<Self> {
        Self::create_with_parent_check(root, path, false, before)
    }
    pub(crate) fn create_with_parent_check(
        root: &Path,
        path: &Path,
        requires_visible_parent: bool,
        before: impl FnOnce(&Path) -> io::Result<()>,
    ) -> io::Result<Self> {
        let source = parent(root, path)?;
        before(path)?;
        if requires_visible_parent {
            source.verify_parent(root, path)?;
        }
        // Failure to create gives no ownership and must never trigger cleanup.
        let file = source.create(&source.name, 0o600)?;
        Ok(Self {
            file,
            path: path.to_path_buf(),
            source,
            root: root.to_owned(),
            cleanup_disabled: std::cell::Cell::new(false),
            requires_visible_parent,
        })
    }
    pub(crate) fn identity(&self) -> io::Result<Identity> {
        file_identity(&self.file)
    }
    pub(crate) fn contents(&mut self, limit: usize) -> io::Result<Vec<u8>> {
        use std::io::{Read, Seek};
        self.file.sync_all()?;
        self.file.rewind()?;
        let mut bytes = Vec::new();
        (&mut self.file)
            .take(limit as u64 + 1)
            .read_to_end(&mut bytes)?;
        Ok(bytes)
    }
    pub(crate) fn publish(&self, root: &Path, destination: &Path) -> io::Result<Parent> {
        // Reject changed visible ancestors before effects. Compare the named
        // source against the verified descriptor, never a replacement reopen.
        if self.requires_visible_parent {
            self.source.verify_parent(root, &self.path)?;
        } else {
            let _ = parent(root, &self.path)?;
        }
        let destination = parent(root, destination)?;
        let expected = self.identity()?;
        if !self.source.matches(&expected)? {
            return Err(io::Error::other("source changed during publication"));
        }
        #[cfg(unix)]
        {
            let movement = Move {
                source: Parent {
                    directory: self.source.directory.try_clone()?,
                    name: self.source.name.clone(),
                },
                destination: Parent {
                    directory: destination.directory.try_clone()?,
                    name: destination.name.clone(),
                },
            };
            movement.rename()?;
        }
        #[cfg(windows)]
        windows::rename_file(&self.file, &destination)?;
        self.cleanup_disabled.set(true);
        Ok(destination)
    }
    // An explicit cleanup failure must not be retried by Drop.
    pub(crate) fn keep(&self) {
        self.cleanup_disabled.set(true);
    }
    pub(crate) fn remove(&self) -> io::Result<()> {
        if self.cleanup_disabled.get() {
            return Ok(());
        }
        if self.requires_visible_parent {
            self.source.verify_parent(&self.root, &self.path)?;
        }
        let expected = self.identity()?;
        match self.source.identity() {
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(error),
            Ok(Some(identity)) if identity == expected => (),
            _ => return Err(io::Error::other("source changed during cleanup")),
        }
        #[cfg(unix)]
        self.source.unlink(&self.source.name, false)?;
        #[cfg(windows)]
        windows::dispose_file(&self.file)?;
        self.cleanup_disabled.set(true);
        Ok(())
    }
}
impl Drop for StagedFile {
    fn drop(&mut self) {
        let _ = self.remove();
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    #[test]
    fn source_swap_after_stat_matches_reference_without_touching_link_target() {
        use std::os::unix::fs::symlink;
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let source = root.join("source");
        let destination = root.join("destination");
        let outside = root.join("outside");
        std::fs::write(&source, b"verified").unwrap();
        std::fs::write(&outside, b"sentinel").unwrap();
        let movement = Move::prepare(&root, &source, &destination).unwrap();
        std::fs::rename(&source, root.join("saved")).unwrap();
        symlink(&outside, &source).unwrap();
        movement.rename().unwrap();
        assert!(destination.is_symlink());
        assert_eq!(std::fs::read(outside).unwrap(), b"sentinel");
    }
    #[test]
    fn unreadable_file_and_search_only_parents_remain_movable() {
        let temp = tempfile::tempdir().expect("synthetic root");
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

#[cfg(all(test, unix))]
mod owned_cleanup_tests {
    use super::*;
    use std::{fs, io::Write};
    #[test]
    fn e02_creation_uses_pinned_parent_after_real_directory_replacement() {
        let t = tempfile::tempdir().unwrap();
        let root = t.path().canonicalize().unwrap();
        let parent = root.join("agents");
        let moved = root.join("moved");
        fs::create_dir(&parent).unwrap();
        let staged = StagedFile::create_with(&root, &parent.join("temp"), |_| {
            fs::rename(&parent, &moved)?;
            fs::create_dir(&parent)
        })
        .expect("E02 creates through the pinned parent");
        assert!(moved.join("temp").is_file());
        assert!(!parent.join("temp").exists());
        drop(staged);
        assert!(!moved.join("temp").exists());
    }
    #[test]
    fn e02_publication_uses_pinned_parent_after_real_directory_replacement() {
        let t = tempfile::tempdir().unwrap();
        let root = t.path().canonicalize().unwrap();
        let parent = root.join("agents");
        let moved = root.join("moved");
        fs::create_dir(&parent).unwrap();
        let mut staged = StagedFile::create(&root, &parent.join("temp")).unwrap();
        staged.file.write_all(b"verified").unwrap();
        fs::rename(&parent, &moved).unwrap();
        fs::create_dir(&parent).unwrap();
        staged
            .publish(&root, &parent.join("dest"))
            .expect("E02 publishes from the pinned parent");
        drop(staged);
        assert_eq!(fs::read(parent.join("dest")).unwrap(), b"verified");
        assert_eq!(fs::read_dir(&moved).unwrap().count(), 0);
    }
    #[test]
    fn contents_and_chmod_use_the_verified_descriptor() {
        use std::os::unix::fs::PermissionsExt;
        let t = tempfile::tempdir().unwrap();
        let r = t.path().canonicalize().unwrap();
        let mut staged = StagedFile::create(&r, &r.join("temp")).unwrap();
        staged.file.write_all(b"verified").unwrap();
        fs::rename(&staged.path, r.join("saved")).unwrap();
        fs::write(&staged.path, b"foreign").unwrap();
        fs::set_permissions(&staged.path, fs::Permissions::from_mode(0o640)).unwrap();
        assert_eq!(staged.contents(8).unwrap(), b"verified");
        staged
            .file
            .set_permissions(fs::Permissions::from_mode(0o755))
            .unwrap();
        assert_eq!(
            fs::metadata(r.join("saved")).unwrap().permissions().mode() & 0o777,
            0o755
        );
        assert_eq!(
            fs::metadata(&staged.path).unwrap().permissions().mode() & 0o777,
            0o640
        );
    }
    #[test]
    fn creation_collision_leaves_foreign_file() {
        let t = tempfile::tempdir().unwrap();
        let r = t.path().canonicalize().unwrap();
        let mut actual = None;
        let result = StagedFile::create_with(&r, &r.join("temp"), |p| {
            actual = Some(p.to_path_buf());
            fs::write(p, b"foreign")
        });
        assert!(result.is_err());
        assert_eq!(fs::read(actual.unwrap()).unwrap(), b"foreign");
    }
    #[test]
    fn substituted_temporary_survives_cleanup() {
        let t = tempfile::tempdir().unwrap();
        let r = t.path().canonicalize().unwrap();
        let mut s = StagedFile::create(&r, &r.join("temp")).unwrap();
        s.file.write_all(b"verified").unwrap();
        fs::rename(&s.path, r.join("saved")).unwrap();
        fs::write(&s.path, b"foreign").unwrap();
        let path = s.path.clone();
        assert!(s.publish(&r, &r.join("dest")).is_err());
        drop(s);
        assert_eq!(fs::read(path).unwrap(), b"foreign");
    }
    #[test]
    fn foreign_stage_directory_survives_drop() {
        let t = tempfile::tempdir().unwrap();
        let r = t.path().canonicalize().unwrap();
        let s = StagedFile::create(&r, &r.join("temp")).unwrap();
        let stage = r.join("temp.stage");
        if stage.exists() {
            fs::rename(&stage, r.join("saved-stage")).unwrap();
        }
        fs::create_dir(&stage).unwrap();
        drop(s);
        assert!(stage.is_dir());
    }
    #[test]
    fn published_temporary_name_is_not_owned_anymore() {
        let t = tempfile::tempdir().unwrap();
        let r = t.path().canonicalize().unwrap();
        let s = StagedFile::create(&r, &r.join("temp")).unwrap();
        let path = s.path.clone();
        s.publish(&r, &r.join("dest")).unwrap();
        fs::write(&path, b"foreign").unwrap();
        drop(s);
        assert_eq!(fs::read(path).unwrap(), b"foreign");
    }
}
