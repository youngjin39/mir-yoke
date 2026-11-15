//! Library-only CLI ports; no dispatch or live caller.
#![forbid(unsafe_code)]
mod argparse;
pub mod context;
pub mod context_sync;
pub mod memory;
pub mod migrate;
pub mod policy;
pub mod relations;

pub mod r#loop;

pub mod changes;

pub mod adoption_native;
#[forbid(unsafe_code)]
pub mod bootstrap;
#[forbid(unsafe_code)]
pub mod bootstrap_adoption;
pub mod capability;
pub mod capability_manager;
pub mod project_hooks;

#[cfg(test)]
mod artifact_redirect_tests;
mod embedding_http;
