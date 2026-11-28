# Plan

## Active task: release v0.14.3 (Mac first)

Intent authority: the owner's release order of 2026-11-28, given through the
managing Mir Harness session (ADR-86).
Scope: release the Stage G hook ports, the retirements and the improvement-loop
reference that are on the candidate branch; Darwin artifacts only.

Order: version commit on `release/v0.14.3`; clean-clone readiness; branch push
and validate; native prerelease from the version commit; bind commit (Darwin
artifacts, CLI pin, lock source); readiness with the staged artifacts; `main`
fast-forward to the bind commit; tag after `main` validates; consumer update
and attestation per runtime on the Mac.

Open after this release: Linux and Windows attestation, the classification of
the Windows advisory lane failures and the Windows `mir_entry_e17` capture.

The previous cursor (SG-Y-PORT2) is in `tasks/change_log.md` under
"2026-11-28 - v0.14.3 release: superseded plan cursor (verbatim)".
