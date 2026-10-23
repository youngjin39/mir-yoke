# Evaluate an instruction change

Inspired by drona23/claude-token-efficient at 0d30a6d.
Inspired by bugbug9999/token-diet at 82ac6a7.

Use on demand to test a proposed instruction intervention; savings are a hypothesis.

1. Select representative tasks and compare baseline and candidate with repeated runs.
   Record model, runtime, instruction profile and isolation conditions. Include tasks
   that need a full answer despite a concision request, and retain neutral or negative
   results rather than selecting only favorable examples.
2. Separate recurring input, output, cache accounting and cost per accepted result.
   Label words separately from tokens and estimates separately from observed usage.
   State the acceptance rule so cheaper failed attempts do not look like savings.
3. Assess retained facts, corrections, completeness and task success alongside length.
   Model judgments are advisory; keep runnable task checks as independent evidence.
   Do not substitute a shorter answer or judge score for required verification.

## Input inventory

Build a table with one row per instruction scope, memory entrypoint, exposed tool
schema and skill metadata component. Columns: observed bytes/tokens, load frequency,
measurement source and uncertainty. Inspect context actually exposed by the CLI;
do not count every configured tool as fully transmitted on every turn.

Compare cold-cache and warm-cache estimates using recorded usage or explicitly
supplied rates. Show assumptions and unknown cache behavior; assume no universal
TTL, discount, price or bytes-to-token conversion.

Propose placement as always needed, task-conditional or historical. Route authorized
relocation through governance, preserving authority, discovery pointers and generated
parity. This evaluation does not apply relocations or overwrite canonical instructions.

Do not install profiles/agents, change global configuration or central routing, use
model environment overrides, disable MCP, impose fixed tool/retry/byte caps, remove
safeguards, prescribe unrelated implementations or send synthetic keep-alive traffic.
Do not import embedded scripts or create home-directory reports.
