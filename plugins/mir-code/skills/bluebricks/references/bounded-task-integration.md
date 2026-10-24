# Bounded multi-task integration

Inspired by fn-opt/dryforge at f5aa6d7.

This optional advisory recipe helps Main coordinate already authorized multi-task
work. It does not authorize delegation, new tasks, commits or cleanup by itself.

1. Bound the result and record task ownership, file boundaries, dependencies,
   expected evidence and base revisions. Give each authorized worker enough context
   to preserve others' edits and report conflicts rather than overwrite them.
2. Separate independent work from dependent work. At each dependency barrier,
   inspect the prerequisite artifact and checks before starting its consumers;
   a worker's completion claim alone is insufficient evidence.
3. Assign one owner for shared writes and regeneration. Put a barrier before
   integrating edits to shared sources; regenerate only after their inputs settle.
   Reconcile changed base revisions before dependent edits or generated output.
4. Run each task's smallest relevant isolated checks and retain its diff and
   revision evidence. Bring successful changes together in dependency order,
   resolving conflicts against the agreed result and preserving unrelated work.
5. Check the integrated result at the combined revision, including affected
   contracts, shared boundaries and generated parity, before closure. Isolated
   passes do not establish that the combined result works. Report unresolved
   failures to Main and revise only the affected work and checks.
6. Retain failed worktrees and diagnostic evidence for inspection. Cleanup needs
   applicable authority; do not delete worktrees or unmerged work merely because
   a task failed or integration ended. Record retained locations in the existing
   task record rather than creating a second handoff.
