# Local Safety Pack

This repository explicitly adopted Mir Yoke's safety pack. The copied hook is repository-owned.
Review `.claude/settings.safety.example.json`, merge only the needed entries into the local runtime
configuration, and keep protected paths aligned with the repository's canonical contract.

The hook fails closed only for deterministic protected-path, Git-internal, direct destructive
command, and credential-text findings. Unknown shell syntax is not treated as destructive merely
because it cannot be classified.
