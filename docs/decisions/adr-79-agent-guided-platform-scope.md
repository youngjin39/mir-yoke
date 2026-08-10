---
title: Agent-Guided Platform Scope and Supported Bootstrap Boundary
type: template-adr
created: 2026-08-10
status: accepted
supported_automation: macos-linux-wsl
native_windows: guidance-only
amends: [adr-74, adr-78]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-79 — Agent-Guided Platform Scope and Supported Bootstrap Boundary

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
4. Support automated bootstrap on macOS, Linux, and WSL while making native Windows a fail-fast,
   guidance-only path.

## 4. Decision

Automated greenfield bootstrap and ready-receipt claims support macOS, Linux, and WSL. WSL follows
the Linux/Bash contract. Native Windows PowerShell is not a supported automation lane.

`setup.ps1` remains only as a safe guidance entrypoint. It performs no installation, capability
activation, bootstrap, or repository mutation. It directs the operator or AI agent to run
`setup.sh` inside WSL or to use Mir Yoke as reference material for an explicit repository-local
adaptation. Direct native-Windows invocation of `mir bootstrap` must also stop before mutation.

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
- Native Windows cannot enter the slim transaction or publish misleading readiness.
- AI agents can still guide Windows users through WSL or selective reference adoption.
- Platform policy becomes smaller without reducing repository-local judgment.

## 7. Negative Consequences — HARD

- Native Windows users need WSL for automated greenfield bootstrap.
- The public template no longer claims three-native-OS parity.
- Maintainers must keep guidance-only entrypoints and supported CI lanes visibly distinct.

## 8. Out-of-Scope — HARD

- Building a native PowerShell hook, transaction, or generator implementation.
- Guaranteeing automated bootstrap on every Unix variant or third-party agent runtime.
- Letting an AI agent bypass the target repository's authority, protected paths, or verification.
- Changing the preservation-first existing-repository adoption boundary.

## 9. Verification

- macOS and Linux CI execute the same Bash bootstrap contract; WSL is documented as the Windows
  route for that Linux contract.
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
