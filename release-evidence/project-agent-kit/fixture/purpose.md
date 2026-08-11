Build a Python 3.12 command-line application that audits local Markdown links in a repository.

Goals:
- report broken relative file and heading links deterministically;
- operate offline and never modify the audited repository; and
- provide machine-readable output suitable for a future CI integration.

Constraints:
- use uv for the project environment;
- keep the future product implementation small and cross-platform; and
- do not design or implement the product during the harness bootstrap.
