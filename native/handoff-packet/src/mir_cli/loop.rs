//! File-backed continuation cursor CLI, library only.
use crate::mir_core::conductor::dispatch_brief::{Error, atomic_write};
use crate::tools::{
    autonomous_loop::r#loop::trigger_circuit_breaker,
    plan_archive::archiver::{self, STEP_STATUS_VOCAB, Section},
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::Path};
pub const PLAN_PATH: &str = "tasks/plan.md";
pub const MARK_STATUSES: [&str; 5] = STEP_STATUS_VOCAB;
pub const DONE_STATUSES: [&str; 2] = ["DONE", "CLOSED"];
#[derive(Clone, Debug)]
pub struct PlanStep {
    pub step_id: u64,
    pub status: String,
    pub line: String,
    pub fields: BTreeMap<String, String>,
}
impl PlanStep {
    pub fn attempts(&self) -> i64 {
        self.fields
            .get("attempts")
            .and_then(|s| s.trim().parse().ok())
            .unwrap_or(0)
    }
    pub fn brief(&self) -> Option<&str> {
        self.fields.get("brief").map(String::as_str)
    }
    pub fn tdd_change_id(&self) -> Option<&str> {
        self.fields
            .get("tdd")?
            .rsplit_once('#')
            .map(|(s, _)| s)
            .filter(|s| !s.is_empty())
    }
    pub fn tdd_category(&self) -> Option<&str> {
        self.fields
            .get("tdd")?
            .rsplit_once('#')
            .map(|(_, s)| s)
            .filter(|s| !s.is_empty())
    }
}
#[derive(Clone, Debug)]
pub struct NextResult {
    pub status: &'static str,
    pub step_id: Option<u64>,
    pub brief: Option<String>,
    pub tdd_change_id: Option<String>,
    pub tdd_category: Option<String>,
    pub reason: Option<String>,
}
impl NextResult {
    pub fn as_dict(&self) -> Value {
        json!({"status":self.status, "step_id":self.step_id, "brief":self.brief,
            "tdd_change_id":self.tdd_change_id, "tdd_category":self.tdd_category,
            "reason":self.reason})
    }
}
fn result(status: &'static str, step: Option<&PlanStep>, reason: Option<&str>) -> NextResult {
    NextResult {
        status,
        step_id: step.map(|s| s.step_id),
        brief: step.and_then(PlanStep::brief).map(str::to_owned),
        tdd_change_id: step.and_then(PlanStep::tdd_change_id).map(str::to_owned),
        tdd_category: step.and_then(PlanStep::tdd_category).map(str::to_owned),
        reason: reason.map(str::to_owned),
    }
}
pub fn active_task_section(text: &str) -> Option<Section> {
    archiver::parse_sections(text)
        .into_iter()
        .find(|s| !s.heading.is_empty() && !s.heading.contains("Pinned Tracker Policies"))
}
pub fn parse_fields(line: &str) -> BTreeMap<String, String> {
    line.trim_end_matches(['\r', '\n'])
        .split('|')
        .skip(1)
        .filter_map(|part| {
            part.trim()
                .split_once('=')
                .map(|(k, v)| (k.trim().into(), v.trim().into()))
        })
        .collect()
}
pub fn parse_step_line(line: &str) -> Result<Option<PlanStep>, Error> {
    Ok(
        archiver::step_match(line)?.map(|(id, status, _, _)| PlanStep {
            step_id: id,
            status: status.into(),
            line: line.into(),
            fields: parse_fields(line),
        }),
    )
}
pub fn section_steps(section: &Section) -> Result<Vec<PlanStep>, Error> {
    let mut steps = Vec::new();
    for line in crate::lines(&section.content) {
        if let Some(step) = parse_step_line(line)? {
            steps.push(step);
        }
    }
    Ok(steps)
}
fn read_plan(path: &Path) -> Result<String, Error> {
    match fs::read_to_string(path) {
        Ok(s) => Ok(s.replace("\r\n", "\n").replace('\r', "\n")),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Err(Error::named(
            "FileNotFoundError",
            "[Errno 2] No such file or directory: 'tasks/plan.md'",
        )),
        Err(e) => Err(e.into()),
    }
}
pub fn next_step(path: &Path) -> Result<NextResult, Error> {
    let Some(section) = active_task_section(&read_plan(path)?) else {
        return Ok(result("BLOCKED", None, Some("no_active_section")));
    };
    let steps = section_steps(&section)?;
    if steps.is_empty() {
        return Ok(if archiver::heading_complete(&section.heading)? {
            result("COMPLETE", None, None)
        } else {
            result("BLOCKED", None, Some("no_machine_steps"))
        });
    }
    for step in &steps {
        if DONE_STATUSES.contains(&step.status.as_str()) {
            continue;
        }
        return Ok(match step.status.as_str() {
            "BLOCKED" => result(
                "BLOCKED",
                Some(step),
                Some(
                    trigger_circuit_breaker(&json!({"state":"open"}))
                        .map_or("step_blocked", |t| t.reason),
                ),
            ),
            "FAILED" => result(
                "FAILED",
                Some(step),
                Some(
                    step.fields
                        .get("reason")
                        .map(String::as_str)
                        .filter(|s| !s.is_empty())
                        .unwrap_or("operator_decision_required"),
                ),
            ),
            _ => result("STEP", Some(step), None),
        });
    }
    Ok(result("COMPLETE", None, None))
}
pub fn set_field(line: &str, key: &str, value: &str) -> String {
    let (body, newline) = if let Some(body) = line.strip_suffix("\r\n") {
        (body, "\r\n")
    } else if let Some(body) = line.strip_suffix('\n') {
        (body, "\n")
    } else {
        (line, "")
    };
    let mut parts: Vec<String> = body.split(" | ").map(str::to_owned).collect();
    let replacement = format!("{key}={value}");
    if let Some(part) = parts
        .iter_mut()
        .skip(1)
        .find(|s| s.starts_with(&format!("{key}=")))
    {
        *part = replacement;
    } else {
        parts.push(replacement);
    }
    parts.join(" | ") + newline
}
pub fn replace_status(line: &str, status: &str) -> Result<String, Error> {
    let (_, _, start, end) = archiver::step_match(line)?
        .ok_or_else(|| Error::named("LoopError", "line is not a machine step"))?;
    Ok(format!("{}{status}{}", &line[..start], &line[end..]))
}
pub fn rewrite_step_line(
    line: &str,
    status: &str,
    reason: Option<&str>,
) -> Result<(String, bool), Error> {
    let step = parse_step_line(line)?
        .ok_or_else(|| Error::named("LoopError", "line is not a machine step"))?;
    if status == "IN_PROGRESS" {
        if step.status == "IN_PROGRESS" {
            return Ok((line.into(), false));
        }
        if step.status != "TODO" {
            return Err(Error::named(
                "LoopError",
                format!(
                    "IN_PROGRESS compare-and-set requires current status TODO (got {})",
                    step.status
                ),
            ));
        }
    } else if DONE_STATUSES.contains(&step.status.as_str()) && status != step.status {
        return Err(Error::named(
            "LoopError",
            format!("refusing to rewrite completed step {}", step.step_id),
        ));
    }
    let mut updated = replace_status(line, status)?;
    if status == "FAILED" {
        updated = set_field(&updated, "attempts", &(step.attempts() + 1).to_string());
    }
    if let Some(reason) = reason.filter(|s| !s.is_empty()) {
        updated = set_field(&updated, "reason", reason);
    }
    let changed = updated != line;
    Ok((updated, changed))
}
pub fn mark_step(id: u64, status: &str, reason: Option<&str>, path: &Path) -> Result<Value, Error> {
    if !MARK_STATUSES.contains(&status) {
        return Err(Error::named(
            "LoopError",
            format!("unsupported status: {status}"),
        ));
    }
    let text = read_plan(path)?;
    let mut lines: Vec<String> = text.split_inclusive('\n').map(str::to_owned).collect();
    for index in 0..lines.len() {
        let Some(step) = parse_step_line(&lines[index])? else {
            continue;
        };
        if step.step_id != id {
            continue;
        }
        let (updated, changed) = rewrite_step_line(&lines[index], status, reason)?;
        if changed {
            lines[index] = updated;
            atomic_write(path, &lines.concat(), |_, _| Ok(()))?;
        }
        return Ok(
            json!({"status":"OK", "step_id":id, "previous_status":step.status,
            "new_status":status, "changed":changed}),
        );
    }
    Err(Error::named("LoopError", format!("step not found: {id}")))
}
pub fn json_text(value: &Value) -> String {
    // Python json.dumps(sort_keys=True), with default comma/colon spacing.
    match value {
        Value::Object(map) => format!(
            "{{{}}}",
            map.iter()
                .map(|(k, v)| format!("{}: {}", json!(k), json_text(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(json_text).collect::<Vec<_>>().join(", ")
        ),
        _ => value.to_string(),
    }
}
pub fn print_next(result: &NextResult, as_json: bool) -> String {
    if as_json {
        return json_text(&result.as_dict()) + "\n";
    }
    let detail = result
        .reason
        .as_deref()
        .filter(|s| !s.is_empty())
        .or(result.brief.as_deref())
        .unwrap_or("");
    format!(
        "{} step_id={} {detail}",
        result.status,
        result.step_id.map_or("None".into(), |s| s.to_string())
    )
    .trim_end()
    .to_owned()
        + "\n"
}
const USAGE: &str = "usage: mir loop [-h] {next,mark} ...\n";
const NEXT_USAGE: &str = "usage: mir loop next [-h] [--json]\n";
const MARK_USAGE: &str = concat!(
    "usage: mir loop mark [-h] --step STEP --status\n",
    "                     {TODO,IN_PROGRESS,DONE,FAILED,BLOCKED} [--reason REASON]\n",
);
const HELP: &str = concat!(
    "\npositional arguments:\n  {next,mark}\n",
    "    next       read the next plan cursor step\n",
    "    mark       update one plan cursor step\n",
    "\noptions:\n  -h, --help   show this help message and exit\n",
);
const NEXT_HELP: &str = "\noptions:\n  -h, --help  show this help message and exit\n  --json\n";
const MARK_HELP: &str = concat!(
    "\noptions:\n  -h, --help            show this help message and exit\n",
    "  --step STEP\n  --status {TODO,IN_PROGRESS,DONE,FAILED,BLOCKED}\n  --reason REASON\n",
);
#[derive(Debug)]
pub struct CliResult {
    /// Number for normal returns, [SystemExit, code] for argparse exits.
    pub status: Value,
    pub stdout: String,
    pub stderr: String,
}
fn parser_error(mark: bool, message: &str) -> CliResult {
    let (usage, prog) = if mark {
        (MARK_USAGE, "mir loop mark")
    } else {
        (USAGE, "mir loop")
    };
    CliResult {
        status: json!(["SystemExit", 2]),
        stdout: String::new(),
        stderr: format!("{usage}{prog}: error: {message}\n"),
    }
}
/// Explicit cwd replaces process-wide chdir so concurrent tests are safe.
pub fn main(argv: &[&str], cwd: &Path) -> Result<CliResult, Error> {
    let command = argv.first().copied().unwrap_or("");
    if matches!(command, "--help" | "-h") {
        return Ok(CliResult {
            status: json!(["SystemExit", 0]),
            stdout: USAGE.to_owned() + HELP,
            stderr: String::new(),
        });
    }
    if command.is_empty() {
        return Ok(parser_error(
            false,
            "the following arguments are required: command",
        ));
    }
    if !["next", "mark"].contains(&command) {
        return Ok(parser_error(
            false,
            &format!(
                "argument command: invalid choice: {} (choose from next, mark)",
                crate::executor_execute::repr(command)
            ),
        ));
    }
    let mark = command == "mark";
    let mut id = None;
    let mut status = None;
    let mut reason = None;
    let mut as_json = false;
    let mut unknown = Vec::new();
    let mut index = 1;
    while index < argv.len() {
        let arg = argv[index];
        if matches!(arg, "--help" | "-h") {
            let (usage, help) = if mark {
                (MARK_USAGE, MARK_HELP)
            } else {
                (NEXT_USAGE, NEXT_HELP)
            };
            return Ok(CliResult {
                status: json!(["SystemExit", 0]),
                stdout: usage.to_owned() + help,
                stderr: String::new(),
            });
        }
        if !mark && arg == "--json" {
            as_json = true;
        } else if mark && ["--step", "--status", "--reason"].contains(&arg) {
            index += 1;
            let Some(value) = argv.get(index).copied() else {
                return Ok(parser_error(
                    true,
                    &format!("argument {arg}: expected one argument"),
                ));
            };
            match arg {
                "--step" => {
                    let Ok(value_id) = value.parse::<u64>() else {
                        return Ok(parser_error(
                            true,
                            &format!(
                                "argument --step: invalid int value: {}",
                                crate::executor_execute::repr(value)
                            ),
                        ));
                    };
                    id = Some(value_id);
                }
                "--status" => {
                    if !MARK_STATUSES.contains(&value) {
                        return Ok(parser_error(
                            true,
                            &format!(
                                "argument --status: invalid choice: {} (choose from {})",
                                crate::executor_execute::repr(value),
                                MARK_STATUSES.join(", ")
                            ),
                        ));
                    }
                    status = Some(value);
                }
                "--reason" => reason = Some(value),
                _ => (),
            }
        } else {
            unknown.push(arg);
        }
        index += 1;
    }
    if mark && (id.is_none() || status.is_none()) {
        let missing = [("--step", id.is_none()), ("--status", status.is_none())]
            .into_iter()
            .filter(|(_, missing)| *missing)
            .map(|(name, _)| name)
            .collect::<Vec<_>>()
            .join(", ");
        return Ok(parser_error(
            true,
            &format!("the following arguments are required: {missing}"),
        ));
    }
    if !unknown.is_empty() {
        return Ok(parser_error(
            false,
            &format!("unrecognized arguments: {}", unknown.join(" ")),
        ));
    }
    let path = cwd.join(PLAN_PATH);
    let output = if mark {
        mark_step(id.unwrap_or(0), status.unwrap_or(""), reason, &path)
            .map(|v| json_text(&v) + "\n")
    } else {
        next_step(&path).map(|r| print_next(&r, as_json))
    };
    match output {
        Ok(stdout) => Ok(CliResult {
            status: json!(0),
            stdout,
            stderr: String::new(),
        }),
        Err(e) if e.class == "LoopError" => Ok(CliResult {
            status: json!(1),
            stdout: String::new(),
            stderr: format!("[mir loop] {e}\n"),
        }),
        Err(e) => Err(e),
    }
}
