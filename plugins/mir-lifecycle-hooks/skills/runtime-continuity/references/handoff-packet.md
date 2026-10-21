# Mechanical handoff packet

Design authority: the current owner brief and its stateless rework addendum,
recorded in the repository-owned `tasks/plan.md`. The dated 2026-10-22 ADR-90
amendment admits this exact implementation. Installation grants no agent authority.

## Events, runtime evidence and budgets

Both plugin manifests auto-discover the common `hooks/hooks.json`. It registers
UserPromptSubmit (supply) and Stop (check), each with an 8-second host budget and
the exact `skills/runtime-continuity/scripts/handoff_packet.py` handler. SessionStart
and its 2-second timeout stay unchanged. Ordinary prompt-submit turns do detection
only: no output, path discovery, runner call or file operation. Stop must read the
explicit transcript tail to detect the current turn; ordinary turns then return
silently without running the pin supplier.

No target adapter, environment configuration, state directory, state file or
other write is used. No network, model, Memory Keeper or agent is called. The
handler walks upward from native absolute cwd to the nearest `.git` marker (file
or directory), then invokes only that root's `scripts/mir_ontology.py` with Python,
`mapping --handoff <paths>`, argv, no shell. A missing repository/runner warns and
skips; no installed-runner or environment override is accepted. The only child
is this runner; it has a 5-second deadline, process-group kill/reap on timeout,
`PYTHONDONTWRITEBYTECODE=1` and `GIT_OPTIONAL_LOCKS=0`. Its supported mapping
operation is read-only/offline; the target owns its local runner implementation.

Native payloads use `hook_event_name`, `cwd` and prompt-submit `prompt`. Stop
requires `transcript_path` and boolean `stop_hook_active`. Read only the final
1 MiB of that explicit regular JSONL file; discard a partial leading record.
Never scan session directories. When the native Stop payload carries a nonempty
`last_assistant_message`, check it instead of the tail's assistant text: round f
showed the transcript can lag behind the final message (5/10 Claude runs).
Support Claude `user`/`assistant` message records and Codex `event_msg.user_message`
and `response_item` user/assistant text records (`final_answer` or absent phase).
Ignore Claude meta/tool-result records and Codex commentary. A new native user
prompt clears any prior assistant candidate. The last native prompt and final
assistant must be in the bounded tail. A missing prompt, malformed/truncated tail,
missing retry flag, runner error/timeout, or other hook error fails open with
stderr plus a visible `systemMessage`. Do not echo exceptions or child stderr.

These events and shapes are evidenced by Yoke's shared project-hook source and
offline native-shape fixtures. They are not fresh live-host verification. A host
without either event has no corresponding supply/check; without the explicit
transcript or retry flag, checking warns and skips. Do not claim runtime parity
from fixtures. This preparation does not change runtime bindings or receipts.

## Detection and owner grammar

Recognize an unquoted imperative line beginning with optional `Please`, then
`write/prepare/draft/create/give/send`, then `handoff/brief`, then `agent`, `Codex`
or `Claude`; also `delegate ... agent/Codex/Claude`. Two narrow Korean patterns
recognize (a) another/next/sub agent, then handoff/brief/instruction text
(`jisimun`, `ingyemun`), then an instruction to write it, and (b) that text,
then "to another/next/sub agent", then a pass/hand-over verb. Skip fenced code, blockquotes, English negative imperatives and the
recognized Korean negative write/delegate form. Indirect or reordered requests,
other languages, file/tool-only handoffs and cross-turn requests may be missed.
Unmarked imperative examples can trigger falsely. This is a narrow detector,
not a general natural-language intent classifier.

Parse case-insensitive `May:`, `May not:`/`May-not:`, `Sources:`, `Exclude:`/
`Do not forward:` with optional Markdown heading/bold/bullets and bullet
continuations. Repeated sections accumulate, preserving spelling. Fenced or
quoted examples are ignored. Unmarked pasted material cannot be attributed
reliably. Sources are explicit semicolon/comma/newline-separated paths (at most
16), relative to the repository root; never harvest paths from arbitrary prose.
Refuse escaping paths, `.env*`, `secrets`, `.mir/memory.db*`, resolved symlink
targets in these locations, and excluded source values. Additional target-local
protected paths are not inferred.

Explicit prose prohibitions (`do not`, `don't`, `never`, no commands/file changes/
scratch writes, commands/writes forbidden/prohibited) and Korean negative/forbidden
forms such as `sujeonghaji malgo` are copied verbatim into May not. Recognition
uses the native Korean spelling, not this transliteration. It is conservative
and sentence-based (a period followed by whitespace, the line end or Hangul ends
a sentence, so `CONTEXT.md` stays whole): only the prohibiting sentence is
copied, and unsupported negations (for example `-ji anko`) are missed. Command prohibitions skip the runner. A prohibition
on file/scratch writes does not skip this read-only, stateless hook.

## Supply and authority check

Supply injects the complete runner `handoff pins:` JSON block unchanged, except
its terminal newline, plus `Prompt SHA256:` computed from the exact native prompt.
Copy both verbatim. Separately inject the owner's may/may-not text as
**copy verbatim; do not add permissions**. No explicit authority sections means
read/inspect authority only. Explicit sections confer only the labeled grant.
Exclusion literals remain author context and must never enter forwarded text.
Exclusions are literal, semicolon-separated values; natural-language exclusions
are not inferred. Refuse supply if pins contain excluded data.

With explicit authority sections, split candidate grants on semicolons/newlines;
normalize case, spacing and punctuation, preserving word/path order. Each
candidate must be a contiguous lexical substring of an owner grant, and cannot
contain an explicit denied item. `none`, `no permissions`, `unavailable` grant
nothing. Without explicit sections, require a read/inspect verb and reject action
classes below. Preserve owner wording: containment can reject safe paraphrases
and can miss a shorter phrase that loses a scope restriction. It is not semantic
authorization proof.

Default-denied English stems: edit, modify, change, write, create, delete, remove,
run, execute, test, check, install, commit, push, network/internet, delegate/spawn,
deploy/release. Default-denied Korean classes cover modification/editing,
writing/creation/deletion, execution/performance, checks/tests, installation,
commit/push, network/internet, delegation/invocation and deployment. Read/inspect
allows English `read`, `inspect` and Korean forms of reading/viewing. Native
spellings are explicit in the handler's `ACTION` and `READ` regexes. Substrings
or filenames containing these words can be false positives; euphemisms, synonyms
and novel inflections can be false negatives. Unsupported grants without a
read/inspect verb are rejected by default. Also inspect enclosing English
`you/recipient/agent may ...` statements and recognized Korean permission endings.
Arbitrary prose, tools and actual actions are outside this lexical checker.

## Packet check and one-shot repair

Recognize an emitted packet by `Qualified target:`, `handoff pins:`, `May not:`,
a forwarded `pin_inventory`/`mapping_sha256` key or a handoff/brief heading line
(English or Korean), so translated or relabelled packets are still checked.
Require namespace:local-id; nonempty Lifecycle, Temporal, Epistemic, Verification;
full pins; Evidence provenance and ISO-8601 observation time; Unknowns; May;
May not; Self-check. Preserve each owner prohibition except those containing
excluded literals. Reject exclusions anywhere in the final artifact, including
wrappers and restrictions; redact excluded values in diagnostics.

Stop recomputes the prompt SHA256 from the last native user prompt. A mismatched
full hash warns/skips rather than using stale authority; a missing hash is a
repairable field defect. Stop reruns the supplier. Every pin field and canonical
JSON byte must match the fresh result, with one necessary exception: the supplied
`observed_at` must remain an ISO timestamp because a fresh read changes time.
With no persisted supply state, the hook cannot attest the original observation
timestamp or prove an unchanged initial block if repository state changed between
hooks. Changed source/HEAD/map/contract pins are named by JSON pointer for repair.
The final packet must still carry the original complete supplied block; if pins
are stale, regenerate the packet from current evidence rather than silently
altering individual values. This limitation follows from stateless recomputation.

Self-check individually lists `field NAME=present/missing/abbreviated/unchecked`
for qualified target, four status axes, evidence, unknowns, may and may not;
`pin NAME=parent-supplied/verified-in-repo/missing/abbreviated/unchecked` for each
`pin_inventory[].pin`. Each exact unknown pin reason must appear individually.
These labels are claims, not proof of evidence truth.

On clear defects, Stop emits `decision=block` with missing/extra items once.
When `stop_hook_active=true`, warn and allow completion without running the
supplier or blocking again. A missing/nonboolean retry flag warns/skips because
one-shot behavior cannot otherwise be guaranteed without state. Non-packet
responses (including clarification) are untouched. Stop cannot undo earlier tool
publication, inspect file artifacts or prove recipient behavior.

## Delivery boundary

0.13.14 source prepares the admitted inventory. Main still owns generated Codex
surfaces, digest acknowledgement, locks/binding and any live-host verification.
This work performs no bind, tag, push or release. A prepared version is not activation.
