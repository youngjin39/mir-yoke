//! Context header helpers only; no CLI dispatch or live caller.
#![forbid(unsafe_code)]
use crate::mir_core::context::profile_task_context::{
    ProfileTaskContext, ordered_python_str, python_str, string_list,
};
use serde_json::Value;
pub fn profile_context_lines(profile: &ProfileTaskContext) -> Vec<String> {
    let context = &profile.value;
    if context.is_null() {
        return Vec::new();
    }
    let repo = &context["repository"];
    let mut line = format!(
        "[repository] {} type={}",
        repo["slug"].as_str().unwrap_or("unknown"),
        repo["repository_type"].as_str().unwrap_or("unknown")
    );
    let purpose = python_str(repo.get("purpose").unwrap_or(&Value::String(String::new())))
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if !purpose.is_empty() {
        line.push_str(&format!(" purpose={purpose}"));
    }
    let mut lines = vec![line];
    let stack = string_list(&repo["technology_stack"]);
    if !stack.is_empty() {
        lines.push(format!("[repository-stack] {}", stack.join(", ")));
    }
    let safety = &context["safety"];
    for key in ["protected_paths", "generated_paths"] {
        let values = string_list(&safety[key]);
        if !values.is_empty() {
            lines.push(format!("[safety] {key}={}", values.join(", ")));
        }
    }
    for (section, values) in [
        ("preserve", &profile.preserve),
        ("boundaries", &profile.boundaries),
    ] {
        for (key, value) in values {
            // Python equality with False also excludes integer and floating zero.
            let skip = match value {
                toml::Value::String(text) => text.is_empty(),
                toml::Value::Array(items) => items.is_empty(),
                toml::Value::Boolean(flag) => !flag,
                toml::Value::Integer(number) => *number == 0,
                toml::Value::Float(number) => *number == 0.0,
                _ => false,
            };
            if skip {
                continue;
            }
            let rendered = if let toml::Value::Array(items) = value {
                items
                    .iter()
                    .map(ordered_python_str)
                    .collect::<Vec<_>>()
                    .join(", ")
            } else {
                ordered_python_str(value)
            };
            lines.push(format!("[safety] {section}.{key}={rendered}"));
        }
    }
    let mut gates = profile
        .gates
        .iter()
        .filter(|(_, value)| value.as_bool() == Some(true))
        .map(|(key, _)| key.as_str())
        .collect::<Vec<_>>();
    gates.sort_unstable();
    if !gates.is_empty() {
        lines.push(format!("[safety] enabled_gates={}", gates.join(", ")));
    }
    for item in context["selected_refs"].as_array().into_iter().flatten() {
        lines.push(format!(
            "[context-ref] {} {}",
            python_str(&item["kind"]),
            python_str(&item["path"])
        ));
    }
    let fresh = &context["freshness"];
    let mut line = format!(
        "[profile-freshness] state={} base={}",
        python_str(&fresh["state"]),
        python_str(&fresh["base_commit"])
    );
    let changed = string_list(&fresh["changed_selected"]);
    if !changed.is_empty() {
        line.push_str(&format!(" changed={}", changed.join(",")));
    }
    line.push_str(&format!(" reason={}", python_str(&fresh["reason"])));
    lines.push(line);
    if context["needs_investigation"] == true {
        lines.push(
            "[context-advisory] inspect only the selected or uncertain boundary before expanding"
                .into(),
        );
    }
    for warning in string_list(&context["warnings"]) {
        lines.push(format!("[context-advisory] {warning}"));
    }
    lines
}
pub fn profile_search_scopes(context: &Value) -> Value {
    if context.is_null() {
        return Value::Null;
    }
    let mut scopes = string_list(&context["task"]["target_paths"]);
    let has_targets = !scopes.is_empty();
    for item in context["selected_refs"].as_array().into_iter().flatten() {
        if has_targets
            && ["code_scope", "non_code_scope"].contains(&item["kind"].as_str().unwrap_or(""))
        {
            continue;
        }
        if let Some(p) = item["path"].as_str() {
            scopes.push(p.into());
        }
    }
    let mut compact = Vec::new();
    for scope in scopes {
        if !scope.is_empty() && !compact.contains(&scope) {
            compact.push(scope);
        }
    }
    serde_json::json!((!compact.is_empty()).then_some(compact))
}
