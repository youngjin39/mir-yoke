"""Validation for the tracked capability-source contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

_PLUGIN_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_EVIDENCE_KEYS = {"claude-code", "codex-cli-desktop"}
_SKILLS_ONLY_COMPONENT_POLICY = {
    "admitted_package_kinds": ["skills"],
    "reserved_active_package_kinds": ["hooks", "mcp"],
    "active_package_shape": "separate-named-package",
    "active_package_admission": "dedicated-validator-and-fresh-digest-acknowledgement",
    "project_integration": "target-local-only",
    "forbidden_provider_components": [
        "agents",
        "commands",
        "apps",
        "scripts",
        "permissions",
        "runtime-policy",
    ],
}
_PLUGIN_COMPONENT_POLICY = {
    **_SKILLS_ONLY_COMPONENT_POLICY,
    "admitted_package_kinds": ["skills", "skills-hooks"],
    "reserved_active_package_kinds": ["mcp"],
}
_COMMAND_DELIVERY = "claude-project-file-codex-plugin-skill"
_PROJECT_INTEGRATIONS = {
    "hooks": {
        "source": "config/project-hooks.json",
        "claude_target": ".claude/settings.json",
        "codex_target": ".codex/hooks.json",
        "delivery": "target-local-generated",
        "plugin_package_kind": "reserved",
    },
    "mcp_servers": {
        "activation_source": ".mcp.json",
        "reference": ".mcp.json.example",
        "codex_target": ".codex/config.toml",
        "delivery": "target-local-opt-in-generated",
        "plugin_package_kind": "reserved",
    },
}


class CapabilityConfigError(ValueError):
    """The tracked capability source is malformed or unsafe."""


def validate_https_git_url(raw: object) -> str:
    if not isinstance(raw, str) or not raw:
        raise CapabilityConfigError("source.url must be a non-empty HTTPS URL")
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CapabilityConfigError("source.url must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise CapabilityConfigError("source.url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise CapabilityConfigError("source.url must not contain a query or fragment")
    return raw


def validate_ref(raw: object) -> str:
    if not isinstance(raw, str) or _REF.fullmatch(raw) is None:
        raise CapabilityConfigError("source.ref is not a safe branch or tag name")
    if (
        raw.startswith("-")
        or raw.endswith((".", "/"))
        or ".." in raw
        or "//" in raw
        or "@{" in raw
        or any(char in raw for char in "\\~^:?*[]")
    ):
        raise CapabilityConfigError("source.ref is not a safe branch or tag name")
    return raw


def validate_relative_path(raw: object, *, prefix: str | None = None) -> str:
    if not isinstance(raw, str) or not raw:
        raise CapabilityConfigError("capability paths must be non-empty strings")
    if "\\" in raw or _WINDOWS_DRIVE.match(raw):
        raise CapabilityConfigError(f"unsafe capability path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise CapabilityConfigError(f"unsafe capability path: {raw!r}")
    if path.as_posix() != raw:
        raise CapabilityConfigError(f"non-canonical capability path: {raw!r}")
    if prefix is not None and (not path.parts or path.parts[0] != prefix):
        raise CapabilityConfigError(f"capability path must stay under {prefix}/: {raw!r}")
    return raw


@dataclass(frozen=True)
class CapabilityPack:
    plugins: tuple[str, ...]
    agents: tuple[str, ...]
    commands: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityConfig:
    source_schema_version: int
    source_url: str
    source_ref: str
    plugins: dict[str, str]
    plugin_kinds: dict[str, str]
    plugin_skills: dict[str, tuple[str, ...]]
    plugin_hooks: dict[str, tuple[str, ...]]
    active_digest_acknowledgements: dict[str, str]
    component_policy: dict[str, object]
    aliases: dict[str, str]
    packs: dict[str, CapabilityPack]
    agents: tuple[str, ...]
    commands: dict[str, str]
    project_integrations: dict[str, object]
    required_project_paths: tuple[str, ...]
    required_runtimes: tuple[str, ...]
    runtime_support: dict[str, object]
    policy: dict[str, object]

    def resolve_profile(self, requested: str) -> tuple[str, CapabilityPack]:
        profile = requested
        visited: set[str] = set()
        while profile in self.aliases:
            if profile in visited:
                raise CapabilityConfigError(f"profile alias cycle at {profile!r}")
            visited.add(profile)
            profile = self.aliases[profile]
        try:
            return profile, self.packs[profile]
        except KeyError as exc:
            choices = ", ".join(sorted(self.packs))
            raise CapabilityConfigError(
                f"unknown capability profile {requested!r}; choose one of: {choices}"
            ) from exc


def _string_map(raw: object, label: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise CapabilityConfigError(f"{label} must be an object")
    result: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise CapabilityConfigError(f"{label} must map strings to strings")
        result[key] = value
    return result


def load_capability_config(path: Path) -> CapabilityConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CapabilityConfigError(f"cannot read capability source: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CapabilityConfigError(f"invalid capability source JSON: {path}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") not in {1, 2, 3, 4}:
        raise CapabilityConfigError("capability source schema_version must be 1, 2, 3, or 4")
    source_schema_version = raw["schema_version"]

    source = raw.get("source")
    if not isinstance(source, dict):
        raise CapabilityConfigError("source must be an object")
    source_url = validate_https_git_url(source.get("url"))
    source_ref = validate_ref(source.get("ref"))

    plugins_raw = raw.get("plugins")
    if not isinstance(plugins_raw, dict) or not plugins_raw:
        raise CapabilityConfigError("plugins must be a non-empty object")
    plugins: dict[str, str] = {}
    plugin_kinds: dict[str, str] = {}
    plugin_skills: dict[str, tuple[str, ...]] = {}
    plugin_hooks: dict[str, tuple[str, ...]] = {}
    for name, metadata in plugins_raw.items():
        if not isinstance(name, str) or _PLUGIN_NAME.fullmatch(name) is None:
            raise CapabilityConfigError(f"invalid plugin name: {name!r}")
        if not isinstance(metadata, dict):
            raise CapabilityConfigError(f"plugin {name!r} metadata must be an object")
        if source_schema_version == 1:
            package_kind = "skills"
            expected_metadata = {"path", "skills"}
        else:
            package_kind = metadata.get("package_kind")
            allowed_kinds = (
                {"skills", "skills-hooks"}
                if source_schema_version == 4
                else {"skills"}
            )
            if package_kind not in allowed_kinds:
                raise CapabilityConfigError(
                    f"plugin {name!r} package_kind is not admitted: {package_kind!r}"
                )
            expected_metadata = {"path", "package_kind", "skills"}
        if package_kind == "skills-hooks":
            expected_metadata.add("hooks")
        if set(metadata) != expected_metadata:
            raise CapabilityConfigError(
                f"plugin {name!r} metadata must contain only "
                f"{', '.join(sorted(expected_metadata))}"
            )
        plugin_path = validate_relative_path(metadata.get("path"), prefix="plugins")
        if PurePosixPath(plugin_path).name != name:
            raise CapabilityConfigError(f"plugin path/name mismatch for {name!r}")
        plugins[name] = plugin_path
        plugin_kinds[name] = package_kind
        skills = metadata.get("skills")
        if not isinstance(skills, list) or not skills:
            raise CapabilityConfigError(f"plugin {name!r} skills must be a non-empty array")
        if not all(
            isinstance(skill, str) and _PLUGIN_NAME.fullmatch(skill) is not None
            for skill in skills
        ):
            raise CapabilityConfigError(f"plugin {name!r} contains an invalid skill name")
        if len(set(skills)) != len(skills):
            raise CapabilityConfigError(f"plugin {name!r} contains duplicate skills")
        plugin_skills[name] = tuple(skills)
        if package_kind == "skills-hooks":
            hooks = metadata.get("hooks")
            if hooks != ["SessionStart"]:
                raise CapabilityConfigError(
                    f"active hook plugin {name!r} must declare exactly SessionStart"
                )
            plugin_hooks[name] = tuple(hooks)
    all_skills = [skill for skills in plugin_skills.values() for skill in skills]
    if len(set(all_skills)) != len(all_skills):
        raise CapabilityConfigError("a common skill is declared by more than one plugin")

    component_policy = raw.get("plugin_component_policy")
    expected_component_policy = (
        _PLUGIN_COMPONENT_POLICY
        if source_schema_version == 4
        else _SKILLS_ONLY_COMPONENT_POLICY
    )
    if source_schema_version >= 3 and component_policy != expected_component_policy:
        raise CapabilityConfigError(
            "plugin_component_policy must preserve the canonical skills-only admission boundary"
        )
    if source_schema_version == 1 and component_policy is not None:
        raise CapabilityConfigError("schema_version 1 cannot declare plugin_component_policy")

    active_digest_acknowledgements: dict[str, str] = {}
    if source_schema_version == 4:
        acknowledgements = raw.get("active_package_digest_acknowledgements")
        if not isinstance(acknowledgements, dict) or set(acknowledgements) != set(plugin_hooks):
            raise CapabilityConfigError(
                "active package digest acknowledgement must cover every active hook package"
            )
        for name, digest in acknowledgements.items():
            if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                raise CapabilityConfigError(
                    f"active hook package {name!r} has an invalid digest acknowledgement"
                )
            active_digest_acknowledgements[name] = digest
    elif "active_package_digest_acknowledgements" in raw:
        raise CapabilityConfigError(
            "only schema_version 4 can declare active package digest acknowledgements"
        )

    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        raise CapabilityConfigError("profiles must be an object")
    aliases = _string_map(profiles.get("aliases", {}), "profiles.aliases")
    packs_raw = profiles.get("packs")
    if not isinstance(packs_raw, dict) or not packs_raw:
        raise CapabilityConfigError("profiles.packs must be a non-empty object")
    expected_profiles = {
        "code_app",
        "hybrid_pipeline",
        "infra_runtime",
        "content_workspace",
    }
    if set(packs_raw) != expected_profiles:
        raise CapabilityConfigError(
            "canonical profiles must be exactly code_app, hybrid_pipeline, "
            "infra_runtime, and content_workspace"
        )

    agents_raw = raw.get("agents")
    if not isinstance(agents_raw, dict) or not isinstance(agents_raw.get("allowlist"), list):
        raise CapabilityConfigError("agents.allowlist must be an array")
    agents: list[str] = []
    for agent_path in agents_raw["allowlist"]:
        value = validate_relative_path(agent_path, prefix=".claude")
        parts = PurePosixPath(value).parts
        if len(parts) != 3 or parts[1] != "agents" or not parts[2].endswith(".md"):
            raise CapabilityConfigError(f"agent path is outside .claude/agents: {value!r}")
        agents.append(value)
    if len(set(agents)) != len(agents):
        raise CapabilityConfigError("agents.allowlist contains duplicates")

    commands: dict[str, str] = {}
    if source_schema_version >= 3:
        commands_raw = raw.get("commands")
        if not isinstance(commands_raw, dict) or set(commands_raw) != {
            "delivery",
            "allowlist",
        }:
            raise CapabilityConfigError(
                "commands must contain only delivery and allowlist"
            )
        if commands_raw.get("delivery") != _COMMAND_DELIVERY:
            raise CapabilityConfigError("commands.delivery has drifted")
        allowlist = commands_raw.get("allowlist")
        if not isinstance(allowlist, dict) or not allowlist:
            raise CapabilityConfigError("commands.allowlist must be a non-empty object")
        known_skills = {
            f"{plugin}:{skill}"
            for plugin, skills in plugin_skills.items()
            for skill in skills
        }
        for command_path, codex_skill in allowlist.items():
            try:
                value = validate_relative_path(command_path, prefix=".claude")
            except CapabilityConfigError as exc:
                raise CapabilityConfigError(f"unsafe command path: {command_path!r}") from exc
            parts = PurePosixPath(value).parts
            if len(parts) != 3 or parts[1] != "commands" or not parts[2].endswith(".md"):
                raise CapabilityConfigError(
                    f"command path is outside .claude/commands: {value!r}"
                )
            if not isinstance(codex_skill, str) or codex_skill not in known_skills:
                raise CapabilityConfigError(
                    f"command {value!r} references an unknown skill"
                )
            commands[value] = codex_skill
        if raw.get("project_integrations") != _PROJECT_INTEGRATIONS:
            raise CapabilityConfigError(
                "project_integrations must preserve target-local hook and MCP ownership"
            )
    elif "commands" in raw or "project_integrations" in raw:
        raise CapabilityConfigError(
            "schema_version 1 or 2 cannot declare commands or project_integrations"
        )

    packs: dict[str, CapabilityPack] = {}
    inventories: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for name, pack in packs_raw.items():
        if not isinstance(name, str) or not isinstance(pack, dict):
            raise CapabilityConfigError(f"invalid profile pack: {name!r}")
        if source_schema_version == 1 and set(pack) != {"plugins", "agents"}:
            raise CapabilityConfigError(
                f"schema_version 1 profile {name!r} must contain only plugins and agents"
            )
        members = pack.get("plugins")
        pack_agents = pack.get("agents")
        pack_commands = pack.get("commands", [])
        if not isinstance(members, list) or not members:
            raise CapabilityConfigError(f"profile {name!r} plugins must be a non-empty array")
        if not isinstance(pack_agents, list) or not pack_agents:
            raise CapabilityConfigError(f"profile {name!r} agents must be a non-empty array")
        if source_schema_version >= 3 and (
            not isinstance(pack_commands, list) or not pack_commands
        ):
            raise CapabilityConfigError(f"profile {name!r} commands must be a non-empty array")
        if source_schema_version == 2 and pack_commands:
            raise CapabilityConfigError(
                f"schema_version 2 profile {name!r} cannot declare commands"
            )
        if not all(isinstance(member, str) and member in plugins for member in members):
            raise CapabilityConfigError(f"profile {name!r} references an unknown plugin")
        if len(set(members)) != len(members) or "mir-core" not in members:
            raise CapabilityConfigError(
                f"profile {name!r} must contain mir-core exactly once and no duplicates"
            )
        if not all(isinstance(agent, str) and agent in agents for agent in pack_agents):
            raise CapabilityConfigError(f"profile {name!r} references an unknown agent")
        if len(set(pack_agents)) != len(pack_agents):
            raise CapabilityConfigError(f"profile {name!r} contains duplicate agents")
        if not all(
            isinstance(command, str) and command in commands for command in pack_commands
        ):
            raise CapabilityConfigError(f"profile {name!r} references an unknown command")
        if len(set(pack_commands)) != len(pack_commands):
            raise CapabilityConfigError(f"profile {name!r} contains duplicate commands")
        selected_skills = {
            f"{plugin}:{skill}"
            for plugin in members
            for skill in plugin_skills[plugin]
        }
        if any(commands[command] not in selected_skills for command in pack_commands):
            raise CapabilityConfigError(
                f"profile {name!r} command maps outside its selected plugin skills"
            )
        inventory = (tuple(members), tuple(pack_agents), tuple(pack_commands))
        if inventory in inventories:
            raise CapabilityConfigError(f"profile {name!r} duplicates another inventory")
        inventories.add(inventory)
        packs[name] = CapabilityPack(*inventory)

    required_raw = raw.get("required_project_paths")
    if not isinstance(required_raw, list) or not required_raw:
        raise CapabilityConfigError("required_project_paths must be a non-empty array")
    required_project_paths = tuple(validate_relative_path(path) for path in required_raw)
    if len(set(required_project_paths)) != len(required_project_paths):
        raise CapabilityConfigError("required_project_paths contains duplicates")
    if source_schema_version >= 3:
        required_integrations = {
            "config/project-hooks.json",
            ".claude/settings.json",
            ".codex/hooks.json",
            ".codex/config.toml",
        }
        if not required_integrations <= set(required_project_paths):
            raise CapabilityConfigError(
                "required_project_paths must include managed hook and MCP projections"
            )

    runtime_support = raw.get("runtime_support")
    policy = raw.get("policy")
    if not isinstance(runtime_support, dict) or not isinstance(policy, dict):
        raise CapabilityConfigError("runtime_support and policy must be objects")
    if runtime_support.get("supported") != [
        "claude-code",
        "codex-cli",
        "codex-desktop",
    ]:
        raise CapabilityConfigError("runtime_support.supported has drifted")
    unsupported = runtime_support.get("unsupported")
    if not isinstance(unsupported, dict) or "codex-ide-extension" not in unsupported:
        raise CapabilityConfigError("Codex IDE extension boundary must be explicit")
    required_runtimes = policy.get("activation_required_runtimes")
    if (
        not isinstance(required_runtimes, list)
        or not required_runtimes
        or not all(
            isinstance(runtime, str) and runtime in _RUNTIME_EVIDENCE_KEYS
            for runtime in required_runtimes
        )
        or len(set(required_runtimes)) != len(required_runtimes)
    ):
        raise CapabilityConfigError(
            "policy.activation_required_runtimes must contain unique supported runtimes"
        )
    if source_schema_version >= 3 and required_runtimes != [
        "claude-code",
        "codex-cli-desktop",
    ]:
        raise CapabilityConfigError(
            "schema 3+ policy.activation_required_runtimes must require "
            "claude-code and codex-cli-desktop in canonical order"
        )
    if source_schema_version == 1 and required_runtimes != ["codex-cli-desktop"]:
        raise CapabilityConfigError(
            "schema 1 policy.activation_required_runtimes must require codex-cli-desktop"
        )

    config = CapabilityConfig(
        source_schema_version=source_schema_version,
        source_url=source_url,
        source_ref=source_ref,
        plugins=plugins,
        plugin_kinds=plugin_kinds,
        plugin_skills=plugin_skills,
        plugin_hooks=plugin_hooks,
        active_digest_acknowledgements=active_digest_acknowledgements,
        component_policy=component_policy,
        aliases=aliases,
        packs=packs,
        agents=tuple(agents),
        commands=commands,
        project_integrations=(
            _PROJECT_INTEGRATIONS if source_schema_version >= 3 else {}
        ),
        required_project_paths=required_project_paths,
        required_runtimes=tuple(required_runtimes),
        runtime_support=runtime_support,
        policy=policy,
    )
    for alias in aliases:
        config.resolve_profile(alias)
    return config
