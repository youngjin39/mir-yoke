# Porting with parity

Port only a measured hot path or a demonstrated distribution need. The existing
implementation remains the reference until parity passes; retain a runnable copy.

1. Capture golden fixtures covering stdin bytes, args and relevant environment.
   Include successful, empty, malformed, boundary and failure inputs and Unicode
   text. Capture stdout bytes, stderr bytes and exit code from the reference.
2. Build a differential test that runs both implementations on every fixture and
   compares stdout, stderr and exit code byte for byte against the goldens and
   each other. Do not normalize whitespace, encoding, line endings or diagnostics
   to conceal differences. Show a new test failing before implementation.
3. Preserve output bytes, exit codes, timeouts, budgets and fail-open/fail-closed
   behavior. Exercise those boundaries explicitly. List every intentional
   difference and obtain project-owner agreement before changing the contract.
4. A partial port may forward unported paths unchanged to the reference: preserve
   args, relevant env, the same stdin, stdout/stderr and the same exit code. Do not
   consume stdin during dispatch and then forward an empty stream. Test forwarding
   through the real caller route so the hot path can move first safely.
5. Measure repeated cold-start timing for both implementations under comparable
   conditions. Record the command, environment, sample count, median and p90.
   Separate process startup from warmed execution and document cache assumptions.
   A faithful port can lose most startup gains to per-process pattern compilation.
   Measure fast and slow paths separately and profile before optimizing. Prefer
   conservative necessary-literal prefilters, compiling only patterns the taken
   path needs, or build-time precompilation. A prefilter may skip only work whose
   result is already determined; keep boundary fixtures for special case folds,
   Unicode words, markup, line breaks and near misses. Demonstrate that deliberately
   wrong prefilters fail those fixtures before accepting the optimization.
6. Switch callers only after parity passes and latency is measured. Keep rollback
   to the reference available until the supported platform checks pass.
