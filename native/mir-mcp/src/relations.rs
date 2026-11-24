//! Selective relations over the MCP target guard.
#[path = "../../handoff-packet/src/relation_terms.rs"]
mod relation_terms;
#[path = "../../handoff-packet/src/relations_reader.rs"]
mod relations_reader;

use self::relations_reader::{
    DEFAULT_GRAPH, DEFAULT_MAX_EDGES, MAX_ANCHOR_CHARS, MAX_DEPTH, MAX_EDGES, Query, Reader,
    RelationsError,
};
use crate::{guard::Guard, handoff::CONTRACT, pagination, wire};
use serde_json::{Value, json};
use std::{cell::RefCell, path::PathBuf};

struct GuardReader<'a>(RefCell<&'a mut Guard>);

impl Reader for GuardReader<'_> {
    fn path(&self, path: &str, allow_missing: bool) -> relations_reader::Result<PathBuf> {
        self.0
            .borrow_mut()
            .path(path, allow_missing)
            .map_err(RelationsError::Code)
    }
    fn exists(&self, path: &str) -> relations_reader::Result<bool> {
        self.0
            .borrow_mut()
            .exists(path)
            .map_err(RelationsError::Code)
    }
    fn read(&self, path: &str) -> relations_reader::Result<Vec<u8>> {
        self.0.borrow_mut().read(path).map_err(RelationsError::Code)
    }
}

fn text(value: &Value, max: usize) -> bool {
    value
        .as_str()
        .is_some_and(|s| !s.is_empty() && s.len() <= max)
}

fn integer(value: &Value, max: usize) -> bool {
    value
        .as_u64()
        .is_some_and(|n| (1..=max as u64).contains(&n))
}

fn validate(args: &Value) -> Result<(), &'static str> {
    let object = args.as_object().ok_or("E_SCHEMA")?;
    if ["target_root", "anchor", "purpose"]
        .iter()
        .any(|key| !object.contains_key(*key))
    {
        return Err("E_SCHEMA");
    }
    for (key, value) in object {
        let valid = match key.as_str() {
            "target_root" | "graph" => text(value, 4096),
            "anchor" => text(value, MAX_ANCHOR_CHARS),
            "purpose" => value
                .as_str()
                .is_some_and(|p| relation_terms::PURPOSES.contains(&p)),
            "adapter" => value == "yaml",
            "depth" => integer(value, MAX_DEPTH),
            "max_edges" => integer(value, MAX_EDGES),
            "page_size" => integer(value, 64),
            "cursor" => text(value, 1024),
            _ => false,
        };
        if !valid {
            return Err("E_SCHEMA");
        }
    }
    Ok(())
}

pub fn execute(args: &Value) -> Result<Value, &'static str> {
    validate(args)?;
    let mut io = Guard::new(args["target_root"].as_str().ok_or("E_SCHEMA")?)?;
    if let Some(graph) = args["graph"].as_str() {
        io.path(graph, true)?;
    }
    wire::parse(CONTRACT)?;
    let default_max_edges = json!(DEFAULT_MAX_EDGES);
    let data = Query::new(
        &args["anchor"],
        &args["purpose"],
        &args["depth"],
        args.get("max_edges").unwrap_or(&default_max_edges),
    )
    .and_then(|query| {
        query.read(
            args["graph"].as_str().unwrap_or(DEFAULT_GRAPH),
            &GuardReader(RefCell::new(&mut io)),
        )
    })
    .map_err(|e| match e {
        RelationsError::Code(code) => code,
        RelationsError::Refusal { .. } => "E_FORMAT",
    })?;
    io.tick()?;
    wire::parse(&pagination::compact(&data)?)?;
    let mut bound = args.clone();
    bound
        .as_object_mut()
        .ok_or("E_SCHEMA")?
        .shift_remove("cursor");
    let binding = pagination::binding(
        "relations_query",
        io.root.to_str().ok_or("E_PATH")?,
        &bound,
        &Value::Object(io.sources),
        &Value::Object(io.source_digests),
        CONTRACT,
    )?;
    pagination::page_tool(
        data,
        args,
        &binding,
        None,
        io.profile_protections,
        &["edges", "notices", "resolved_anchors"],
        false,
    )
}
