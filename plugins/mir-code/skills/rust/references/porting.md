# Porting with parity

Use the owning repository's port criteria. Pin the existing implementation for parity and retain a runnable reference until acceptance.

1. Capture golden fixtures covering stdin bytes, args and relevant environment.
   Capture stdout bytes, stderr bytes, exit code and relevant file and process
   effects from the reference. Use a project-owned scenario card to map each
   changed surface to concrete witnesses for each applicable edge class.

   - Malformed input and its refusal path.
   - Error and cleanup, including the state left after a partial failure.
   - Boundary values, including empty inputs and values below, at and above a limit.
   - Prior install state, including clean and already-installed paths.
   - Caller route, through the supported entry point that selects the implementation.

   Include a successful control. Have generators reject duplicate case IDs and
   duplicate witness inputs before insertion, using the input, caller route, and
   relevant starting state to identify a witness. Check that each input reaches
   its named class. For example, use an otherwise valid input to witness a size
   limit so an earlier parse error cannot satisfy the assertion. For parser
   generators, record a pinned seed and include directed witnesses that
   guarantee each applicable edge class regardless of the random output.
   If many comparisons match unexpectedly, verify that the generator changed the inputs.
   Include Python/Rust boundary cases for Unicode, line splitting, exceptions, serialization, and paths.
2. Build a differential test that runs both implementations on every fixture and
   compares stdout and stderr byte for byte, along with exit code and recorded
   effects, against the goldens and each other. Do not normalize whitespace,
   encoding, line endings or diagnostics to conceal differences. Before the fix,
   verify that the test builds and the intended case runs and fails on the
   contract assertion. A compile error, setup failure or zero selected tests
   cannot establish failing-first evidence. Re-run the same case after the fix.
3. Preserve output bytes, exit codes, timeouts, budgets and fail-open/fail-closed
   behavior. Exercise those boundaries explicitly. List every intentional
   difference and obtain project-owner agreement before changing the contract.
   For each boundary change, sample one mutant that violates the boundary and
   run the targeted witness against the freshly built mutant after a green
   unmutated run. Use a bounded process-group runner with a wall-clock deadline
   that terminates the group and reaps the child on timeout. Save the original
   source and restore it in guaranteed cleanup on success, failure or timeout.
   Record the mutation, selected case and assertion result. A build failure or
   runner timeout leaves the mutation check inconclusive.
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
6. Switch callers after parity and the owning repository's required platform and performance
   checks pass. Apply the repository's cutover and recovery policy.
