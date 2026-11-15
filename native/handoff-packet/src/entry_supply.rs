//! Public relation and project-hook bindings; no Python fallback or network discovery.
use handoff_packet::{mir_cli, mir_core};
use serde_json::Value;

pub fn hooks(argv: &[&str], metadata: &Value, target: Option<&str>) -> mir_cli::memory::Output {
    use mir_cli::{adoption_native as adoption, project_hooks as hooks};
    let disabled = std::env::var("MIR_CAPABILITY_NATIVE_ARTIFACTS").as_deref() == Ok("0");
    hooks::main(
        argv,
        metadata,
        target,
        disabled,
        |root, pin| {
            // Preserve the private host's bounded local-source admission.
            let source = pin.get("url").and_then(Value::as_str)?;
            let local = mir_core::capabilities::native::local_source(source).ok()??;
            if hooks::unsupported_read_size(pin)
                || local.components().next().is_some_and(|part| {
                    part.as_os_str()
                        .to_str()
                        .is_some_and(|s| s.starts_with('~') && s != "~")
                })
            {
                return None;
            }
            adoption::install_project_hooks(
                root,
                &adoption::InstallOptions {
                    target,
                    artifact_pin: Some(pin),
                    ..Default::default()
                },
                &mut adoption::LocalHost,
            )
        },
        hooks::run_probe,
    )
}

pub fn relations(argv: &[&str]) -> mir_cli::memory::Output {
    use mir_core::memory_relations as memory;
    mir_cli::relations::main(argv, |bundle, anchors, purposes, options| {
        if bundle {
            memory::bundle_memory_relations(anchors, purposes, options)
        } else {
            memory::query_memory_relations(&anchors[0], purposes[0].as_str().unwrap_or(""), options)
        }
    })
}

pub fn console(family: &str, argv: &[&str]) -> mir_cli::memory::Output {
    if family == "relations" {
        return relations(argv);
    }
    let system = match std::env::consts::OS {
        "macos" => "Darwin",
        "linux" => "Linux",
        "windows" => "Windows",
        _ => "",
    };
    let target = mir_core::capabilities::native::host_target(system, std::env::consts::ARCH);
    hooks_resource(
        argv,
        include_str!("../../../config/project-hooks-provider.json"),
        target.as_deref(),
    )
}

// A byte-input seam exercises the real resource parser without replacing an Error.
pub fn hooks_resource(argv: &[&str], bytes: &str, target: Option<&str>) -> mir_cli::memory::Output {
    // Same wheel resource mapping as pyproject.toml; never consult a consumer lock.
    let metadata = match serde_json::from_str(bytes) {
        Ok(value) => value,
        Err(error) => {
            return (
                1,
                format!("project-hooks: degraded: {error}\n").into_bytes(),
                vec![],
            );
        }
    };
    hooks(argv, &metadata, target)
}
