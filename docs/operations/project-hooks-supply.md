# Explicit project-hooks supply and dormant native declarations

The provider CLI offers `scripts/mir.sh project-hooks install --project-root .`
and `scripts/mir.sh project-hooks check --project-root .`. The target is explicit;
these operations do not activate hooks or change registrations.

Release metadata lives in `config/project-hooks-provider.json` and is packaged as
`mir/resources/project-hooks-provider.json`. Pins require an immutable provider
source revision and the existing per-host artifact URL, size and SHA-256 fields.
The CLI reads that package resource, never a developer checkout capability lock.
The initial resource has no released pins: install/check report degraded, return
1 and create no files. Installed package bytes define the metadata revision;
there is no branch/latest lookup. Existing executor sync retains its own lock route.

Successful installation uses the existing placement helper and the existing
`.mir/bin/project-hooks.json` receipt shape (`path`, `sha256`). Check requires
matching artifact bytes, executable permission, receipt and compact capability.
An explicit supply operation may retrieve pinned bytes. Hook commands never fetch.

## Rendering without activation

Schema v1 script rendering remains unchanged. Schema v2 requires exactly one
`script` or `native` declaration per hook. For example:

```json
{
  "native": {"executable": ".mir/bin/project-hooks", "args": ["pre-compact"]},
  "timeout": 60,
  "statusMessage": "Project PreCompact checkpoint"
}
```

Only exact event argv is accepted: PreCompact `pre-compact`, PostCompact
`post-compact`, SessionStart with matcher `^compact$` `compact-resume`, and
SessionEnd `session-end`. No canonical registration uses this form yet.

Render/check with `--platform posix` (default) or explicit Windows profiles:
`--platform windows --shell git-bash|powershell|pwsh|cmd`. The derivative generator
accepts and forwards the same flags. Projects must preserve their chosen profile
in both render and parity invocations when adopting native declarations.

On POSIX, the emitted handler invocation is
`CLAUDE_PROJECT_DIR="$project_root" "$native" pre-compact`, where `native` is
`$project_root/.mir/bin/project-hooks`. Windows Git Bash uses the same guard and
argv with `.exe`; PowerShell emits `& $mirBinary pre-compact`; CMD emits
`"!_mir_binary!" pre-compact` inside a CMD-specific guard. These excerpts omit
required guards and must not be used as standalone registrations.

Claude requires nonempty `CLAUDE_PROJECT_DIR`. Codex resolves the Git project root
from the working directory. Guards reject missing/non-executable/linked binaries
and linked placement directories. Warmup uses null stdin and suppressed output;
only the handler receives event stdin. Missing root, disabled native, failed
warmup and statuses 64/126/127 report unavailability on stderr and return 0.
Other handler statuses pass through. Per-invocation guards establish launchability,
not artifact integrity; explicit supply/check establishes the pinned bytes.

The repository SessionStart and durable-edit launchers additionally require
`mir-project-hooks-session-start-v2` and
`mir-project-hooks-post-edit-memory-sync-v1`, respectively. The legacy
SessionStart v1 marker does not certify the native renderer. Unavailable,
disabled, linked or outdated binaries leave visible bootstrap and safety context
on SessionStart stdout, or a skipped-sync diagnostic on PostToolUse stderr.
Both identify `scripts/mir.sh project-hooks install --project-root .` as the
explicit repair operation; it requires released provider pins as described above.
These degraded paths never fetch binaries or run the retired Python handlers.

Durable-edit payloads use a bounded reader of 16 MiB plus one sentinel byte.
This admits large Write and patch events above the general 1 MiB hook-parser
limit while bounding JSON decoding memory. An unreadable or larger payload
produces a diagnostic and returns non-blocking status 0; after repair the operator
can run `scripts/mir.sh context sync` to rescan durable documents.

Windows command tests are structural evidence only. Windows shell parsing, stdin,
client discovery and timing still require a Windows host. No cross-platform
retirement or registration readiness follows from rendering.
