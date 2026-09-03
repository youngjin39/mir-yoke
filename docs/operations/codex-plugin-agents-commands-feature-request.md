---
title: Codex Plugin Agents and Commands Feature Request
status: agent-request-submitted-command-request-not-planned
updated: 2026-09-03
upstream: https://github.com/openai/codex
---

# Codex Plugin Agents and Commands Feature Request

This record avoids duplicate upstream requests and preserves the submitted text.

## Existing agent issue

Target: <https://github.com/openai/codex/issues/18308>

Suggested comment:

> We have a concrete cross-repository use case for this in Mir Yoke. We package shared development
> workflows as role-oriented plugins (`core`, `code`, and `content`) used by both Claude Code and
> Codex. Skills install globally and remain namespaced, but each consumer repository still needs a
> copied/generated `.codex/agents/*.toml` projection. That prevents the plugin from being the
> complete reusable role boundary and creates drift between repositories.
>
> It would help if plugins could contribute namespaced custom agents, for example
> `mir-code:reviewer`, with these safeguards:
>
> 1. The plugin manifest declares an `agents` directory or explicit inventory.
> 2. Agent names are namespaced by plugin, with deterministic collision and project-override rules.
> 3. Installation shows and requires trust for model, reasoning, tools, sandbox, and delegation
>    settings before the agent becomes available.
> 4. Project agents can intentionally override or extend a plugin agent without the plugin writing
>    `.codex/agents` in the repository.
> 5. `codex plugin list --json` and app-server APIs expose the installed agent inventory and source
>    digest so automation can verify it after a fresh session.
>
> The desired result is one plugin package that can be reused across repositories without copying
> agent definitions, while preserving project-local policy and explicit trust.

Submitted: <https://github.com/openai/codex/issues/18308#issuecomment-5527444139>

## Command-alias request not submitted

OpenAI maintainers already closed `#13893`, `#22674`, and `#31666`, explaining that custom slash
commands were intentionally removed in favor of explicitly invocable skills and are not planned to
return. The draft below is retained as product rationale, but a duplicate issue was not created.

Suggested title: `Allow Codex plugins to contribute namespaced command aliases for skills`

Suggested body:

> ### What variant of Codex are you using?
>
> Codex CLI and Codex App.
>
> ### What feature would you like to see?
>
> Allow a plugin to declare namespaced command aliases that invoke or preselect one of its packaged
> skills. For example, a plugin could expose `/mir-core:verify` as an explicit, discoverable entry
> point for the `mir-core:verify` skill.
>
> We maintain one set of role-oriented workflow plugins for Claude Code and Codex across multiple
> repositories. Claude can expose an explicit command surface, while Codex currently requires the
> same intent to be inferred from a skill or copied into project files. The workflow body already
> belongs to the skill; the missing piece is a stable explicit invocation and discovery surface.
>
> Suggested contract:
>
> - A manifest `commands` inventory maps a namespaced alias to a packaged skill plus a short
>   description and optional default prompt.
> - Aliases cannot execute arbitrary package code; they select a skill and submit the declared
>   prompt through normal Codex policy and tool approval.
> - Plugin namespace, collision, enable/disable, and project-override rules are deterministic.
> - The CLI/App lists the alias, its source plugin, target skill, version, and digest.
> - Removing or disabling the plugin removes its aliases without writing repository files.
>
> This would let one role plugin provide the same explicit workflow entry points across repositories
> while keeping skills as the canonical instruction body.

## Submission procedure

The agent request has been delivered. Revisit the command request only if Codex changes its stated
skills-first direction or asks for a narrower plugin discovery proposal.
