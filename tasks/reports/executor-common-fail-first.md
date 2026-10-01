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
