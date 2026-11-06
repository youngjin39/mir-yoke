//! Library-only memory helpers and store; callers remain on the Python reference.
pub mod backends;
pub mod distill;
pub mod external_store;
pub mod predicates;
pub mod relation_facts;
pub mod sanitize;
pub mod store;
pub mod vector_index;
