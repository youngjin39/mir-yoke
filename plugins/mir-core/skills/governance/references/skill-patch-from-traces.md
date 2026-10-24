# Propose a skill patch from traces

Inspired by microsoft/SkillOpt at 84b36cd.

Use only for owner-invoked skill or instruction-document maintenance within an
authorized source scope: CLAUDE.md, AGENTS.md and their canonical sources may be
proposed under the same edit budget, held-out comparison, staging and owner adoption rules.
Generated derivatives are regenerated, never hand-edited.

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

## Learning-safe feedback and per-skill proposals

Keep raw judge evidence in its authorized audit sink. Behavioral learning-safe
feedback describes the user-visible mistake and desired behavior, excluding
evaluator internals: hidden answers, check expressions, private labels and raw
judge rationales. Review the description for secrets, prompt-like content and
misleading claims; a prose projection is not a universal sanitizer. When a safe
behavioral explanation is unavailable, mark feedback insufficient rather than
forwarding raw evidence or inventing a lesson.

Stage independent per-skill proposals, each with source identity, small diff,
supporting cases, baseline comparison, regressions and rejected-edit reasons.
Main chooses an explicit subset, including none. Disclose cross-skill dependencies;
review the chosen subset together for conflicts and run its relevant held-out
checks before authorized application. Do not silently apply unselected proposals
or claim that isolated improvements establish combined improvement.
