# Executor common v3 verification (2026-10-01)

Authority: `tasks/plan.md` and the supplied `spec-executor-v3.md`.
Baseline HEAD: `9fc39cd`. No consumer writes, commit, push or tag.
Every pytest command uses `UV_CACHE_DIR=/tmp/mir-yoke-uv-cache uv run pytest -q`.

| Item | Fail-first observations | Pass observations |
| --- | --- | --- |
| 1 CLI agent routes | Baseline CLI: `9 failed, 6 deselected`; omitted route options: `6 failed, 6 passed, 9 deselected` | Route selector: `15 passed, 7 deselected` |
| 2 Agent API / stderr | Executor API: `2 failed`; dispatch stderr: `2 failed` | `-k item2`: `5 passed, 41 deselected` |
| 3 Execution writer lease | Executor: `2 failed`; direct/nested lease: `2 failed`; ledger: `2 failed`; repeated cancellation: `2 failed, 27 deselected` | Final selector: `9 passed, 39 deselected`; repeated cancellation: `2 passed, 27 deselected` |
| 4 Strict item shape | MCP aggregate: `10 failed, 8 passed`, including six shape failures | Shape selector: `14 passed, 4 deselected` |
| 5 Provider hook / metadata | Executor: `4 failed`; dispatch: `3 failed`; MCP metadata: `4 failed`; notification usage: `1 failed, 23 deselected`; reviewer budget: `1 failed, 26 deselected` | Hook/metadata selector: `13 passed, 51 deselected` |
| 6 Timeout bounds | Executor: `4 failed`; CLI: `6 failed, 9 deselected`; dispatch/config/resume: `16 failed`; stall: `2 failed, 24 deselected`; finalize preflight: `1 failed, 21 deselected` | Bounds selector: `32 passed, 36 deselected` |

Parent baseline aggregate: `test_v3_execution.py` returned `23 failed in 0.89s`
before dispatch/helper implementation. MCP's baseline includes eight compatible
cases. The corrected route fixture was also checked against baseline CLI loaded
from Git into memory in a separate process; no baseline file mutation was needed.

Selectors, with all test files under `tools/mir_executor/tests/`:
- Item 1: `test_v3_cli_routes.py -k 'not timeout'`.
- Items 2/3: `test_v3_execution.py test_v3_executor.py -k item2` / `-k item3`.
- Item 4: `test_v3_mcp.py -k 'malformed or unknown'`.
- Item 5: the execution, executor and MCP v3 files, selecting
  `'(item5 or collect or constructor_backward) and not malformed'`.
- Item 6: the execution, executor and CLI v3 files, selecting `'item6 or timeout'`.

All 88 new v3 tests passed in 1.78s. The initial full suite returned
`1 failed, 1542 passed in 205.43s (0:03:25)`. Its only failure was an old resume
fixture without a resolver for its named agent; the corrected fixture passed
(`1 passed, 28 deselected`). Final full pytest: `1546 passed in 205.29s (0:03:25)`.
Final Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
common manifest Python files. Self-target sync reported `Common manifest: PASS`;
Codex generated parity passed. Regenerated common manifests and adopter payload;
portable-manifest and payload/classification checks returned `7 passed`.
Parent execution logs are `/tmp/mir-executor-v3-*.txt`.

## Preserved predecessor evidence

# Executor common fail-first evidence

Every new test node below was observed failing before its implementation and passing afterward.
The initial logs and follow-up cycles are retained in temporary verification storage.
Collection errors are not counted as fail-first proof. All entries refer to explicit FAILED/PASSED lines.

New regression nodes: 89.

| Test node | Fail-first line | Pass line |
| --- | --- | --- |
| `tests/test_executor_sync.py::test_should_generate_hashes_without_local_files` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_show_per_file_dry_run_without_writes` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_apply_only_common_files_and_preserve_local_data` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_refuse_dirty_common_files` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_detect_local_and_source_drift` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_refuse_symlink_targets` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_reject_unsafe_manifest_paths` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_use_defaults_when_local_module_absent` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_call_repo_hooks_without_cross_repo_leakage` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_load_local_config_and_fail_on_invalid_data` | `FAILED` (executor-sync-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_preserve_repo_tests_outside_the_tiny_common_contract` | `FAILED` (executor-manifest-red.log) | `PASSED` (executor-manifest-green.log) |
| `tests/test_executor_sync.py::test_should_leave_git_index_unchanged_during_dry_run` | `FAILED` (executor-index-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_manifest.py::test_should_match_common_manifest` | `FAILED` (executor-manifest-red.log) | `PASSED` (executor-manifest-green.log) |
| `tools/mir_executor/tests/local/test_local.py::test_should_validate_yoke_brief_files` | `FAILED` (executor-local-red.log) | `PASSED` (executor-local-green.log) |
| `tools/mir_executor/tests/local/test_local.py::test_should_reject_invalid_yoke_brief_files` | `FAILED` (executor-local-red.log) | `PASSED` (executor-local-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_canonical_mode[obey_user]` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_canonical_mode[user_command_priority]` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_optional_local_and_delegation_merge` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_lock_path_seam` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_unresolved_mode_warning` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_nullable_metadata_and_legacy_read` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_sanitized_persistence` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_resume_clears_results[mark_resumed]` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_resume_clears_results[update_status]` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_terminal_artifact_sweep` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_artifact_sweep_rejects_symlink_root` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_ai_run_metadata_roundtrip` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_delegation_project_evidence_accessors` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_local_artifact_retention_and_explicit_override` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_update_route_metadata` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_sweep_resume_attempt_history` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_policy_jobs.py::test_common_artifact_sweep_evidence_is_path_specific` | `FAILED` (executor-policy-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_reject_empty_agent_item_id` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_reject_conflicting_response_envelope[envelope0]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_reject_conflicting_response_envelope[envelope1]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_reject_invalid_completion_turn[None]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_reject_invalid_completion_turn[turn1]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_reject_invalid_completion_turn[turn2]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_reject_invalid_completion_turn[turn3]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_terminate_after_reader_protocol_error` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_bound_blocked_send_by_request_timeout` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_preserve_extra_ledger_category_keys` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_default_executor_sandbox_to_workspace_write[False]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_default_executor_sandbox_to_workspace_write[True]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_wait_for_worker_before_propagating_cancellation` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_filter_credentials_from_dispatch_environment` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_import_common_executor_without_mir_package` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_secure_and_redact_initial_worktree_artifacts` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_filter_executor_child_env_using_local_config[False]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_common_transport_fixes.py::test_should_filter_executor_child_env_using_local_config[True]` | `FAILED` (executor-client-red.log) | `PASSED` (executor-acceptance-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_common_optional_parser_options` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_backend_uses_policy_order_and_project_data` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_codex_dispatch_missing_route_fails_closed` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_dispatch_exception_marks_job_failed` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_execute_propagates_command_exit` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_resume_redispatches_existing_job` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_background_propagates_persisted_exit` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_dispatch_propagates_attempt_exit_and_metadata` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_main_loads_execute_options_from_explicit_target` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_resume_restores_route_and_local_execution_scope` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_failed_dispatch_resume_allocates_new_worktree` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_configured_declaration_fields_reject_ambiguous_backend` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_cli_dispatch_constructs_opt_in_reviewer` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_cli_common.py::test_cli_sweep_includes_terminal_artifact_report` | `FAILED` (executor-cli-red.log) | `PASSED` (executor-cli-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_glob_allowlist` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_timeout_validation[0]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_timeout_validation[-1]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_timeout_validation[nan]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_timeout_validation[inf]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_timeout_validation[True]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_workspace_sandbox_and_metadata` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_secure_redacted_artifacts` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_unknown_verifier_fails_closed` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_named_verifier_and_reviewed_no_diff` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_required_review_fails_closed` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_reviewer_read_only` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_agent_route_api` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_failure_preserves_metadata` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_verifier_environment_filters_credentials` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_claude_route_api` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_reviewed_no_diff_rechecks_review_mutation` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_run_artifacts_root` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_reviewed_cleanup_failure_keeps_review_verdict` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_long_review_evidence_remains_valid_json` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_long_structured_artifacts_remain_valid_json[status.json]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_long_structured_artifacts_remain_valid_json[events.jsonl]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_nested_secret_redaction_preserves_json[status.json]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_nested_secret_redaction_preserves_json[events.jsonl]` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |
| `tools/mir_executor/tests/test_dispatch_common.py::test_common_worktree_structured_status_redacts_values` | `FAILED` (executor-dispatch-red.log) | `PASSED` (executor-dispatch-green.log) |


## Common v3.7: worktree/artifact symlinks and backend precedence (2026-10-02)

Intent/design authority: `tasks/plan.md`. Baseline: clean HEAD `7f7e677`.
Every uv command used the owner-provided external `UV_CACHE_DIR` and an external
`TMPDIR`. Absolute scratch paths in captured output are normalized for publication.
All runs below used `uv run pytest -q -p no:cacheprovider`.

1. `tools/mir_executor/tests/test_worktree.py -k should_refuse_private_write`:
   before **1 failed, 20 deselected in 0.08s**; after
   **1 passed, 20 deselected in 0.03s**.
2. `tools/mir_executor/tests/test_dispatch_common.py -k should_refuse_artifact_copy`:
   before **12 failed, 25 deselected in 0.11s**; after
   **12 passed, 25 deselected in 0.05s**. Six artifact names each cover a file
   symlink and a symlinked `.mir-dispatch` directory.
3. `tools/mir_executor/tests/test_v3_cli_routes.py -k should_use_agent_route`:
   before **12 failed, 96 passed, 10 deselected in 2.86s**; after
   **108 passed, 10 deselected in 2.93s**. Current source already selected agent
   backends over policy force/default backends; only conflicting explicit user
   flags in user_command_priority mode failed. Existing source behavior is
   reported faithfully, rather than inventing an absent route/default failure.
   Extended checks preserve selection order, modes and the obey_user alias.

Captured fail-first output follows. Artifact/backend output retains the failure
reason and every failed node; repetitive individual traces are omitted.

### worktree baseline output

```text
F                                                                        [100%]
=================================== FAILURES ===================================
_________ test_should_refuse_private_write_when_destination_is_symlink _________

tmp_path = PosixPath('<test-scratch>/test_should_refuse_private_wri0')

    def test_should_refuse_private_write_when_destination_is_symlink(tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("keep original\n")
        outside.chmod(0o644)
        destination = tmp_path / "brief.md"
        destination.symlink_to(outside)

>       with pytest.raises(OSError) as error:
             ^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE <class 'OSError'>

tools/mir_executor/tests/test_worktree.py:31: Failed
=========================== short test summary info ============================
FAILED tools/mir_executor/tests/test_worktree.py::test_should_refuse_private_write_when_destination_is_symlink
1 failed, 20 deselected in 0.08s
```

### artifact baseline output

```text
>       with pytest.raises(OSError):
             ^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE <class 'OSError'>

tools/mir_executor/tests/test_dispatch_common.py:107: Failed
=========================== short test summary info ============================
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[False-reviewer.json]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[False-brief.md]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[False-status.json]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[False-result.json]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[False-events.jsonl]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[False-dispatch-events.jsonl]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[True-reviewer.json]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[True-brief.md]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[True-status.json]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[True-result.json]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[True-events.jsonl]
FAILED tools/mir_executor/tests/test_dispatch_common.py::test_should_refuse_artifact_copy_when_source_is_symlink[True-dispatch-events.jsonl]
12 failed, 25 deselected in 0.11s
```

### backend baseline output

```text
E       AssertionError: assert 'claude' == 'codex'
E
E         - codex
E         + claude

tools/mir_executor/tests/test_v3_cli_routes.py:96: AssertionError
----------------------------- Captured stdout call -----------------------------
[DISPATCH] status=completed attempts=1 fell_back=False reason=None
[FINALIZE] action=reviewed reason='passed' merged=[]
=========================== short test summary info ============================
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[codex-persisted-route_options0-user_command_priority-claude]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[codex-persisted-route_options1-user_command_priority-claude]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[codex-validated_object-route_options0-user_command_priority-claude]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[codex-validated_object-route_options1-user_command_priority-claude]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[codex-validated_dict-route_options0-user_command_priority-claude]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[codex-validated_dict-route_options1-user_command_priority-claude]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[claude-persisted-route_options0-user_command_priority-codex]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[claude-persisted-route_options1-user_command_priority-codex]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[claude-validated_object-route_options0-user_command_priority-codex]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[claude-validated_object-route_options1-user_command_priority-codex]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[claude-validated_dict-route_options0-user_command_priority-codex]
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_agent_route_when_dispatch_brief_names_agent[claude-validated_dict-route_options1-user_command_priority-codex]
12 failed, 96 passed, 10 deselected in 2.86s
```

### Final checks

```text
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests
FAILED tools/mir_executor/tests/test_policy.py::test_adr88_this_repository_routes_from_its_deployed_lock
1 failed, 742 passed in 72.49s (0:01:12)

uv run pytest -q -p no:cacheprovider
FAILED tools/mir_executor/tests/test_policy.py::test_adr88_this_repository_routes_from_its_deployed_lock
1 failed, 1748 passed in 232.84s (0:03:52)

uv run ruff check
All checks passed!

uv run python scripts/verify_codex_sync.py
OK: Codex derivatives match Claude sources

uv run python -m tools.executor_sync --check --target .
Common manifest: PASS
```

The sole remaining failure is an unchanged test's hardcoded expectation
`user_command_priority` versus the committed lock's `force_codex`. Policy source,
test, conftest, local policy and lock were verified byte-identical to HEAD.
No routing lock or format change is made to work around that test.
Python 3.11.16 compiled all 15 common files. The initial public-path scan failure
was resolved by normalizing host paths; the final full-suite result above includes
that correction. Common v3.7 is recorded in the sync guide and CHANGELOG.


### v3.7 owner review corrections (2026-10-02)

Authority: the current owner follow-up and `tasks/plan.md`. This section
supersedes the earlier v3.7 decision to let agent backends override forced modes
and the earlier remaining policy-test item. Earlier outputs remain historical.

Restored unconditional forced-mode selection in `_resolve_dispatch_backend`.
`force_codex` selects Codex even when the agent route declares Claude;
`force_claude` likewise selects Claude. Explicit CLI backend selection still
wins when the policy selects the user_command step, and the agent backend
otherwise wins over project/default steps. The route matrix now checks these
forced-mode semantics. The live-policy test compares its mode to the committed
lock rather than a literal; the routing lock is not changed.

Fail-first command (external UV cache and scratch environment applied):

```text
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_cli_common.py::test_should_return_codex_when_force_codex_conflicts_with_agent_backend
F                                                                        [100%]
=================================== FAILURES ===================================
____ test_should_return_codex_when_force_codex_conflicts_with_agent_backend ____

    def test_should_return_codex_when_force_codex_conflicts_with_agent_backend():
        policy = SimpleNamespace(mode="force_codex")

>       assert cli._resolve_dispatch_backend(
            policy, requested_backend=None, agent_backend="claude",
        ) == "codex"
E       AssertionError: assert 'claude' == 'codex'
E
E         - codex
E         + claude

tools/mir_executor/tests/test_cli_common.py:42: AssertionError
=========================== short test summary info ============================
FAILED tools/mir_executor/tests/test_cli_common.py::test_should_return_codex_when_force_codex_conflicts_with_agent_backend
1 failed in 0.06s
```

Final follow-up outputs (all exit 0; external UV cache and scratch applied):

```text
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_cli_common.py tools/mir_executor/tests/test_v3_cli_routes.py tools/mir_executor/tests/test_policy.py
177 passed in 3.86s

uv run python -m tools.executor_sync --generate
Generated config/mir-executor-common.json: 15 files

uv run python -m tools.template_assets --write-adopter-payload
template asset classification: pass

uv run pytest -q -p no:cacheprovider
1750 passed in 248.36s (0:04:08)

uv run ruff check
All checks passed!

uv run python scripts/verify_codex_sync.py
OK: Codex derivatives match Claude sources

uv run python -m tools.executor_sync --check --target .
Common manifest: PASS
```

The fail-first regression is covered by the 177-test focused run and the full
1750-test run. Both required corrections are complete. This follow-up changed
CHANGELOG.md; config/adopter-payload.json; config/mir-executor-common.json;
docs/operations/mir-executor-sync.md; tasks/change_log.md; tasks/plan.md;
tasks/reports/executor-common-fail-first.md; tools/mir_executor/COMMON_MANIFEST.json;
tools/mir_executor/cli.py; tools/mir_executor/tests/test_cli_common.py;
tools/mir_executor/tests/test_policy.py; tools/mir_executor/tests/test_v3_cli_routes.py.
Earlier v3.7 symlink implementation/tests remain intact. No commit, tag, push or
consumer write occurred. The committed lock and generated `.codex/**` are
unchanged. Final evidence edits are followed by the same payload generator and
exact-payload/public-surface checks; task scratch is removed after those checks.
No requested item remains open.

## Common v3.8: forced-mode route model guard (2026-10-02)

Authority: owner Discord 1555426386900942934, 2026-10-02, and `tasks/plan.md`.
Baseline: clean HEAD `f95dcd5`, common v3.7. No commit/tag/push, consumer writes,
routing lock edits or generated `.codex/**` writes are authorized.

The agent route's explicit `execution_backend` now gates its model/effort:
when it differs from the resolved backend, the category/default values already
computed by `_resolve_policy_runtime_options` apply. CLI model and effort flags
keep precedence. Agent definitions supply an explicit backend; Codex agent routes
obtain their model from the lock-selected category. Category/default policy routes
have no declared backend and `resolve_category()` returns model/effort only.
The final automatic model is therefore checked against known Claude aliases
sonnet/opus/fable/haiku and claude-* versus Codex gpt-* under forced modes.
A recognized opposite-backend model fails before runner construction or invocation.
Unknown model names are not guessed, and an explicit CLI model bypasses the guard.
No policy schema or lock edits are required. Matching agent routes remain effective.

Fail-first command (external UV cache and task scratch applied), exit 1:

```text
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_category_model_when_force_codex_conflicts_with_agent_backend
F                                                                        [100%]
=================================== FAILURES ===================================
_ test_should_use_category_model_when_force_codex_conflicts_with_agent_backend _

dispatch_model_options = <function dispatch_model_options.<locals>.execute at 0x10b1893a0>

    def test_should_use_category_model_when_force_codex_conflicts_with_agent_backend(
        dispatch_model_options,
    ):
        result, calls = dispatch_model_options("force_codex", {
            "by_category": {"unit": {"model": "gpt-category", "reasoning_effort": "medium"}},
        })
        assert result == 0
        assert calls[0]["backend"] == "codex"
>       assert calls[0]["model"] == "gpt-category"
E       AssertionError: assert 'sonnet' == 'gpt-category'
E
E         - gpt-category
E         + sonnet

tools/mir_executor/tests/test_v3_cli_routes.py:57: AssertionError
----------------------------- Captured stdout call -----------------------------
[DISPATCH] status=completed attempts=1 fell_back=False reason=None
[FINALIZE] action=reviewed reason='passed' merged=[]
=========================== short test summary info ============================
FAILED tools/mir_executor/tests/test_v3_cli_routes.py::test_should_use_category_model_when_force_codex_conflicts_with_agent_backend
1 failed in 0.07s
```

Focused regression command, exit 0:

```text
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_cli_common.py tools/mir_executor/tests/test_v3_cli_routes.py tools/mir_executor/tests/test_policy.py
211 passed in 4.00s
```

Coverage includes the real Claude agent definition versus forced Codex category
model; explicit model/effort (including an explicitly selected sonnet); effort-only
override; non-forced and matching forced agent routes; category, prefer, default
and legacy flat defaults for both forced backends; and unchanged handling of unknown
model names. The existing dispatch matrix now expects policy model/effort whenever
the selected backend differs from the agent backend.

Final outputs (all exit 0; external UV cache and task scratch applied):

```text
uv run python -m tools.executor_sync --generate
Generated config/mir-executor-common.json: 15 files

uv run python -m tools.template_assets --write-adopter-payload
template asset classification: pass

uv run pytest -q -p no:cacheprovider
1784 passed in 220.99s (0:03:40)

uv run ruff check
All checks passed!

uv run python scripts/verify_codex_sync.py
OK: Codex derivatives match Claude sources

uv run python -m tools.executor_sync --check --target .
Common manifest: PASS

python3.11 -m compileall -q tools/mir_executor
(no output; exit 0, bytecode cache in task scratch)
```

Changed files: CHANGELOG.md; config/adopter-payload.json;
config/mir-executor-common.json; docs/operations/mir-executor-sync.md;
tasks/change_log.md; tasks/plan.md; tasks/reports/executor-common-fail-first.md;
tools/mir_executor/COMMON_MANIFEST.json; tools/mir_executor/cli.py;
tools/mir_executor/tests/test_v3_cli_routes.py.
The two generated manifests retain schema 1 and SOURCE_COMMIT. Git diff confirms
routing lock and `.codex/**` are unchanged. No commit/tag/push or consumer write
occurred. All requested acceptance commands passed. Final record edits are followed
by adopter-payload regeneration and exact-content/public-surface tests; task scratch
is removed after those checks.

Final record/payload checks: `9 passed in 0.41s` using
`uv run pytest -q -p no:cacheprovider tests/test_template_asset_classification.py
tests/test_public_template_surface.py`. Lock and all 15 generated `.codex/**`
files match the follow-up baseline SHA-256 values.


Final record refresh: `uv run python -m tools.template_assets --write-adopter-payload`
passed; `uv run pytest -q -p no:cacheprovider tests/test_template_asset_classification.py
tests/test_public_template_surface.py` passed (`9 passed in 0.35s`, exit 0).
The closing cursor/log update repeats the same payload refresh and checks.
No requested implementation or acceptance item remains. Task scratch is removed
after the closing checks; no additional delivery or Git authority is exercised.
