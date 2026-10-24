# Migration policy confirmation

Inspired by fn-opt/dryforge at f5aa6d7.

Use this short advisory reference for existing-code migration interviews; it adds
no mandatory layout or engine. Reuse the design skill's existing dispositions.

1. Mark implementation observed in code as `code_confirmed`, with its location.
   Keep it separate from owner intent: code confirmation alone never confirms owner intent.
   Use `user_confirmed` only with owner evidence for the intended rule; cite that
   evidence separately even when implementation and intent agree.
2. Derive ordinary answers from available material first, but dangerous inferred business or security policy
   needs existing owner evidence or targeted confirmation before it becomes an
   accepted intent rule. Keep unsupported inference `derived` and intent `unresolved`;
   preserve disagreement as `conflict`. Do not use a technical default to close it.
3. Ask about important intended rules absent from code, including missing business
   constraints or security boundaries that could change the migration outcome.
   State the observed omission and the specific policy question; an absent
   implementation is not evidence that the owner intended no rule.
4. Reconcile answers with the affected design decisions. Retain `not_applicable`
   only with a reason, and leave `unresolved` or `conflict` open until resolved by
   appropriate evidence or the owner. Do not re-ask already evidenced decisions.
