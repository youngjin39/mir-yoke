//! The configuration validation reached by bootstrap's native lock evidence.
//! Only the plugins projection is returned; every Python load-time check still runs.
#![forbid(unsafe_code)]
use super::authored::{json_text, read_text};
use super::{Error, PROFILE_CHOICES};
use crate::executor_execute::repr;
use crate::mir_cli::bootstrap_adoption::wire;
use crate::plugin_scripts::ontology_check::Doc;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

fn error(message: impl Into<String>) -> Error {
    Error::new("CapabilityConfigError", message)
}
fn require(condition: bool, message: impl Into<String>) -> Result<(), Error> {
    if condition {
        Ok(())
    } else {
        Err(error(message))
    }
}
fn keys(value: &Value) -> BTreeSet<&str> {
    value
        .as_object()
        .into_iter()
        .flat_map(|m| m.keys().map(String::as_str))
        .collect()
}
fn exact(value: &Value, expected: &[&str]) -> bool {
    value.is_object() && keys(value) == expected.iter().copied().collect()
}
fn unique(values: &[Value]) -> bool {
    values
        .iter()
        .enumerate()
        .all(|(i, v)| !values[..i].contains(v))
}
fn list(value: &Value) -> &[Value] {
    value.as_array().map_or(&[], Vec::as_slice)
}
fn nonempty_list(value: &Value) -> bool {
    value.as_array().is_some_and(|a| !a.is_empty())
}
fn nonempty_object(value: &Value) -> bool {
    value.as_object().is_some_and(|m| !m.is_empty())
}
fn name(value: &str) -> bool {
    !value.is_empty()
        && value.split('-').all(|p| {
            !p.is_empty()
                && p.bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
        })
}
fn path(value: &Value, prefix: Option<&str>) -> Result<String, Error> {
    let text = value
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| error("capability paths must be non-empty strings"))?;
    let drive = text.as_bytes().get(1) == Some(&b':') && text.as_bytes()[0].is_ascii_alphabetic();
    if text.contains('\\') || drive || text.starts_with('/') || text.split('/').any(|p| p == "..") {
        return Err(error(format!("unsafe capability path: {}", repr(text))));
    }
    let parts: Vec<_> = text
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    let canonical = if parts.is_empty() {
        ".".into()
    } else {
        parts.join("/")
    };
    if canonical != text {
        return Err(error(format!(
            "non-canonical capability path: {}",
            repr(text)
        )));
    }
    if let Some(prefix) = prefix
        && parts.first().copied() != Some(prefix)
    {
        return Err(error(format!(
            "capability path must stay under {prefix}/: {}",
            repr(text)
        )));
    }
    Ok(text.into())
}
fn strings(value: &Value, label: &str) -> Result<BTreeMap<String, String>, Error> {
    let map = value
        .as_object()
        .ok_or_else(|| error(format!("{label} must be an object")))?;
    map.iter()
        .map(|(k, v)| {
            v.as_str()
                .map(|v| (k.clone(), v.into()))
                .ok_or_else(|| error(format!("{label} must map strings to strings")))
        })
        .collect()
}
fn url(value: &Value) -> Result<(), Error> {
    let raw = value
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| error("source.url must be a non-empty HTTPS URL"))?;
    // urlsplit strips leading ASCII controls/spaces and removes tabs/newlines anywhere.
    let raw = raw
        .trim_start_matches(|c: char| c <= ' ')
        .replace(['\t', '\r', '\n'], "");
    let Some((scheme, tail)) = raw.split_once(':') else {
        return Err(error("source.url must use HTTPS"));
    };
    let authority = tail
        .strip_prefix("//")
        .unwrap_or("")
        .split(['/', '?', '#'])
        .next()
        .unwrap_or("");
    let host = authority.rsplit('@').next().unwrap_or("");
    if host.contains('[') != host.contains(']') {
        return Err(Error::new("ValueError", "Invalid IPv6 URL"));
    }
    require(
        scheme.eq_ignore_ascii_case("https") && !host.split(':').next().unwrap_or("").is_empty(),
        "source.url must use HTTPS",
    )?;
    require(
        !authority.contains('@'),
        "source.url must not contain credentials",
    )?;
    let query = raw
        .split_once('?')
        .map(|(_, q)| q.split('#').next().unwrap_or(""));
    let fragment = raw.split_once('#').map(|(_, f)| f);
    require(
        query.is_none_or(str::is_empty) && fragment.is_none_or(str::is_empty),
        "source.url must not contain a query or fragment",
    )
}
fn reference(value: &Value) -> Result<(), Error> {
    let valid = value.as_str().is_some_and(|s| {
        s.as_bytes().first().is_some_and(u8::is_ascii_alphanumeric)
            && s.bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._/-".contains(&b))
            && !s.ends_with(['.', '/'])
            && !s.contains("..")
            && !s.contains("//")
    });
    require(valid, "source.ref is not a safe branch or tag name")
}
fn component_policy(version: u64) -> Value {
    json!({"admitted_package_kinds": if version == 5 { vec!["skills","skills-hooks","mcp-stdio"] }
        else if version == 4 { vec!["skills","skills-hooks"] } else { vec!["skills"] },
        "reserved_active_package_kinds":if version >= 4 { vec!["mcp"] }
            else { vec!["hooks","mcp"] },
        "active_package_shape":"separate-named-package",
        "active_package_admission":"dedicated-validator-and-fresh-digest-acknowledgement",
        "project_integration":"target-local-only",
        "forbidden_provider_components":["agents","commands","apps","scripts","permissions",
            "runtime-policy"]})
}
fn integrations() -> Value {
    json!({"hooks":{"source":"config/project-hooks.json","claude_target":".claude/settings.json",
        "codex_target":".codex/hooks.json","delivery":"target-local-generated",
        "plugin_package_kind":"reserved"},
        "mcp_servers":{"activation_source":".mcp.json","reference":".mcp.json.example",
        "codex_target":".codex/config.toml","delivery":"target-local-opt-in-generated",
        "plugin_package_kind":"reserved"}})
}
fn mcp_metadata() -> Value {
    json!({"path":"plugins/mir-mcp","package_kind":"mcp-stdio",
        "files":[".claude-plugin/plugin.json",".codex-plugin/plugin.json",".mcp.claude.json",
        ".mcp.codex.json","mir_mcp.py","ontology/references/common-contract.json",
        "ontology/scripts/ontology_check.py","shared/relations_query.py"],"server":"mir-mcp",
        "tools":["ontology_validate","ontology_lookup","ontology_impact","handoff_pins",
        "relations_query"]})
}
pub(super) fn plugins(pathname: &Path) -> Result<Value, Error> {
    let raw = json_text(pathname).map_err(|e| {
        if e.class == "UnicodeDecodeError" {
            return e;
        }
        let action = if e.class == "JSONDecodeError" {
            "invalid capability source JSON"
        } else {
            "cannot read capability source"
        };
        error(format!("{action}: {}", wire(pathname)))
    })?;
    let version = if raw["schema_version"] == true {
        Some(1)
    } else {
        raw["schema_version"]
            .as_f64()
            .filter(|v| v.fract() == 0.0)
            .map(|v| v as u64)
    };
    let version = version.filter(|v| (1..=5).contains(v));
    require(
        raw.is_object() && version.is_some(),
        "capability source schema_version must be 1, 2, 3, 4, or 5",
    )?;
    let version = version.unwrap_or(0);
    require(raw["source"].is_object(), "source must be an object")?;
    url(&raw["source"]["url"])?;
    reference(&raw["source"]["ref"])?;
    require(
        nonempty_object(&raw["plugins"]),
        "plugins must be a non-empty object",
    )?;
    // Keep validation finding order equal to the source's insertion order.
    let ordered: Doc =
        serde_json::from_str(&read_text(pathname)?).map_err(|e| error(e.to_string()))?;
    let mut plugins = serde_json::Map::new();
    let mut skills = BTreeMap::<String, Vec<Value>>::new();
    let mut active = BTreeSet::new();
    for (plugin, metadata) in ordered.get("plugins").items() {
        let metadata = metadata.value();
        require(
            name(plugin),
            format!("invalid plugin name: {}", repr(plugin)),
        )?;
        require(
            metadata.is_object(),
            format!("plugin {} metadata must be an object", repr(plugin)),
        )?;
        let kind = if version == 1 {
            "skills"
        } else {
            metadata["package_kind"].as_str().unwrap_or("")
        };
        if version != 1 {
            let admitted = kind == "skills"
                || (version >= 4 && kind == "skills-hooks")
                || (version == 5 && kind == "mcp-stdio");
            require(
                admitted,
                format!(
                    "plugin {} package_kind is not admitted: {}",
                    repr(plugin),
                    crate::executor_brief_render::python_value_repr(&metadata["package_kind"])
                ),
            )?;
        }
        if kind == "mcp-stdio" {
            require(
                plugin == "mir-mcp" && metadata == mcp_metadata(),
                "mcp-stdio requires the exact mir-mcp metadata",
            )?;
            plugins.insert(plugin.clone(), metadata["path"].clone());
            active.insert(plugin.clone());
            continue;
        }
        require(
            plugin != "mir-mcp",
            "mir-mcp requires schema 5 and package_kind mcp-stdio",
        )?;
        let mut expected = vec!["path", "skills"];
        if version != 1 {
            expected.push("package_kind");
        }
        if kind == "skills-hooks" {
            expected.push("hooks");
        }
        expected.sort();
        require(
            exact(&metadata, &expected),
            format!(
                "plugin {} metadata must contain only {}",
                repr(plugin),
                expected.join(", ")
            ),
        )?;
        let plugin_path = path(&metadata["path"], Some("plugins"))?;
        require(
            plugin_path.rsplit('/').next() == Some(plugin),
            format!("plugin path/name mismatch for {}", repr(plugin)),
        )?;
        plugins.insert(plugin.clone(), json!(plugin_path));
        let selected = &metadata["skills"];
        require(
            nonempty_list(selected),
            format!("plugin {} skills must be a non-empty array", repr(plugin)),
        )?;
        require(
            list(selected).iter().all(|s| s.as_str().is_some_and(name)),
            format!("plugin {} contains an invalid skill name", repr(plugin)),
        )?;
        require(
            unique(list(selected)),
            format!("plugin {} contains duplicate skills", repr(plugin)),
        )?;
        skills.insert(plugin.clone(), list(selected).to_vec());
        if kind == "skills-hooks" {
            require(
                metadata["hooks"]
                    == json!(["SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"]),
                format!(
                    "active hook plugin {} must declare exactly SessionStart, UserPromptSubmit, \
                    PreToolUse, Stop",
                    repr(plugin)
                ),
            )?;
            active.insert(plugin.clone());
        }
    }
    let all: Vec<_> = skills.values().flatten().cloned().collect();
    require(
        unique(&all),
        "a common skill is declared by more than one plugin",
    )?;
    if version >= 3 {
        require(
            raw["plugin_component_policy"] == component_policy(version),
            "plugin_component_policy must preserve the canonical skills-only admission boundary",
        )?;
    }
    if version == 1 {
        require(
            raw["plugin_component_policy"].is_null(),
            "schema_version 1 cannot declare plugin_component_policy",
        )?;
    }
    if version >= 4 {
        let empty = json!({});
        let ack = raw
            .get("active_package_digest_acknowledgements")
            .unwrap_or(&empty);
        require(
            ack.is_object() && keys(ack).iter().all(|k| active.contains(*k)),
            "active package digest acknowledgement must name only active packages",
        )?;
        for (name, digest) in ordered
            .get("active_package_digest_acknowledgements")
            .items()
        {
            let digest = digest.value();
            require(
                digest.as_str().is_some_and(|s| {
                    s.len() == 64
                        && s.bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                }),
                format!(
                    "active package {} has an invalid digest acknowledgement",
                    repr(name)
                ),
            )?;
        }
    } else {
        require(
            raw.get("active_package_digest_acknowledgements").is_none(),
            "only schema_version 4+ can declare active package digest acknowledgements",
        )?;
    }
    let profiles = &raw["profiles"];
    require(profiles.is_object(), "profiles must be an object")?;
    let aliases = strings(
        profiles.get("aliases").unwrap_or(&json!({})),
        "profiles.aliases",
    )?;
    let packs = &profiles["packs"];
    require(
        nonempty_object(packs),
        "profiles.packs must be a non-empty object",
    )?;
    require(
        exact(packs, &PROFILE_CHOICES),
        "canonical profiles must be exactly code_app, \
        hybrid_pipeline, infra_runtime, and content_workspace",
    )?;
    let agents = &raw["agents"];
    let expected = if version >= 4 {
        vec!["allowlist", "provider_local"]
    } else {
        vec!["allowlist"]
    };
    require(
        exact(agents, &expected) && agents["allowlist"].is_array(),
        "agents.allowlist must be an array",
    )?;
    let mut agent_paths = vec![];
    for agent in list(&agents["allowlist"]) {
        let agent = path(agent, Some(".claude"))?;
        let parts: Vec<_> = agent.split('/').collect();
        require(
            parts.len() == 3 && parts[1] == "agents" && parts[2].ends_with(".md"),
            format!("agent path is outside .claude/agents: {}", repr(&agent)),
        )?;
        agent_paths.push(json!(agent));
    }
    require(unique(&agent_paths), "agents.allowlist contains duplicates")?;
    let mut local = vec![];
    if version >= 4 {
        require(
            agents["provider_local"].is_array(),
            "agents.provider_local must be an array",
        )?;
        for agent in list(&agents["provider_local"]) {
            local.push(json!(path(agent, Some(".claude"))?));
        }
        require(
            unique(&local) && local.iter().all(|a| agent_paths.contains(a)),
            "agents.provider_local must be a unique subset of agents.allowlist",
        )?;
    }
    let mut commands = BTreeMap::new();
    if version >= 3 {
        let raw_commands = &raw["commands"];
        require(
            exact(raw_commands, &["delivery", "allowlist"]),
            "commands must contain only delivery and allowlist",
        )?;
        require(
            raw_commands["delivery"] == "claude-project-file-codex-plugin-skill",
            "commands.delivery has drifted",
        )?;
        require(
            nonempty_object(&raw_commands["allowlist"]),
            "commands.allowlist must be a non-empty object",
        )?;
        let known: BTreeSet<_> = skills
            .iter()
            .flat_map(|(plugin, skills)| {
                skills
                    .iter()
                    .filter_map(Value::as_str)
                    .map(move |skill| format!("{plugin}:{skill}"))
            })
            .collect();
        for (command, skill) in ordered.get("commands").get("allowlist").items() {
            let command_path = path(&json!(command), Some(".claude"))
                .map_err(|_| error(format!("unsafe command path: {}", repr(command))))?;
            let parts: Vec<_> = command_path.split('/').collect();
            require(
                parts.len() == 3 && parts[1] == "commands" && parts[2].ends_with(".md"),
                format!(
                    "command path is outside .claude/commands: {}",
                    repr(&command_path)
                ),
            )?;
            require(
                skill.text().is_some_and(|s| known.contains(s)),
                format!(
                    "command {} references an unknown skill",
                    repr(&command_path)
                ),
            )?;
            commands.insert(command_path, skill.value());
        }
        require(
            raw["project_integrations"] == integrations(),
            "project_integrations must preserve target-local hook and MCP ownership",
        )?;
    } else {
        require(
            raw.get("commands").is_none() && raw.get("project_integrations").is_none(),
            "schema_version 1 or 2 cannot declare commands or project_integrations",
        )?;
    }
    let mut inventories = vec![];
    for (profile, pack) in ordered.get("profiles").get("packs").items() {
        let pack = pack.value();
        require(
            pack.is_object(),
            format!("invalid profile pack: {}", repr(profile)),
        )?;
        if version == 1 {
            require(
                exact(&pack, &["plugins", "agents"]),
                format!(
                    "schema_version 1 profile {} must contain only plugins and agents",
                    repr(profile)
                ),
            )?;
        }
        let members = &pack["plugins"];
        let selected_agents = &pack["agents"];
        let empty = json!([]);
        let selected_commands = pack.get("commands").unwrap_or(&empty);
        require(
            nonempty_list(members),
            format!(
                "profile {} plugins must be a non-empty array",
                repr(profile)
            ),
        )?;
        require(
            !list(members).contains(&json!("mir-mcp")),
            "default Profiles cannot select mir-mcp; use explicit opt-in",
        )?;
        require(
            nonempty_list(selected_agents),
            format!("profile {} agents must be a non-empty array", repr(profile)),
        )?;
        if version >= 3 {
            require(
                nonempty_list(selected_commands),
                format!(
                    "profile {} commands must be a non-empty array",
                    repr(profile)
                ),
            )?;
        }
        if version == 2 {
            require(
                !super::content::truthy(selected_commands),
                format!(
                    "schema_version 2 profile {} cannot declare commands",
                    repr(profile)
                ),
            )?;
        }
        require(
            list(members)
                .iter()
                .all(|m| m.as_str().is_some_and(|s| plugins.contains_key(s))),
            format!("profile {} references an unknown plugin", repr(profile)),
        )?;
        require(
            unique(list(members)) && list(members).contains(&json!("mir-core")),
            format!(
                "profile {} must contain mir-core exactly once and no duplicates",
                repr(profile)
            ),
        )?;
        require(
            list(selected_agents)
                .iter()
                .all(|a| agent_paths.contains(a)),
            format!("profile {} references an unknown agent", repr(profile)),
        )?;
        require(
            unique(list(selected_agents)),
            format!("profile {} contains duplicate agents", repr(profile)),
        )?;
        require(
            list(selected_commands)
                .iter()
                .all(|c| c.as_str().is_some_and(|s| commands.contains_key(s))),
            format!("profile {} references an unknown command", repr(profile)),
        )?;
        require(
            unique(list(selected_commands)),
            format!("profile {} contains duplicate commands", repr(profile)),
        )?;
        let selected_skills: BTreeSet<_> = list(members)
            .iter()
            .filter_map(Value::as_str)
            .flat_map(|p| {
                skills
                    .get(p)
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(move |s| json!(format!("{p}:{s}")))
            })
            .map(|v| v.to_string())
            .collect();
        require(
            list(selected_commands).iter().all(|c| {
                c.as_str()
                    .and_then(|s| commands.get(s))
                    .is_some_and(|s| selected_skills.contains(&s.to_string()))
            }),
            format!(
                "profile {} command maps outside its selected plugin skills",
                repr(profile)
            ),
        )?;
        let inventory = json!([members, selected_agents, selected_commands]);
        require(
            !inventories.contains(&inventory),
            format!("profile {} duplicates another inventory", repr(profile)),
        )?;
        inventories.push(inventory);
    }
    require(
        !inventories
            .iter()
            .any(|i| list(&i[1]).iter().any(|a| local.contains(a))),
        "agents.provider_local entries cannot belong to a distributable profile",
    )?;
    let required = &raw["required_project_paths"];
    require(
        nonempty_list(required),
        "required_project_paths must be a non-empty array",
    )?;
    let paths: Vec<_> = list(required)
        .iter()
        .map(|v| path(v, None).map(Value::String))
        .collect::<Result<_, _>>()?;
    require(unique(&paths), "required_project_paths contains duplicates")?;
    if version >= 3 {
        require(
            [
                "config/project-hooks.json",
                ".claude/settings.json",
                ".codex/hooks.json",
                ".codex/config.toml",
            ]
            .iter()
            .all(|p| paths.contains(&json!(p))),
            "required_project_paths must include managed hook and MCP projections",
        )?;
    }
    let runtime = &raw["runtime_support"];
    let policy = &raw["policy"];
    require(
        runtime.is_object() && policy.is_object(),
        "runtime_support and policy must be objects",
    )?;
    require(
        runtime["supported"] == json!(["claude-code", "codex-cli", "codex-desktop"]),
        "runtime_support.supported has drifted",
    )?;
    require(
        runtime["unsupported"].is_object()
            && runtime["unsupported"].get("codex-ide-extension").is_some(),
        "Codex IDE extension boundary must be explicit",
    )?;
    let runtimes = &policy["activation_required_runtimes"];
    require(
        nonempty_list(runtimes)
            && unique(list(runtimes))
            && list(runtimes)
                .iter()
                .all(|r| r == "claude-code" || r == "codex-cli-desktop"),
        "policy.activation_required_runtimes must contain unique supported runtimes",
    )?;
    if version >= 3 {
        require(
            *runtimes == json!(["claude-code", "codex-cli-desktop"]),
            "schema 3+ policy.activation_required_runtimes must require claude-code and \
                codex-cli-desktop in canonical order",
        )?;
    }
    if version == 1 {
        require(
            *runtimes == json!(["codex-cli-desktop"]),
            "schema 1 policy.activation_required_runtimes must require codex-cli-desktop",
        )?;
    }
    for (requested, _) in ordered.get("profiles").get("aliases").items() {
        let mut current = requested;
        let mut visited = BTreeSet::new();
        while let Some(next) = aliases.get(current) {
            require(
                visited.insert(current),
                format!("profile alias cycle at {}", repr(current)),
            )?;
            current = next;
        }
        require(
            packs.get(current).is_some(),
            format!(
                "unknown capability profile {}; choose one of: {}",
                repr(requested),
                keys(packs).into_iter().collect::<Vec<_>>().join(", ")
            ),
        )?;
    }
    Ok(Value::Object(plugins))
}
