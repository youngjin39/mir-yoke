# Porting with parity

Use the owning repository's port criteria. Pin the existing implementation for parity and retain a runnable reference until acceptance.

1. Capture golden fixtures covering stdin bytes, args and relevant environment.
   Include successful, empty, malformed, boundary and failure inputs and Unicode
   text. Capture stdout bytes, stderr bytes and exit code from the reference.
   Reject duplicate frozen case names and invalid witness inputs. If many comparisons match unexpectedly, verify that the generator changed the inputs.
   Include Python/Rust boundary cases for Unicode, line splitting, exceptions, serialization, and paths.
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
6. Switch callers after parity and the owning repository's required platform and performance
   checks pass. Apply the repository's cutover and recovery policy.
