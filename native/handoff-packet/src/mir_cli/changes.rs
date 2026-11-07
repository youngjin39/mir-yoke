//! Content snapshots for an explicitly targeted project, mirroring cli/_changes.py.
#![forbid(unsafe_code)]
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io;
use std::path::Path;

const EXCLUDED_DIRS: &[&str] = &[".git", ".pytest_cache", ".venv", "__pycache__"];

pub fn snapshot_project(root: &Path) -> io::Result<BTreeMap<String, String>> {
    fn visit(root: &Path, dir: &Path, snapshot: &mut BTreeMap<String, String>) -> io::Result<()> {
        for entry in fs::read_dir(dir)? {
            let path = entry?.path();
            if EXCLUDED_DIRS
                .iter()
                .any(|name| path.file_name() == Some(name.as_ref()))
            {
                continue;
            }
            let relative = path.strip_prefix(root).map_err(io::Error::other)?;
            let key = relative
                .to_str()
                .ok_or_else(|| io::Error::other("non-UTF-8 path"))?;
            let key = key.replace(std::path::MAIN_SEPARATOR, "/");
            let metadata = fs::symlink_metadata(&path)?;
            if metadata.file_type().is_symlink() {
                let target = fs::read_link(&path)?;
                let target = target
                    .to_str()
                    .ok_or_else(|| io::Error::other("non-UTF-8 link"))?;
                snapshot.insert(key, format!("symlink:{target}"));
            } else if metadata.is_file() {
                snapshot.insert(key, crate::digest::sha256(&fs::read(&path)?));
            } else if metadata.is_dir() {
                visit(root, &path, snapshot)?;
            }
        }
        Ok(())
    }
    let mut snapshot = BTreeMap::new();
    if root.is_dir() {
        visit(root, root, &mut snapshot)?;
    }
    Ok(snapshot)
}

pub fn changed_paths(
    before: &BTreeMap<String, String>,
    after: &BTreeMap<String, String>,
) -> Vec<String> {
    before
        .keys()
        .chain(after.keys())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .filter(|key| before.get(*key) != after.get(*key))
        .cloned()
        .collect()
}
