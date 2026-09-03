---
name: runtime-continuity
description: Keep work continuous after a runtime lifecycle transition without assuming repository-specific authority. Use when resuming a session, reconciling compacted context, or deciding what must be revalidated before continuing.
---

# Runtime Continuity

Re-establish the current task from the repository-owned cursor and active evidence before acting.

Keep repository policy, paths, state, and write authority owned by the target repository. Treat the lifecycle hook as bounded context only; it does not discover state, grant authority, or mutate files.
