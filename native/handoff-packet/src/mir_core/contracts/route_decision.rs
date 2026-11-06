//! Ordered field specs mirror the Python reference class.
use super::Kind::*;
super::contract!(RouteDecision;
    ("type", Nullable(&Literal(&["bugfix", "feature", "refactor", "security", "research", "unknown"])), None, None, None),
    ("mode", Literal(&["deterministic", "supervisor_needed"]), None, None, None),
    ("signals", Dict(&Bool), None, None, None),
    ("executor_provider", String, None, None, None),
    ("reviewer_provider", Nullable(&String), None, None, None),
);
