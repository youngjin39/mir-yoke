# Plan

## P5 — Restore core harness engineering and release v0.9.0 (2026-08-11) — ACTIVE

Authorization: the owner approved implementation, capability-lock rebinding, intentional commits,
SSH push to `main`, and the `v0.9.0` tag. The owner will run the external generated-repository
acceptance later; release evidence must describe that run as post-release acceptance, not a tag
prerequisite.

- P5.1 DONE — recorded the restoration TDD contract and mapped the v0.8 public CLI/bootstrap/memory
  surface against the current Project Agent Kit.
- P5.2 DONE — restored the public `mir` package entry point, dispatcher, installed-CLI proof, and
  explicit bootstrap regression without exposing the removed `yoke` composer as an active command.
- P5.3 DONE — required a bounded project-owned common harness and memory component in the
  Project Agent Kit while keeping the four-file Minimal Starter unchanged and never copying the Mir
  CLI implementation into generated repositories.
- P5.4 DONE — preserved the superseded ADR-82 composition platform under a clearly non-default
  reference-template namespace with inventory and classification gates.
- P5.5 DONE — aligned ADR-83, README, architecture, bootstrap, migration, specifications, generated
  derivatives, release policy, and durable task state with the three supported layers.
- P5.6 DONE — implementation commit `e5abfad` records the restored surface; focused/full
  regressions, independent review, and materialized clean-candidate readiness pass; the protected
  capability lock is rebound to that implementation in the separate release commit.
- P5.7 ACTIVE — repeat readiness from the final clean tree, push the verified commits to `main` over
  SSH, push the `v0.9.0` annotated tag, and confirm the tag-triggered GitHub Release.
