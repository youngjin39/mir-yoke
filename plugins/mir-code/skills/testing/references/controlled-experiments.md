# Controlled experiments

Inspired by karpathy/autoresearch at 228791f.

Use for an authorized, bounded performance comparison, not routine correctness checks.

1. Declare the mutable candidate, immutable evaluator and data, resource budget,
   hardware and runtime versions. Fix a finite experiment count or spending limit
   before Main dispatches any work.
2. Measure an unchanged baseline first. Compare candidates using the same data,
   evaluator and conditions; record variation where repeated measurements are needed.
   Separate startup and evaluation overhead from the measured work. Equal wall time
   on different hardware does not prove comparable compute or performance.
3. Append to the target's existing evidence log: candidate identity, hypothesis,
   metric and units, resource use, conditions and outcome. Record crashes as failed
   attempts; never encode them as an apparently superior metric. If a run
   exceeds its declared budget or timeout, stop it and record a failed attempt;
   never score it.
4. Weigh measured gain against complexity and maintenance cost. Main recommends the
   disposition and owns dispatch under the target's authority; a metric alone does
   not select, retain or authorize a change.

Keep this procedure advisory. Do not disable permissions, continue indefinitely,
commit/reset autonomously or automatically retain candidates. Add no training
scripts, runner, model escalation or separate results cursor.
