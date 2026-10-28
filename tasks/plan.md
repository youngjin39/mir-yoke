# Plan

## Active task: release 0.13.42 (`mir-mcp` native Windows lane and the Python 3.11 floor) (2026-10-28)

Intent authority: the owner's answers on the native Windows lane (Discord 1564632417304838205:
option B `ctypes` guard, keep `python3`, Git at the default Git for Windows location, the same
user-visible behaviour), the Python 3.11+ floor on every OS (1564633173516755045), the home_server
PATH fix applied (1564793658933383179; Main observed every live `mir-mcp` on 3.14.6) and the start
of 0.13.42 ("go ahead", 1564794291950452747), with the release-chain approvals
(1564297975755448493, 1564320227062186065), relayed by Mir Harness Main (parent-supplied). Design
authority: this cursor, Mir Harness `tasks/reports/mir-mcp-windows-admission-design-2026-10-27.md`
§2-§5 with its 2026-10-28 update (parent-supplied), and the ADR-91 amendment this release adds.
Baseline: 54b3841 on `main` (v0.13.41 installed and attested on the maintainer host).

Prior cursor preserved verbatim:
[cursor before release 0.13.42](change_log.md#cursor-before-release-01342-2026-10-28).

Rules:
1. Windows filesystem guard (option B): lexical refusals, root refusals (UNC, `\\?\`, `\\.\`,
   drive-relative, resolving to UNC), a handle walk with `CreateFileW`
   (`FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS`, no `FILE_SHARE_DELETE`), refusal
   of every reparse point, final-path proof by `GetFinalPathNameByHandleW`, ancestors held during
   the read; the only native surface is `kernel32` `CreateFileW`, `GetFinalPathNameByHandleW`,
   `CloseHandle` plus `msvcrt.open_osfhandle`.
2. Windows deadline: the cooperative deadline stays; a worker thread backstop answers `E_TIMEOUT`
   at 10 s and exits the server. Startup selects the platform path instead of refusing Windows.
3. Windows Git: only `C:\Program Files\Git\mingw64\bin\git.exe`, the same argv and five-entry
   environment, `CREATE_NO_WINDOW`, two bounded reader threads instead of `selectors`.
4. Provider: receipts accept `platform: windows` only on Windows (and refuse it elsewhere), the
   native interpreter path, and the observed launcher forms; the manager admits `mir-mcp` on
   Windows x64.
5. Python 3.11+: `mir-mcp` refuses to start below 3.11 with a stderr reason; receipts require
   `interpreter.version` >= 3.11; hooks and copied runners warn below 3.11 and still run.

Request matrix: (1) fail-first tests and code for rules 1-5; (2) ADR-91 amendment, docs, version
surfaces; (3) Main full suite, fresh-clone readiness, Windows PC `mir-mcp` and in-scope tests;
(4) release and host re-attestation (macOS receipts at >= 3.11); (5) Windows receipts on the
owner's PC (needs the PC's real Claude/Codex homes: owner decision on its Yoke 0.8.0 state).

Status (2026-10-28, Main):
- (1) done: slices M1 guard, M2 deadline/startup/Git, M3 provider/manager, M4 floor, M5 Windows
  test fixes. Main changes: the SessionStart hook keeps its exact print-only H1 source (the M4
  warning broke its 1024-byte bound), so only the handoff hook warns; handoff handler SHA
  updated; receipt lookups keyed by the consumer key.
- (2) done: ADR-91 and ADR-90 amendments, CHANGELOG, MIGRATION, README, version surfaces 0.13.42;
  `windows_native` CI job gains the `mir-mcp` test files.
- (3) partly done: macOS full suite 3834 passed with 3 failures. Two were version pins in
  `tests/test_plugin_skill_packages.py`, fixed and re-run at 16 passed; the third is the lock,
  rebound at release. Windows PC: 1945 passed, 4 failed (lock plus the three consumer-key
  lookups, since fixed); a targeted re-run after the fixes gave 114 passed, 1 skipped (8.3
  names disabled on the volume). Fresh-clone readiness is still open.
- (4), (5) open.
- 2026-10-28 later: v0.13.42 was tagged and pushed (79a9cbf source, 35f696a bind) but its release
  check failed twice. On `windows-latest`, Git for Windows 2.56 moved `git.exe` from `mingw64\bin`
  to `ucrt64\bin`. On Ubuntu, no Python 3.11 compatibility interpreter was installed. Following
  the v0.13.37 precedent, the tag stays and has no release. 0.13.43 uses the first present of two
  fixed binaries (`ucrt64`, then `mingw64`) and adds 3.11 to the release workflow.
- (3) done for 0.13.43: fresh-clone readiness passed with 3837 tests (26 skipped) and every
  check exiting 0. CI validate (including `windows_native` on Git for Windows 2.56) and release
  succeeded; v0.13.43 was published 2026-10-28T02:37:05Z.
- (4) done: provider updated 0.13.41 -> 0.13.43 (0bb5634); Codex hooks re-trusted (4). Claude
  session 3d6aedad and Codex thread 01a18060 attested: five mir-mcp calls ok, four hooks and the
  skills. The observed servers ran Homebrew Python 3.14.6, so the 3.11 floor holds; the Codex
  server cwd is the installed 0.13.43 root. Finalized after restart; status ready at 0bb5634.
- (5) open: Windows receipts need the PC's real Claude/Codex homes (stale Yoke 0.8.0
  registration for `daily_reward_runner`); owner decision.
