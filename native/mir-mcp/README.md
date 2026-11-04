# Native MCP core (M1a + M1b)

This independent crate avoids the lifecycle crate's unrelated SQLite and executor
dependencies. Its dependency tree builds offline without derive macros.
The Python server remains the default entrypoint; no distribution surface changes.

Run `mir-mcp --reference-python <interpreter> --reference-script <mir_mcp.py>`.
Both paths are explicit caller configuration. The core owns newline framing,
limits, protocol state, discovery, listing and RPC errors. The embedded tool
inventory is a frozen copy of the Python inventory. Byte transcript tests detect
inventory and version drift.

`handoff_pins` runs natively. The other four tools start an isolated Python child
with `--internal-reference`. That mode enters the reference directly, treats
legacy negotiation as complete, refuses any other argument, and never selects a
native backend, so a forwarded call cannot recurse. The native parent forwards the
original request bytes, closes child stdin, and returns the single response bytes
unchanged. Spawn, input, output and wait share one ten-second deadline. Each pipe
is capped at 16,384 bytes; a refusal kills and reaps the child. There is no retry.
Output overflow, child failure, malformed output and deadline expiry produce
stable tool errors, followed by continued service.

Processing is sequential, including ignored cancellation notifications, as in the
reference. EOF exits successfully; there is no shutdown handshake. Broken output
pipes exit successfully. The supported reference launch uses `-u`; buffered
Python can report a finalizer flush failure after catching a broken pipe.

Discovery, inventory, framing and stable errors are tested byte for byte. Ordinary
RPC object order is not a semantic requirement, but the tests preserve it too.
Forwarded child response bytes remain under the reference's ownership.
Native handoff uses ordered compact JSON and padded URL-safe Base64 cursors.
Number parsing preserves integer IDs; other numbers
are validated and represented by type in the core, while raw forwarded bytes
retain their full precision. Native handoff tests validate observation timestamps
independently and compare bytes after substituting only that clock field.

Build with `cargo build --offline --locked --manifest-path native/mir-mcp/Cargo.toml`.
Set `CARGO_HOME`, `CARGO_TARGET_DIR` and `TMPDIR` to approved cache/scratch locations.
For the Python oracle, set `MIR_MCP_NATIVE_BINARY` to the built binary and run
`uv run --no-sync pytest tests/test_mir_mcp_native_core.py`.
The tests use hermetic subprocesses, never installed plugins or live clients.

Native handoff reads use a pinned root and component handles, bounded regular-file
reads, built-in and profile protection patterns, source stamps, and replacement
checks. Limits are 1 MiB per file, 4 MiB total, 256 reads and distinct files, and
10 seconds per call. Each handoff call runs in a native worker process using the
argv-only internal mode. The parent kills and reaps an expired worker, returns
`E_TIMEOUT` and continues serving. This also bounds operations that never return
to a guard check. The worker cannot forward tools or recurse. Git shares the
call deadline with a one-second response reserve. Its executable, argument forms,
configuration overrides and environment are fixed; both pipes share a 65,536-byte
capture budget. Metadata redirections and execution-capable config are refused.

Cursor bindings include tool, canonical root, arguments excluding cursor, ordered
source stamps/digests, and bundled contract digest. Pages shrink to 15,360 bytes;
an indivisible page refuses with `E_LIMIT`. Page inventories are recalculated
while retaining full-result unknowns. Cursors work across Python/native process
boundaries when their complete inputs remain unchanged. Distribution and runtime
selection remain unchanged.
