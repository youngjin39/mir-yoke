# Mechanical handoff packet

Design authority: the current owner writer brief for the 0.13.22 round-i checker
defects (2026-10-23, decision 1562831233971392553, parent-supplied), recorded in the
Harness active cursor's `Current` section. The bounded writer scope leaves that
cursor unchanged. This extends the stateless design recorded in `tasks/plan.md`;
ADR-90 amendments through 2026-10-23b admit the bounded events
and checks. Installation grants no agent authority. Semantic evidence remains
`.mir/ontology-map.json#/domain/invariants/2` and its referenced ADR-90.

## Events, runtime evidence and budgets

Both plugin manifests auto-discover the common `hooks/hooks.json`. It registers
UserPromptSubmit (supply), PreToolUse (owner command/file-write guards) and Stop (check),
each with an 8-second host budget and
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
prompt clears any prior assistant candidate. Codex repair messages wrapped
in `<hook_prompt hook_run_id="...">` are native feedback, not new owner prompts;
retain the original scope and current-turn tool evidence. The last native prompt and final
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
continuations. Parenthesized heading qualifiers and standalone headings are
accepted; `Not read` / `Protected` sections also identify denied citation scope.
Repeated sections accumulate, preserving spelling. Fenced or
quoted examples are ignored. Unmarked pasted material cannot be attributed
reliably. Sources are explicit semicolon/comma/newline-separated paths (at most
16), relative to the repository root; never harvest paths from arbitrary prose.
Refuse escaping paths, `.env*`, `secrets`, `.mir/memory.db*`, resolved symlink
targets in these locations, and excluded source values. The cited-path collector
also reads `.mir/repo-profile.toml`, when present, and skips glob matches from
`paths.protected_paths`, `paths.secret_paths` and `boundaries.secrets`. An absent,
unreadable or malformed profile fails open; built-in exclusions still apply.
It does not open protected files.

Explicit prose prohibitions (`do not`, `don't`, `never`, no commands/file changes/
scratch writes, commands/writes forbidden/prohibited) and Korean negative/forbidden
forms such as `sujeonghaji malgo` are copied verbatim into May not. Recognition
uses the native Korean spelling, not this transliteration. It is conservative
and sentence-based (a period followed by whitespace, the line end or Hangul ends
a sentence, so `CONTEXT.md` stays whole): only the prohibiting sentence is
copied. Korean command prohibitions include native spellings of `-ji anko`,
`myeongnyeong silhaeng eopsi`, `-ji ma` and `-ji malgo`. A request to include
the prohibition scope, or an attributed negative subordinate clause, is not
itself copied as a prohibition. Recognition remains lexical, not a general
language parser. Only owner prohibition sentences determine a command ban, after
removing quoted/backticked literals. Fences and blockquotes stay ignored. A packet's
`Do not run the "Never run" commands above` sentence refers to listed examples;
it does not forbid local revision/digest comparisons. Command prohibitions skip
both supply and Stop runners. A prohibition
on file/scratch writes does not skip this read-only, stateless hook.
Unlabelled owner prose such as `Do not run commands; answer from the sources.`
or `No commands. Read only.` still establishes a command ban.

## Supply and authority check

Supply injects the complete runner `handoff pins:` JSON block unchanged, except
its terminal newline, plus `Prompt SHA256:` computed from the exact native prompt.
Copy both verbatim. Separately inject the owner's may/may-not text as
**copy verbatim; do not add permissions**. No explicit authority sections means
read/inspect authority only. Explicit sections confer only the labeled grant.
Exclusion literals remain author context and must never enter forwarded text.
The explicit Exclude section retains literal, semicolon-separated values.
Also extract quoted/backticked literals following English `do not include/forward/copy`
or `author-only marker`, or preceding Korean forms of `do not forward/include/copy`.
Unquoted identifiers matching `[A-Z][A-Z0-9_]{3,}` are also excluded after
`do not forward/include` or before `must not be forwarded`. Korean identifiers
may directly precede an optional topic/object/subject particle and
`\uc804\ub2ec\ud558\uc9c0 \uc54a` / `\uc804\ub2ec\ud558\uc9c0 \ub9d0` /
`\ud3ec\ud568\ud558\uc9c0 \uc54a` / `\ud3ec\ud568\ud558\uc9c0 \ub9d0`.
An allowed identifier elsewhere in the sentence is not excluded. Other unquoted
prose is not inferred as an exclusion. Use synthetic stand-ins in tests;
never copy author-only content from a capture. Refuse supply if pins contain excluded data.

With explicit authority sections, split candidate grants on semicolons/newlines;
normalize case, spacing and punctuation, preserving word/path order. Each
action candidate must be a contiguous lexical substring of an owner grant, and cannot
contain an explicit denied item. `none`, `no permissions`, `unavailable` grant
nothing. Safe read/inspect text without action verbs is accepted, including
read-only synthetic-source descriptions. Explicitly conditional future grants
(`only after a separate owner grant`, `if/once explicit owner authorization`)
and explicit Korean separate-approval conditions do not confer current authority
and are skipped. Possibility statements are not permission grants. Separate current grants on
the same line remain checked. Without explicit sections, require a read/inspect verb and reject action
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
May-not qualifiers are not scanned as positive inline grants. Colon labels
accept bullets and bold markup; envelope fields also accept bullet markers.
Evidence provenance/time keywords are case-insensitive and may share one line.
Restriction comparison normalizes whitespace, case, punctuation and bullet
markers. Self-check field and pin names may omit the literal `field`/`pin` prefix.
Arbitrary semantic paraphrases remain outside this lexical checker.

## Packet check and bounded repair

Recognize an emitted packet by `Qualified target:`, `handoff pins:`, `May not:`,
a forwarded `pin_inventory`/`mapping_sha256` key or a handoff/brief heading line
(English or Korean), so translated or relabelled packets are still checked.
Require namespace:local-id; nonempty Lifecycle, Temporal, Epistemic, Verification;
full pins; Evidence provenance and ISO-8601 observation time; Unknowns; May;
May not; Self-check. Preserve each owner prohibition except those containing
excluded literals. Reject exclusions anywhere in the final artifact, including
wrappers and restrictions; redact excluded values in diagnostics.

Read the local `.mir/ontology-map.json` namespace for author, recipient and
no-command checks. A differing qualified-target namespace produces
`qualified target namespace <ns> differs from map namespace <map>`.
An optional `namespace_aliases` array admits an alias only as an object with
`namespace`, `reviewed: true` and a nonempty `evidence` string. Plain aliases,
similar names and capability-pack aliases confer no namespace equivalence.
This is a declaration check, not verification of the review evidence. Missing,
unreadable or malformed maps fail open for this check; no runner or write is needed.
Author target checks, recipient detection and namespace checks share the target label
form. Korean examples here use Unicode escapes. Accept parenthetical bilingual labels
such as `\ub300\uc0c1(Qualified target):`,
`Qualified target (\ub300\uc0c1):` and `**\ub300\uc0c1 (Qualified target):**`.

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
When the supplied JSON is present but its header became a Markdown heading or
another label, report `supplied pins header altered (keep the literal 'handoff pins:' line)`.
The header must be a complete literal line immediately before the JSON.

Every other existing repository file the packet cites (relative path; protected, excluded,
symlinked, map and runner paths skipped; at most 32) must carry its own sha256 and
last-change revision. Stop runs the runner once more for those paths within the shared
budget and names each file whose digest or revision is absent. Supply asks for them up
front. Add them to the packet's source list, not as a second pins block.
Paths in the owner's May not or the packet's May not / Not read / Protected
sections, and explicitly not-read prose, are not harvested as citations.

Self-check individually lists `field NAME=present/missing/abbreviated/unchecked`
for qualified target, four status axes, evidence, unknowns, may and may not;
`pin NAME=parent-supplied/verified-in-repo/missing/abbreviated/unchecked` for each
`pin_inventory[].pin`. Each exact unknown pin reason must appear individually.
These labels are claims, not proof of evidence truth.

On clear defects, Stop emits `decision=block` with missing/extra items. When
`stop_hook_active=true`, a second block is permitted only if current-turn native
transcript rows establish exactly one previous block from this handler. Count
Claude system `hook_response` or Codex `event_msg.hook_response` Stop output, or
Claude meta-user feedback, bearing this handler's repair reason. Codex
`response_item` user `<hook_prompt>` and `event_msg/item_completed` `HookPrompt`
fragments bearing a Stop run ID and this handler's repair prefix also count;
deduplicate their two views by `hook_run_id`/`hookRunId`. Assistant text
quoting a decision is not evidence. Unknown record shapes or an indeterminate
count retain the warning/allow behavior. Two recorded blocks always allow the
next Stop; no third block is emitted. No persistent counter is used.

The second block names only deterministic defects: missing cited-source digests
or revisions, abbreviated hex pins, missing recipient pin labels, qualified-target
namespace mismatches, excluded items and undisclosed command-ban compliance failures.
A mismatch first exposed after a target-label
repair can therefore trigger the one second/final block. Field headings, extra grants,
computing evidence and limitation prose
are first-block checks only. A missing/nonboolean retry flag warns/skips because
bounded behavior cannot otherwise be guaranteed without state. Non-packet
responses (including clarification) are untouched. Stop cannot undo earlier tool
publication or inspect file artifacts.

Every block reason (first author block, recipient block and second/final block)
ends with the following sentence. UserPromptSubmit supplies the same rule once,
including recipient and no-command guidance:

> Re-send the complete corrected artifact as your final message; it replaces the previous one, so do not send only the changed sections.

The final message is the complete replacement artifact. This is an instruction
change only; no heuristic attempts to detect partial repairs.

## No-command Stop subset

When the owner forbids commands, retain the unavailable-pin warning
`pins/check unavailable: owner forbids commands; no runner performed.` and never
invoke either runner. Stop still checks the whole emitted artifact for owner
exclusions, extra may grants using the same lexical rules, and unsupported
`verified-in-repo` claims. Every such pin/path needs a this-turn Read/Grep/Glob
reference to its path; a declaration in the mapping is not a reader reference
to the contract file. An unresolved pin path cannot be claimed verified.
For `head`, a this-turn Read of `<root>/.git/HEAD` counts, optionally accompanied
by a Read of the ref file it names. For `repository_root`, any this-turn
Read/Grep/Glob path inside the repository root counts. Relative paths resolve
against that root; an unrelated path outside it does not count, including a
sibling repository whose name starts with the same root string. These rules
also apply to recipient accounting when commands are forbidden. They establish
reference provenance, not the resolved commit value or hash computation.

Reject 7–39 hex characters presented as a full HEAD, revision, commit or digest,
including `path@revision` and Markdown pin-table columns, unless explicitly
inventoried as `abbreviated`. The inventory must identify the pin, or label the
value's own line. This subset requires no English field labels and accepts
translated packets and Korean permission labels. It does not require fresh
pins, English status headings or prompt hashes; the current owner prompt still
governs the subset if an old prompt hash appears. The same two-block bound
applies; only exclusions, abbreviated pins, qualified-target namespace mismatches
and undisclosed command-ban compliance failures can trigger its second block.

## Recipient accounting and owner no-command guard

A qualified-target heading/label (`Qualified target` or native Korean `daesang`) followed
on the same or next three lines by `namespace:local-id`, plus a pins block or
full sha256 pin lines, is a received packet. Without pins, require at least two
other handoff-field categories: status axes / `sangtae`, pins / `pin`, unknowns /
`mihwagin`, authority / may / may not / `heoyong` / `geumji` (native Korean
spellings, shown here as transliterations). Authoring `detect()` takes
precedence. UserPromptSubmit supplies the
recipient rule without invoking a runner. At Stop the recipient must label
all eight base pins (`repository_root`, `head`, `mapping.identity|version|digest`,
`contract.identity|version|digest`) and every named packet/source/inventory pin as
`verified-in-repo`, `parent-supplied` or `unavailable`, for example
`pin sources[0].digest=parent-supplied`. Both `handoff pins:` and `Pins:` JSON
blocks are accepted, including a JSON fence. For sha256-line packets, use the line's
name before its first colon. Markdown table rows also count when one cell names a
base/source pin (for example `head`, `mapping.digest` or `sources[3].revision`) and
another cell contains its label, with optional emphasis/backticks. Column order is
irrelevant. Pins without values still require a label. Prose words `reason`, `reasons`
and `\uc774\uc720` (Unicode escapes), and summary `sha256`/`revision` headers are not pin names and never add
label requirements. Labels account for claims; they do not prove hashes.

Verified-path scanning excludes version strings such as `1.1.0`, qualified IDs
such as `namespace:local-id`, and structured base/source pin keys. Actual file
references on the same line still require a tool reference.

Each source path claimed `verified-in-repo`, including paths inferred from the
packet's source pin names, must have a tool reference in this turn's transcript:
Claude `Read`/`Grep`/`Glob` with a matching `file_path`/`path`/`pattern`, or shell
command text containing the path.
`repository_root` accepts a this-turn Read/Grep/Glob path inside the root using
the same containment rule as the no-command subset.
The root `mapping --handoff` runner also counts as a map reference. Claude
`tool_use` and Codex `response_item.function_call` records are recognized.
Codex `response_item.custom_tool_call` named `exec` (including a dotted name)
counts as a tool call; its static nested `tools.exec_command` and other supported
shell calls expose literal `cmd`/`command` arguments, paths and computations.
Static nested shell and interpreter calls count as commands even with dynamic
arguments or no arguments. Recognize the same nested calls in native `tool_use`
and `function_call` exec inputs. Interpreter code supplies no Read/Grep/Glob evidence.
Tokenize JavaScript without executing it; ignore comments and quoted decoy calls.
Single/double quotes and static backtick strings are supported, with escapes
decoded. Dynamic expressions, variable-built commands and interpolated templates
provide no computation evidence. The outer call still counts for the local-tool
inventory. A new
native user prompt discards earlier references. A digest pin additionally needs
a this-turn command computing SHA256 over that path: `shasum -a 256`, `sha256sum`,
`openssl dgst -sha256`, `hashlib.sha256`, or the root `mapping --handoff` runner.
A revision needs `git log`/`git rev-list` naming its path or that runner naming
the source. When commands are permitted, HEAD needs `git rev-parse` or the runner.
The runner also covers map
and contract pins. A Read alone verifies neither hashes nor revision history.
This checks command/reference provenance, not tool success, comparison results
or semantic truth. When commands are forbidden, recipient accounting uses the
no-command reference rules above instead of requiring computing commands;
`contract.*` still requires a reference to the contract file itself.
If commands are permitted but no tool call exists, explicitly
state a local-check limitation; otherwise report `no local check and no stated limitation`.
If commands are forbidden and neither a reader nor a command tool was called, the final
answer must explicitly say commands are forbidden and no non-command reader was
used/available, in English or Korean. If a shell or interpreter was called under
the ban, the artifact must instead state that execution as a `compliance failure`
(or Korean instruction-violation/compliance-failure wording). The acknowledgement
must mention commands, an interpreter, a shell or a recorded command tool on the
same line. This is lexical disclosure checking, not semantic acceptance. Its reads
do not count as non-command reads, and paths/pins supported only by that call must
not be labelled `verified-in-repo`. Stop requests failure disclosure rather than
asking for an untrue statement that no reader was used. A separate permitted reader
does not erase the failure. Undisclosed failures join the deterministic second-block
set; computing/limitation defects remain first-block checks only.

When the owner forbids commands, file changes or both, UserPromptSubmit adds the
matching sentence once in author and recipient guidance (a file-only ban never
mentions shell, because command-permitted packets still need the pins runner):

> Shell tools and code interpreters (for example node_repl or a Python REPL) must not be called in this turn; attempts are compliance failures even if denied.

> Write/Edit/apply_patch and file-writing tools must not be called in this turn; attempts are compliance failures even if denied.

PreToolUse recomputes the prompt from native `prompt` or the explicit transcript
tail, without state. Only authoring/recipient handoff turns with an owner command
prohibition deny shell tools: `Bash`, `shell`, `shell_command`, `exec_command`,
including dotted names such as `functions.exec_command`. The same ban covers
code interpreters: `js`, `js_reset`, `mcp__node_repl__js` and Python/JS REPL
names, including MCP names containing `node_repl`, `python`, `python_repl`,
`js_repl` or `javascript_repl` namespace segments. Code-mode `exec` is denied
only when its static input contains a supported `tools.<shell/interpreter>(`
call. Use the same tokenization as command evidence: ignore comments and quoted
decoys, never evaluate JavaScript. Calls that only list/filter `ALL_TOOLS` or
call non-interpreter tools pass this command guard. Dynamic tool names and
indirect aliases are outside this static recognition. Owner file-change
prohibitions also deny `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and Codex
`apply_patch`, including dotted names. Read/Grep/Glob and ordinary turns pass.
Only unqualified file-write bans activate this guard, such as `May not: write files.`,
`No file changes`, `\ud30c\uc77c \uc218\uc815 \uae08\uc9c0` or `\ud30c\uc77c\uc744 \uc218\uc815\ud558\uc9c0 \ub9d0\uace0`.
A scoped prohibition (`outside`, `other than`, `except`, `beyond`, `besides`,
`under`, `in`, `not listed`, `only`, `\uc678`, `\ubc16`, `\uc774\uc678`, `\uc81c\uc678`, `\ubc94\uc704 \ubc16`)
does not ban all writes or supply the forbidden-tool sentence. Check separate
sentences, semicolon items and lines independently so a scoped prohibition
does not hide an additional unqualified ban. This guard does not enforce paths.
The shell guard does not classify arbitrary tools that might write files;
the supplied instruction covers those attempts. Payload/transcript errors in
PreToolUse fail open silently, as the guard runs on every matching tool call.
Denial emits `hookSpecificOutput` with `hookEventName=PreToolUse`,
`permissionDecision=deny` and `permissionDecisionReason`, plus stderr and exit 2.
Claude consumes the deny JSON; exit 2 is the shared blocking convention used by
both local CLI guards (`pre-tool-use.sh` and `env-read-gate.sh`). Offline fixtures
check native transcript shapes and this exit/output contract; they do not
establish fresh live-host delivery or activation.

## Delivery boundary

0.13.22 source prepares round-i exclusions, code-mode accounting, retry feedback,
quoted-command handling, namespace checks and file-write guards.
Python 3.9 remains supported with
optional `tomllib`; absent parsing still skips only the Profile glob filter.
Main still owns generated Codex
surfaces, digest acknowledgement, locks/binding and any live-host verification.
This work performs no bind, tag, push or release. A prepared version is not activation.
