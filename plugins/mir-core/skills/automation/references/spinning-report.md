# Report-only SPINNING check

Inspired by ADR-58 item 5b.

Use when observing an existing multi-attempt run. Before assessment, record a
finite, declared number of attempts and what counts as measurable progress in the
existing run ledger (for example newly passing cases or a completed checkpoint).
The observation window does not authorize another attempt or a new process.

Repeated identical failure signatures or no measurable progress across that window
produce a **SPINNING** report to the Main. Reuse existing telemetry when available:
Mir Yoke's own executor implements this signature (`error_sig`); consumers apply
the rule manually. It is neither a required detector nor a guarantee that
equal signatures have the same root cause.
Compare actual evidence, not a changing narrative or merely elapsed time.

Report the run ID, declared window, attempt IDs, signatures and output locations,
progress baseline/current measurements, and what remains unknown. If signatures or
measurements are unavailable, report insufficient evidence rather than inventing a
SPINNING diagnosis. Use the existing ledger or authorized Main reply surface.

This is report-only: no automatic retry, escalation, model change, dispatch,
restart, cancellation or other actuation. The Main decides any next action within
owner authority. This reference adds no loop, hook, detector code or second cursor.
