# Frontier interview rounds

Inspired by mattpocock/skills at 5beb35b.

Use for consequential or owner-requested interviews, not routine bounded work.
This expands **Grill-style elicit** and **Derive-first elicit** in the entrypoint;
it does not replace their filtering of answered or derivable decisions.
Outside owner-invoked interviews, retain tuning defaults from the entrypoint.

Conversation-only interviews need no repository or workspace. When a repository
exists, use its existing active cursor for durable decisions under local policy;
do not create a workspace merely to conduct an interview.

1. Map the scoped Decision Surface as a design tree. Record each decision's
   prerequisites and disposition; confirmed and derived answers need no new question.
   The frontier contains every unresolved human decision with settled prerequisites.
2. Ask the whole frontier together in numbered rounds. Give each question a
   recommended answer and brief rationale; phrase it so "yes" accepts that answer.
   Example: "Should exports include archived rows? Recommended answer: yes, because
   the stated audit goal includes historical records." Alternatives remain welcome.
3. Facts are the agent's job: look up repository/environment evidence yourself, or
   use an already-available sub-agent when authorized. A pending fact is an unsettled
   prerequisite: defer its dependent questions while independent questions proceed.
   Do not make the user research discoverable facts or wait for unrelated research.
4. Wait for answers. Before recording a decision or recomputing the tree and frontier,
   including newly exposed branches, take each free-text answer carrying scope, constraints
   or exclusions, restate it in one line and confirm it with the user in the next round's
   numbered list. Keep dependent questions deferred until confirmation; do not ask them
   in the same round as their prerequisites.
   Once confirmed, recompute the tree and frontier, including newly exposed branches.
   The interview ends when the frontier is empty and every scoped branch has an
   explicit disposition; an unanswered or conflicting decision is not settled.
5. Summarize the shared understanding, including scope, decisions and any explicitly
   deferred work. Get the user's confirmation of that understanding before acting
   on the interviewed design. Missing replies never count as confirmation.

When a frontier question requires visible alternatives to answer meaningfully,
propose a bounded throwaway prototype instead of repeating abstract questions.
State the alternatives, scope, time or effort limit, evidence to observe, and
disposal plan. Build only within authorized scope; a prototype grants no delivery
or deletion authority. Present what was observed, separate it from assumptions,
then resume the frontier with the remaining owner decisions. Dispose of artifacts
only under applicable authority, otherwise retain them and state their status.

In remote channels use numbered text lists, never interactive pickers. If the
interview cannot continue, use the adjacent interview-fallback reference.
