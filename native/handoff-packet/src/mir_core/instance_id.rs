//! Explicit inputs prevent ambient host reads. One resolver represents Python's
//! zero-argument lru_cache(maxsize=1); clear it before changing external files.
use crate::executor_local::Error;
use std::{fs, path::PathBuf};

#[derive(Debug)]
pub struct InstanceIdResolver {
    files: Vec<PathBuf>,
    node: String,
    migration: PathBuf,
    cached: Option<String>,
    hits: usize,
    misses: usize,
}
impl InstanceIdResolver {
    pub fn new(files: Vec<PathBuf>, node: String, migration: PathBuf) -> Self {
        Self {
            files,
            node,
            migration,
            cached: None,
            hits: 0,
            misses: 0,
        }
    }
    pub fn current_instance_id(&mut self) -> Result<String, Error> {
        if let Some(value) = &self.cached {
            self.hits += 1;
            return Ok(value.clone());
        }
        self.misses += 1;
        let mut resolved = None;
        for path in &self.files {
            // Python catches OSError, but UTF-8 decoding errors propagate.
            if let Ok(bytes) = fs::read(path) {
                let text = String::from_utf8(bytes).map_err(Error::Unicode)?;
                let value = text.trim_matches(crate::executor_brief_authority::python_space);
                if !value.is_empty() {
                    resolved = Some(value.to_owned());
                    break;
                }
            }
        }
        let value = resolved.unwrap_or_else(|| {
            let mut bytes = if self.node.is_empty() {
                b"unknown".to_vec()
            } else {
                self.node.as_bytes().to_vec()
            };
            bytes.extend(
                fs::read(&self.migration)
                    .unwrap_or_else(|_| b"mir-initial-schema-missing".to_vec()),
            );
            crate::digest::sha256(&bytes)
        });
        self.cached = Some(value.clone());
        Ok(value)
    }
    pub fn cache_clear(&mut self) {
        self.cached = None;
        self.hits = 0;
        self.misses = 0;
    }
    /// Python CacheInfo order: hits, misses, maxsize, currsize. Errors are not cached.
    pub fn cache_info(&self) -> (usize, usize, usize, usize) {
        (
            self.hits,
            self.misses,
            1,
            usize::from(self.cached.is_some()),
        )
    }
}
