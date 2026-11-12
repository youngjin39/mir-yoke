//! Configuration and memory defaults for the bootstrap coordinator's library host.
use super::{Error, memory};
use crate::mir_core::{config::loader, memory::external_store::ExternalStore};
use serde_json::Value;
use std::path::{Path, PathBuf};

fn config_error(error: loader::ConfigLoadError) -> Error {
    Error::new(error.class, error.message)
}

pub(super) fn load_config(root: &Path, home: &Path) -> Result<Value, Error> {
    loader::load_config(Some(root), home, root)
        .map(|config| config.to_dict())
        .map_err(config_error)
}

pub(super) fn resolve_memory_db(root: &Path, cfg: &Value, home: &Path) -> Result<PathBuf, Error> {
    let config = loader::ResolvedConfig::from_dict(cfg)
        .map_err(|e| config_error(loader::validation_error("ResolvedConfig", cfg, e)))?;
    loader::resolve_memory_db(root, &config, home).map_err(config_error)
}

pub(super) fn abspath(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for part in path.components() {
        match part {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                normalized.pop();
            }
            part => normalized.push(part.as_os_str()),
        }
    }
    normalized
}

pub(super) fn context_main(
    root: &Path,
    db: &Path,
    home: &Path,
    now: &str,
) -> Result<(i32, String), Error> {
    let cfg = load_config(root, home)?;
    let connection = memory::connect(db)?;
    let clock = || now.to_owned();
    let store =
        ExternalStore::new(&connection, &clock).map_err(|e| Error::new(e.kind, e.message))?;
    crate::mir_cli::context::do_sync(&store, &cfg, root, home)
        .map_err(|e| Error::new(e.kind, e.message))
}

pub(super) fn run_doctor(root: &Path, db: &Path, home: &Path) -> Result<(i32, Value), Error> {
    crate::mir_cli::memory::run_doctor(root, Some(db), home, std::time::SystemTime::now, |path| {
        crate::mir_core::memory::store::connect(
            path,
            crate::mir_core::memory::store::ConnectOptions {
                timeout: None,
                vec_loading: crate::mir_core::memory::store::VecLoading::Bundled,
            },
        )
    })
    .map_err(|e| Error::new(e.python_class(), e.to_string()))
}
