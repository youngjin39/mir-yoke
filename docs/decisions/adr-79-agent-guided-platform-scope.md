---
title: Agent-Guided Platform Scope and Supported Bootstrap Boundary
type: template-adr
created: 2026-08-10
amended: 2026-09-04
status: accepted
primary_automation: macos
compatibility_lanes: [linux, wsl]
native_windows: reference-adaptation-only
amends: [adr-74, adr-78]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-79 — Agent-Guided Platform Scope and Supported Bootstrap Boundary

> **2026-09-04 owner amendment:** macOS remains the primary operational and release-evidence lane.
> Linux and WSL are separate compatibility lanes whose failure does not invalidate a proven macOS
> provider. Native Windows consumes this repository as AI-readable reference material for a
> target-owned adaptation; cloning Yoke is not an instruction to apply its POSIX automation.

## 1. Context

Mir Yoke provides a baseline harness-engineering template that an AI agent evaluates against the
repository it has actually opened. It is not a universal operating-system installer. Earlier
portable-bootstrap work treated native Windows PowerShell as a ready-state automation target even
though the active hook and generation toolchain is Unix-oriented.

The owner confirmed that repository-specific agent judgment and explicit local adaptation are the
product value. Platform breadth must not force unsafe or misleading automation into that template.

## 2. Decision Drivers

- Keep the default automated path small, observable, and compatible with the shipped Bash hooks.
- Let an AI agent adapt guidance to the target repository without claiming unsupported execution.
- Stop unsupported automation before it mutates project or host state.
- Preserve Mir Yoke as reusable material rather than an authoritative runtime or installer.

## 3. Considered Alternatives — HARD

1. Continue promising equivalent native Windows, macOS, and Linux ready-state automation.
2. Rewrite the complete hook, generator, transaction, and launcher stack for native PowerShell.
3. Remove every Windows-visible entrypoint and leave users without a safe explanation.
4. Keep macOS as the primary automated lane, retain Linux and WSL as isolated compatibility lanes,
   and make native Windows a fail-fast, reference-adaptation-only path.

## 4. Decision

macOS is the primary automated bootstrap, provider, and release-evidence lane. The existing Bash
implementation may run on Linux and WSL as separate compatibility lanes, but neither lane is a
prerequisite for macOS acceptance. A Linux or WSL failure marks only that compatibility lane not
ready unless the same evidence proves a shared source artifact is invalid.

WSL uses its own Linux runtime homes, plugin caches, receipts, and `MIR_CAPABILITY_HOME`. It must not
reuse or claim the native Windows Claude/Codex user homes. A future WSL bundle or canary may be
maintained separately without adding Windows-specific branches to the macOS provider path.

Native Windows PowerShell is not a supported automation lane. A Windows project may point an AI
agent at the Git repository as a template example. The agent reads the target's own contract,
selects only applicable skills, agents, command intent, hook semantics, and structure, replaces
POSIX assumptions with target-owned Windows implementations, and verifies the result locally. It
must not copy Yoke wholesale or report Yoke bootstrap/plugin readiness from source presence alone.

`setup.ps1` remains only as a safe guidance entrypoint. It performs no installation, capability
activation, bootstrap, or repository mutation. It directs the operator or AI agent to the separate
WSL compatibility lane or to Mir Yoke's Windows reference-adaptation guide. Direct native-Windows
invocation of `mir bootstrap` must also stop before mutation.

The AI agent owns contextual assessment, not implicit authority. It reads the target repository's
contract and Profile, selects applicable template material, records target-specific decisions, and
uses the target's own verification. Unsupported platforms may inspect and adapt files, but Mir Yoke
does not issue a ready receipt or claim equivalent automated behavior there.

## 5. Rejected Alternatives — HARD

- Equivalent native Windows automation: expands the product into a second runtime toolchain and
  preserves unsafe platform assumptions.
- Full PowerShell rewrite: duplicates the Unix implementation and conflicts with the minimum
  template goal.
- Silent removal of Windows entrypoints: gives an operator no safe next action and encourages
  improvised execution.

## 6. Positive Consequences

- The supported bootstrap contract matches the actual Bash-based harness runtime.
- macOS release evidence stays independent of WSL environment availability or compatibility drift.
- Native Windows cannot enter the slim transaction or publish misleading readiness.
- AI agents can construct a target-owned Windows harness from explicit, versioned Yoke examples.
- Platform policy becomes smaller without reducing repository-local judgment.

## 7. Negative Consequences — HARD

- WSL and native Windows require separate runtime homes and cannot share one activation receipt.
- Native Windows adaptation has no automatic readiness claim; the target must define and run its
  own Windows checks.
- The public template no longer claims three-native-OS parity.
- Maintainers must keep guidance-only entrypoints and supported CI lanes visibly distinct.

## 8. Out-of-Scope — HARD

- Building a native PowerShell hook, transaction, or generator implementation.
- Shipping or validating a WSL bundle in the macOS provider release gate.
- Guaranteeing automated bootstrap on every Unix variant or third-party agent runtime.
- Letting an AI agent bypass the target repository's authority, protected paths, or verification.
- Changing the preservation-first existing-repository adoption boundary.

## 9. Verification

- macOS runs the authoritative provider and release checks. Linux and WSL compatibility results are
  reported separately and cannot silently upgrade themselves to primary evidence.
- The Windows/WSL reference-adaptation guide identifies non-portable hook, generator, launcher, and
  user-home assumptions and gives an AI agent a bounded target-configuration procedure.
- `setup.ps1` returns a guidance-only failure without invoking `uv`, Mir, or another mutating tool;
  `setup.sh` rejects native-Windows Bash and other unsupported systems before tool or storage work.
- `mir bootstrap` rejects unsupported execution before project input parsing, snapshots, or writes,
  while retaining read-only `--help` inspection.
- Public slim transaction entrypoints reject unsupported platforms before reading project state.
- Root contracts, bootstrap guidance, quality requirements, and generated derivatives name the
  same support boundary.

## 10. References

- ADR-74 — portable bootstrap, capability sources, and required memory.
- ADR-78 — public template identity and non-authority.
- `docs/operations/windows-wsl-reference-adaptation.md` — AI-agent adaptation procedure and lane
  warnings.
