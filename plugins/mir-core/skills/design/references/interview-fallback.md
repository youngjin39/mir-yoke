# Degraded interview brief

Inspired by ADR-58 item 4.

Use when an interview cannot proceed because of no reply channel, tool failure,
or a time-out. If a question tool fails but text replies work, continue in plain
text; otherwise leave this text-only brief in the existing task evidence record
or available reply surface. Do not create a competing cursor or send a message
through an unauthorized channel.

- **Unresolved decisions:** list each open question, its prerequisites and the
  recommended defaults with reasons. Label recommendations as proposals, not answers.
- **Blocked:** name the design choices and actions that depend on those decisions;
  distinguish any independent work already authorized by the owner.
- **Next human action:** state who needs to answer or restore the reply channel,
  which numbered questions need answers, and how to resume the same interview.
- **Evidence:** state the observed interruption and last completed round. A time-out
  records an absent response, never agreement or a new authorization.

Never invent answers, silently enact recommended defaults or claim interview
completion. Resume from the unresolved frontier when communication returns and
obtain the shared-understanding confirmation before acting on that design.
