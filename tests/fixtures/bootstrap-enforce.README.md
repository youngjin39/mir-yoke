# Incomplete-bootstrap reference freeze

Authority: the owner's W1-Y6b(1) brief. The unmodified
.claude/hooks/_lib/bootstrap-gate.sh is the oracle; its SHA-256 is in
bootstrap-enforce.json. No caller is switched. The current maintainer cursor
is intentionally untouched under the owner's explicit file restriction.

The fixture shares ten synthetic repository setups (greenfield/adoption,
missing/pending/restart/invalid/ready), then records 1,848 independent invocations.
The state/tool/path product has 1,080 records. Other records cover command
grammar, Git staging and detached worktree creation, provider identity/revision/
cleanliness, working directory checks, patch fields/deletion/moves, and exact
instructions with and without adoption evidence. Each record pins status,
stdout/stderr bytes and the absence of project filesystem changes.

Supplementary records check scalar surfaces, null surfaces, multiline provider
profiles, composite instruction pins (including ordered duplicate keys), and
empty HOME/TMPDIR fallbacks. These were
captured from the same shell source after read-only security review.

The capture driver remains in task scratch. It sources the real shell file,
uses the fixed POSIX tool allowlist from tests/w1_golden.py (including jq),
private fake Git/uv/receipt-bound CLI, and isolated home/temp/project directories.
Payload placeholders are expanded before execution; only temporary root and
repository path substitutions are normalized afterward. No clocks or diagnostic
text are normalized. No existing frozen expected bytes are changed.

Two missing-jq records preserve the retired shell dependency diagnostic. Both
replay suites explicitly identify these records; all remaining native records
run without jq or any POSIX utility on PATH. The private fake Git and the pinned
CLI are still executable for repository/runtime checks. This proves neither
real Windows execution nor removal of the shell adoption source.
