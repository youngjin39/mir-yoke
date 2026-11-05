//! Read-only own-project SessionStart. Caller selection stays with the shell.
use std::path::Path;

const HEADER: &str = "=== SESSION CONTEXT ===\n";
const FALLBACK: &str = "repository_profile: unavailable\nmandatory_safety: inspect repository-local instructions before mutation\nContext depth on demand: scripts/mir.sh context pull \"<query>\" (--history for archived/expired)\n\n";

/// Reproduce the shell's UTF-8 cap and command-substitution newline handling.
fn capped(body: &str) -> String {
    let output = if body.len() <= 10_239 {
        body.to_owned()
    } else {
        let mut end = 10_239 - 64;
        while !body.is_char_boundary(end) {
            end -= 1;
        }
        format!(
            "{}\n[mir] session-start context truncated at 10KB (F3 cap)\n",
            &body[..end]
        )
    };
    format!("{}\n", output.trim_end_matches('\n'))
}

pub fn run(project: &Path) -> String {
    let (state, code) = crate::bootstrap_state::evaluate(project);
    if code != 0 {
        // Unsupported native state inputs remain fail-closed, as an unavailable
        // shell bootstrap gate does; no receipt is inferred from a profile.
        let state = state["state"].as_str().unwrap_or("missing");
        return format!(
            "{HEADER}{}",
            crate::bootstrap_enforce::instructions(state, project)
        );
    }
    // File presence is retained solely because it chooses observable fallback
    // bytes in the frozen hook. Neither Python nor script contents are executed.
    let body = if project
        .join("scripts/build_session_upfront_context.py")
        .is_file()
    {
        format!("{HEADER}{}\n\n", crate::session_upfront::build(project))
    } else {
        format!("{HEADER}{FALLBACK}")
    };
    capped(&body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cap_matches_shell_threshold_and_utf8_boundary() {
        for length in [10_238, 10_239] {
            let input = "x".repeat(length);
            assert_eq!(capped(&input), format!("{input}\n"));
        }
        let input = format!("{}é{}", "x".repeat(10_174), "x".repeat(65));
        assert_eq!(
            capped(&input),
            format!(
                "{}\n[mir] session-start context truncated at 10KB (F3 cap)\n",
                "x".repeat(10_174)
            )
        );
        assert_eq!(capped("text\n\n"), "text\n");
    }
}
