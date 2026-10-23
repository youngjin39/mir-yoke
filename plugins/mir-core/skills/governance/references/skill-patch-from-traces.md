# Propose a skill patch from traces

Inspired by microsoft/SkillOpt at 84b36cd.

Use only for owner-invoked skill maintenance within an authorized source scope.

1. Group authorized, redacted traces by recurring success or failure pattern. Cite
   the supporting cases and separate a systematic omission from a one-off incident.
   Do not harvest transcripts or promote an observed preference into binding policy.
2. Identify the canonical skill source and propose the smallest justified add,
   replace or delete edits. Declare an edit budget before drafting; explain each edit
   and avoid redundant rules or task-specific constants. An empty proposal is valid.
3. Keep selection cases separate from held-out final evaluation cases. Compare the
   unchanged baseline with the proposal and report improved, regressed, persistently
   failing and stable cases, together with instruction length and scoring uncertainty.
   A score, including an LLM judgment, is advisory and cannot become a hard gate.
4. Keep the patch staged for Main review. Put source identity, supporting evidence
   and rejected-edit reasons in the existing evidence sink. Apply an approved change
   through existing generation and verification, preserving cross-runtime parity.

Neither learned wording nor a score grants instruction or memory write authority.
Main retains recommendations and dispatch under centrally owned model selection.
Do not add an optimizer engine, scheduler, nightly cycle, runner, transcript harvester,
WebUI, commands, autonomous evolution or auto-adopt path.
