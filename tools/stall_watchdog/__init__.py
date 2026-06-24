"""your-harness Stall Watchdog — ADR-06 MIR-STALL-001.

External supervisor that tails Claude Code JSONL session ledgers to detect
in-flight stalls (CLI infinite wait or model-API silent drop) that Stop/StopFailure
hooks cannot catch. Single-deploy daemon covers all 15 family workspaces via the
unified ``~/.claude/projects/`` pool.
"""

__all__: list[str] = []
