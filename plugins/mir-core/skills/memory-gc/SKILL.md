---
name: memory-gc
description: "Inspect an explicitly configured repository memory store for expired facts and apply garbage collection only after a user-approved dry run. User-triggered only; never run automatically."
---

# Memory GC

1. Locate the repository-owned memory schema, command, and expiry field. Do not assume a database,
   file path, CLI, or `valid_to` convention.
2. If the repository declares no compatible memory GC interface, report that the operation is not
   configured and stop without mutation.
3. Run the repository's declared dry-run command and report the exact candidates and count.
4. Apply expiration only after the user explicitly approves that result and only through the
   repository-owned command or documented transaction.
5. Re-run the dry run and integrity check after apply; report the changed count and failures.

Never invent a memory command, edit an unknown store directly, expire records without the declared
date semantics, or treat missing configuration as successful GC.
