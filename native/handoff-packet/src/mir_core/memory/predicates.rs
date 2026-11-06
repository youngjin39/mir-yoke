//! Pure parity with memory/predicates.py; no live callers.
//! BORROWED-FROM: codenamev/claude_memory@d0e523cd06d6adeae4744d89736f79564d9db41d
//! db/migrations/014_canonicalize_predicates.rb#PredicateMap (MIT).
const _SEED: &[(&str, &str)] = &[
    ("use", "use"),
    ("uses", "use"),
    ("used", "use"),
    ("using", "use"),
    ("call", "call"),
    ("calls", "call"),
    ("called", "call"),
    ("calling", "call"),
    ("depend on", "depend_on"),
    ("depends on", "depend_on"),
    ("depended on", "depend_on"),
    ("depending on", "depend_on"),
    ("import", "import"),
    ("imports", "import"),
    ("imported", "import"),
    ("extend", "extend"),
    ("extends", "extend"),
    ("extended", "extend"),
    ("implement", "implement"),
    ("implements", "implement"),
    ("implemented", "implement"),
    ("reference", "reference"),
    ("references", "reference"),
    ("referenced", "reference"),
];
/// Immutable view of the Python seed, including identity aliases.
pub const PREDICATE_MAP: &[(&str, &str)] = _SEED;
pub fn canonicalize(predicate: &str) -> String {
    let lowered = predicate.to_lowercase();
    let key = lowered.trim_matches(crate::executor_brief_authority::python_space);
    PREDICATE_MAP
        .iter()
        .find(|(alias, _)| *alias == key)
        .map_or(key, |(_, value)| value)
        .to_owned()
}
