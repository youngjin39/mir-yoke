//! cli/policy.py: thin adapter to the pinned native resolver. Library only.
use super::memory::Output;

const USAGE: &str =
    "usage: mir policy resolve --category CATEGORY [--repo-root PATH] [--format json|text]\n";
const UNAVAILABLE: &str =
    "[mir policy] pinned native policy resolver unavailable or incompatible; no routing result\n";

/// Mirrors policy.main(argv). `native_query` stands for entrypoint._native_query: it
/// receives the forwarded argv and returns the resolver exit code, or None when the
/// pinned resolver is unavailable or incompatible.
pub fn main(argv: &[&str], native_query: impl FnOnce(&[&str]) -> Option<i32>) -> Output {
    if let Some((&"resolve", rest)) = argv.split_first() {
        let forwarded: Vec<&str> = std::iter::once("policy-resolve")
            .chain(rest.iter().copied())
            .collect();
        return match native_query(&forwarded) {
            Some(code) => (code, vec![], vec![]),
            None => (2, vec![], UNAVAILABLE.as_bytes().to_vec()),
        };
    }
    if matches!(argv, ["--help"] | ["-h"]) {
        return (0, USAGE.as_bytes().to_vec(), vec![]);
    }
    (2, vec![], USAGE.as_bytes().to_vec())
}
