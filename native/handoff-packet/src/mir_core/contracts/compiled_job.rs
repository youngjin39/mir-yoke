//! Ordered field specs mirror the Python reference class.
use super::{Kind::*, route_decision::RouteDecision, task_spec::TaskSpec};
super::contract!(CompiledJob;
    ("spec", Model("TaskSpec", TaskSpec::fields), None, None, None),
    ("route", Model("RouteDecision", RouteDecision::fields), None, None, None),
    ("resolved_files", Dict(&String), None, None, None),
    ("required_tools", Tuple(&String), None, None, None),
    ("session_plan", Dict(&String), None, None, None),
    ("guides_plan", Dict(&Tuple(&String)), None, None, None),
    ("budget", Dict(&Int), None, None, None),
    ("workdir", String, None, None, None),
    ("role", String, None, None, None),
    ("session_uuid", String, None, None, None),
);
