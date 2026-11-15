//! Installer-only descriptor-relative mutations.
use crate::adoption_fs::{self, StagedFile};
use crate::executor_text::IoOperation;
use std::{
    ffi::OsStr,
    io::{self, Write},
    path::{Component, Path, PathBuf},
};

/// An owned temporary whose writes, publication and cleanup use pinned handles.
pub struct PendingWrite {
    staged: StagedFile,
    root: PathBuf,
    target: PathBuf,
}
impl PendingWrite {
    pub fn prepare(
        root: &Path,
        target: &Path,
        temporary: &OsStr,
        content: &[u8],
    ) -> io::Result<Self> {
        Self::prepare_mapped(root, target, temporary, content, |_, e, _| e)
    }
    /// Preserve the filename context of the failing syscall.
    pub(crate) fn prepare_mapped<E>(
        root: &Path,
        target: &Path,
        temporary: &OsStr,
        content: &[u8],
        error: impl Fn(Option<&Path>, io::Error, IoOperation) -> E,
    ) -> Result<Self, E> {
        if !matches!(Path::new(temporary).components().next(), Some(Component::Normal(name)) if name == temporary)
        {
            return Err(error(
                Some(target),
                io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "temporary must be one basename",
                ),
                IoOperation::Win32,
            ));
        }
        let relative = adoption_fs::relative(root, target)
            .map_err(|e| error(Some(target), e, IoOperation::Win32))?;
        let mut directory = root.to_owned();
        let mut parts = relative.components().peekable();
        while let Some(part) = parts.next() {
            if parts.peek().is_none() {
                break;
            }
            directory.push(part.as_os_str());
            match adoption_fs::mkdir(root, &directory, 0o777) {
                Ok(()) => (),
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => (),
                Err(e) => return Err(error(Some(&directory), e, IoOperation::Win32)),
            }
        }
        let path = target.with_file_name(temporary);
        if adoption_fs::aliases(root, &path, target)
            .map_err(|e| error(Some(target), e, IoOperation::Win32))?
        {
            return Err(error(
                Some(target),
                io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "temporary must differ from target",
                ),
                IoOperation::Win32,
            ));
        }
        let staged = StagedFile::create_with_parent_check(root, &path, true, |_| Ok(()))
            .map_err(|e| error(Some(&path), e, IoOperation::Read))?;
        let result = (|| {
            let mut writer = staged
                .file
                .try_clone()
                .map_err(|e| error(None, e, IoOperation::Handle))?;
            let written = (|| {
                writer.write_all(content)?;
                writer.flush()?;
                writer.sync_all()
            })();
            // Python's with-statement lets a close failure replace a body failure.
            adoption_fs::close_file(writer).map_err(|e| error(None, e, IoOperation::Handle))?;
            written.map_err(|e| error(None, e, IoOperation::Handle))?;
            adoption_fs::set_mode(&staged.file, 0o644)
                .map_err(|e| error(Some(&path), e, IoOperation::Win32))
        })();
        if let Err(e) = result {
            let cleanup = staged
                .remove()
                .map_err(|e| error(Some(&path), e, IoOperation::Win32));
            staged.keep();
            cleanup?;
            return Err(e);
        }
        Ok(Self {
            staged,
            root: root.to_owned(),
            target: target.to_owned(),
        })
    }
    #[cfg(unix)]
    pub(crate) fn temporary_path(&self) -> &Path {
        &self.staged.path
    }
    /// Create, replace and snapshot restoration share atomic replacement semantics.
    pub fn publish_with(&self, before: impl FnOnce(&Path) -> io::Result<()>) -> io::Result<()> {
        before(&self.staged.path)?;
        self.staged.publish(&self.root, &self.target).map(|_| ())
    }
    pub fn cleanup_with(&self, before: impl FnOnce(&Path) -> io::Result<()>) -> io::Result<()> {
        before(&self.staged.path)?;
        let result = self.staged.remove();
        self.staged.keep();
        result
    }
}

/// Remove a file or an empty created directory, skipping an already missing entry.
pub fn remove_with(
    root: &Path,
    target: &Path,
    directory: bool,
    before: impl FnOnce() -> io::Result<()>,
) -> io::Result<()> {
    let pinned = match adoption_fs::parent(root, target) {
        Ok(pinned) => pinned,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(e),
    };
    match pinned.object_identity(directory) {
        Ok(Some(_)) => (),
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(e),
        Ok(None) => return Err(io::Error::other("mutation target has unexpected type")),
    }
    before()?;
    pinned.verify_parent(root, target)?;
    pinned.unlink(&pinned.name, directory)
}

#[cfg(all(test, unix))]
#[rustfmt::skip]
mod tests {
    use super::*;
    use std::{fs, os::unix::fs::{PermissionsExt, symlink}};
    use crate::user_runtime_windows_race_tests::snapshot;
    fn swap(path: &Path, outside: &Path) -> io::Result<()> {
        fs::rename(path, path.with_extension("saved"))?;
        symlink(outside, path)
    }
    #[test]
    fn nested_parents_atomic_modes_and_missing_removal() {
        let temp = tempfile::tempdir().unwrap(); let root = temp.path().canonicalize().unwrap();
        let target = root.join("new/nested/agent.md");
        for content in [b"create".as_slice(), b"replace", b"restore"] {
            let pending = PendingWrite::prepare(&root, &target, OsStr::new("temporary"), content).unwrap();
            pending.publish_with(|_| Ok(())).unwrap();
            assert_eq!(fs::read(&target).unwrap(), content);
            assert_eq!(fs::metadata(&target).unwrap().permissions().mode() & 0o777, 0o644);
            assert!(!target.with_file_name("temporary").exists());
        }
        remove_with(&root, &target, false, || Ok(())).unwrap();
        remove_with(&root, &target, false, || panic!("missing target skips mutation")).unwrap();
        for directory in [root.join("new/nested"), root.join("new")] {
            remove_with(&root, &directory, true, || Ok(())).unwrap();
        }
        for temporary in ["../escape", "nested/temp", "", ".", ".."] {
            assert!(PendingWrite::prepare(&root, &root.join("agent"), OsStr::new(temporary), b"x").is_err());
        }
    }
    #[test]
    fn missing_parent_removal_is_a_noop() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        for directory in [false, true] {
            remove_with(&root, &root.join("missing/nested/target"), directory,
                || panic!("missing parent skips mutation")).unwrap();
        }
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
    }
    #[test]
    fn directory_cleanup_rejects_swaps() {
        for site in ["ancestor", "leaf", "temporary"] {
            let temp = tempfile::tempdir().unwrap(); let base = temp.path().canonicalize().unwrap();
            let root = base.join("root"); let dir = root.join("agents");
            let child = dir.join("empty"); let outside = base.join("outside");
            fs::create_dir_all(&child).unwrap(); fs::create_dir(&outside).unwrap();
            fs::write(outside.join("keep"), b"OUTSIDE").unwrap(); let expected = snapshot(&outside);
            let result = remove_with(&root, &child, true, || match site {
                "ancestor" => swap(&dir, &outside), "leaf" => swap(&child, &outside),
                "temporary" => symlink(&outside, child.join("temporary")), _ => unreachable!(),
            });
            assert_eq!(snapshot(&outside), expected, "directory cleanup/{site}"); assert!(result.is_err());
        }
    }
    #[test]
    fn replaced_parent_before_installer_publication_is_rejected() {
        let temp = tempfile::tempdir().unwrap(); let base = temp.path().canonicalize().unwrap();
        let root = base.join("root"); let dir = root.join("agents"); let outside = base.join("outside");
        fs::create_dir_all(&dir).unwrap(); fs::create_dir(&outside).unwrap();
        let pending = PendingWrite::prepare(&root, &dir.join("agent.md"), OsStr::new("temporary"), b"after").unwrap();
        let mut expected = vec![];
        let result = pending.publish_with(|_| {
            fs::rename(&dir, outside.join("moved"))?;
            fs::create_dir(&dir)?;
            expected = snapshot(&outside);
            Ok(())
        });
        assert_eq!(result.unwrap_err().to_string(), "mutation parent changed");
        drop(pending);
        assert_eq!(snapshot(&outside), expected);
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 0);
    }
    #[test]
    fn moved_parent_before_temporary_creation_is_rejected() {
        for replacement_directory in [false, true] {
            let temp = tempfile::tempdir().unwrap(); let base = temp.path().canonicalize().unwrap();
            let root = base.join("root"); let dir = root.join("agents"); let outside = base.join("outside");
            fs::create_dir_all(&dir).unwrap(); fs::create_dir(&outside).unwrap();
            let mut expected = vec![];
            let result = StagedFile::create_with_parent_check(&root, &dir.join("temporary"), true, |_| {
                fs::rename(&dir, outside.join("moved"))?;
                if replacement_directory { fs::create_dir(&dir)?; } else { symlink(outside.join("moved"), &dir)?; }
                expected = snapshot(&outside); Ok(())
            });
            assert!(result.is_err(), "moved parent must reject temporary creation"); drop(result);
            assert_eq!(snapshot(&outside), expected);
        }
    }
}
pub(crate) fn remove_required(root: &Path, target: &Path, directory: bool) -> io::Result<()> {
    let pinned = adoption_fs::parent(root, target)?;
    pinned.verify_parent(root, target)?;
    pinned.unlink(&pinned.name, directory)
}
