//! Argparse-compatible declared-relations CLI. Library only; memory is caller-supplied.
use super::memory::Output;
use crate::{
    executor_execute::repr,
    mir_core::relations::{self as r, Options},
};
use serde_json::{Value, json};
use std::path::Path;
const TOP: &str = "usage: mir relations [-h] {query,bundle} ...\n";
const CHOICES: &str = "implementation,impact,verification,dependencies";
// Same option-table parsing pattern as mir_cli::memory (not a shared parser).
const OPTIONS: &[(&str, Option<&str>)] = &[
    ("--help", None),
    ("--purpose", Some("PURPOSE")),
    ("--root", Some("ROOT")),
    ("--graph", Some("GRAPH")),
    ("--memory", None),
    ("--depth", Some("DEPTH")),
    ("--max-edges", Some("MAX_EDGES")),
    ("--max-bytes", Some("MAX_BYTES")),
    ("--json", None),
];
fn usage(command: &str) -> String {
    if command.is_empty() {
        return TOP.into();
    }
    let pad = " ".repeat(22 + command.len());
    let anchor = if command == "query" {
        "anchor"
    } else {
        "anchors [anchors ...]"
    };
    format!(
        "usage: mir relations {command} [-h] --purpose\n{pad}{{{CHOICES}}}\n\
{pad}[--root ROOT] [--graph GRAPH | --memory]\n\
{pad}[--depth DEPTH] [--max-edges MAX_EDGES]\n\
{pad}[--max-bytes MAX_BYTES] [--json]\n{pad}{anchor}\n"
    )
}
fn diag(command: &str, message: &str) -> Output {
    let prog = format!(" {command}").trim_end().to_owned();
    (
        2,
        vec![],
        format!("{}mir relations{prog}: error: {message}\n", usage(command)).into_bytes(),
    )
}
fn help(command: &str) -> Output {
    let body = if command.is_empty() {
        "\npositional arguments:\n  {query,bundle}\n\noptions:\n  -h, --help      \
show this help message and exit\n"
            .into()
    } else {
        let anchor = if command == "query" {
            "anchor"
        } else {
            "anchors"
        };
        format!(
            "\npositional arguments:\n  {anchor}\n\noptions:\n  \
-h, --help            show this help message and exit\n  --purpose {{{CHOICES}}}\n  \
--root ROOT\n  --graph GRAPH\n  --memory              \
read only the canonical <root>/.mir/memory.db relation\n                        facts\n  \
--depth DEPTH         omit: dependencies=1; implementation, verification,\n                        \
and impact=3; an explicit value applies to every facet\n  --max-edges MAX_EDGES\n  \
--max-bytes MAX_BYTES\n  --json\n"
        )
    };
    (0, (usage(command) + &body).into_bytes(), vec![])
}
fn option_like(s: &str) -> bool {
    s.len() > 1 && s.starts_with('-') && s[1..].parse::<f64>().is_err()
}
/// `memory` is an explicit adapter boundary, never discovered or connected here.
pub fn main(
    argv: &[&str],
    memory: impl FnOnce(bool, &Value, &Value, &Options<'_>) -> r::Result<Value>,
) -> Output {
    let Some(&command) = argv.first() else {
        return diag("", "the following arguments are required: command");
    };
    if super::argparse::resolve(command, &["--help"])
        .ok()
        .flatten()
        == Some("--help")
    {
        if let Some((_, value)) = command.split_once('=') {
            return diag(
                "",
                &format!(
                    "argument -h/--help: ignored explicit argument {}",
                    repr(value)
                ),
            );
        }
        return help("");
    }
    if !matches!(command, "query" | "bundle") {
        return diag(
            "",
            &format!(
                "argument command: invalid choice: {} \
(choose from query, bundle)",
                repr(command)
            ),
        );
    }
    let err = |message: &str| diag(command, message);
    let (mut anchors, mut purposes, mut unknown) = (Vec::new(), Vec::new(), Vec::new());
    let (mut root, mut graph) = (".", r::DEFAULT_GRAPH);
    let (mut depth, mut max_edges, mut max_bytes) = (Value::Null, json!(16), json!(6000));
    let (mut mem, mut graph_seen, mut json_output, mut options) = (false, false, false, true);
    let mut i = 1;
    while let Some(&token) = argv.get(i) {
        i += 1;
        if options && token == "--" {
            options = false;
            continue;
        }
        if !options || !option_like(token) {
            anchors.push(token);
            continue;
        }
        let (_, explicit) = token
            .split_once('=')
            .map_or((token, None), |(a, b)| (a, Some(b)));
        let names: Vec<_> = OPTIONS.iter().map(|o| o.0).collect();
        let name = match super::argparse::resolve(token, &names) {
            Ok(Some(name)) => name,
            Ok(None) => {
                unknown.push(token);
                continue;
            }
            Err(message) => return err(&message),
        };
        let takes_value = OPTIONS.iter().any(|o| o.0 == name && o.1.is_some());
        let value = if takes_value {
            if let Some(v) = explicit {
                v
            } else {
                let Some(&v) = argv.get(i).filter(|v| !option_like(v)) else {
                    return err(&format!("argument {}: expected one argument", name));
                };
                i += 1;
                v
            }
        } else {
            if let Some(v) = explicit {
                return err(&format!(
                    "argument {}: ignored explicit argument {}",
                    if name == "--help" { "-h/--help" } else { name },
                    repr(v)
                ));
            }
            ""
        };
        match name {
            "--help" => return help(command),
            "--purpose" => {
                if !r::PURPOSES.contains(&value) {
                    return err(&format!(
                        "argument --purpose: invalid choice: {} (choose from {})",
                        repr(value),
                        CHOICES.replace(',', ", ")
                    ));
                }
                if command == "query" {
                    purposes.clear();
                }
                purposes.push(value);
            }
            "--root" => root = value,
            "--graph" => {
                if mem {
                    return err("argument --graph: not allowed with argument --memory");
                }
                graph = value;
                graph_seen = true;
            }
            "--memory" => {
                if graph_seen {
                    return err("argument --memory: not allowed with argument --graph");
                }
                mem = true;
            }
            "--json" => json_output = true,
            "--depth" | "--max-edges" | "--max-bytes" => {
                let Ok(n) = value.parse::<i64>() else {
                    return err(&format!(
                        "argument {}: invalid int value: {}",
                        name,
                        repr(value)
                    ));
                };
                match name {
                    "--depth" => depth = json!(n),
                    "--max-edges" => max_edges = json!(n),
                    _ => max_bytes = json!(n),
                }
            }
            _ => {}
        }
    }
    let mut missing = Vec::new();
    if anchors.is_empty() {
        missing.push(if command == "query" {
            "anchor"
        } else {
            "anchors"
        });
    }
    if purposes.is_empty() {
        missing.push("--purpose");
    }
    if !missing.is_empty() {
        return err(&format!(
            "the following arguments are required: {}",
            missing.join(", ")
        ));
    }
    if command == "query" && anchors.len() > 1 {
        unknown.extend(anchors.drain(1..));
    }
    if !unknown.is_empty() {
        return diag(
            "",
            &format!("unrecognized arguments: {}", unknown.join(" ")),
        );
    }
    let o = Options {
        root: Path::new(root),
        graph,
        depth,
        max_edges,
        max_bytes,
    };
    let bundled = command == "bundle";
    let result = if mem {
        memory(bundled, &json!(anchors), &json!(purposes), &o)
    } else if bundled {
        r::bundle_relations(&json!(anchors), &json!(purposes), &o)
    } else {
        r::query_relations(&json!(anchors[0]), purposes[0], &o)
    };
    let rendered = result.and_then(|v| {
        let n = o.max_bytes.as_u64().unwrap_or(0) as usize;
        if json_output {
            r::render_json(&v, n)
        } else if bundled {
            r::render_bundle_human(&v, n)
        } else {
            r::render_human(&v, n)
        }
    });
    match rendered {
        Ok(out) => (0, out.into_bytes(), vec![]),
        Err(e) => (2, vec![], format!("relations: {e}\n").into_bytes()),
    }
}
