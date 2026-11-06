//! Gate errors, codes, and ordered leaf-model specifications.
use super::Kind::*;
use serde_json::json;
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GateBlocked {
    pub code: std::string::String,
    pub detail: std::string::String,
}
impl GateBlocked {
    pub fn new(
        code: impl Into<std::string::String>,
        detail: impl Into<std::string::String>,
    ) -> Self {
        Self {
            code: code.into(),
            detail: detail.into(),
        }
    }
}
impl std::fmt::Display for GateBlocked {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{}] {}", self.code, self.detail)
    }
}
impl std::error::Error for GateBlocked {}
super::contract!(PathFingerprint;
    ("path", String, None, None, None),
    ("inode", Int, None, Some((0.0, f64::INFINITY)), None),
    ("sha256", Nullable(&String), Some(json!(null)), None, None),
);
super::contract!(ValidationResult;
    ("ok", Bool, None, None, None),
    ("reason", String, Some(json!("")), None, None),
    ("rule_id", String, Some(json!("")), None, None),
);
pub const STANDARD_CODES: &[&str] = &[
    "policy_deny",
    "circuit_open",
    "denied_path",
    "session_isolation_required",
    "session_not_minted",
    "role_pair_same_session",
    "hook_integrity",
    "hook3_violation",
    "meta_approval",
    "meta_fsm_lock",
    "meta_blocked_pending_nuke",
    "nuke_requires_tty",
    "nuke_requires_foreground",
    "nuke_tty_check_failed",
    "nuke_bad_signature",
    "nuke_replay",
    "nuke_platform_unsupported",
    "toctou",
    "toctou_discord_event",
    "provider_not_allowed",
    "reviewer_degenerate_fail_closed",
    "claude_memory_unavailable",
    "config_error",
    "meta_applier_not_ready",
    "meta_nonce_replay",
    "meta_instance_mismatch",
    "migrate_self_target",
    "migrate_cross_family",
    "migrate_symlink_reject",
    "migrate_manifest_bad_sig",
    "migrate_manifest_missing",
    "migrate_manifest_expired",
    "migrate_toctou",
    "preserve_tamper_blocked",
    "phase_gate_unmet",
    "phase_gate_unknown_phase",
    "phase_gate_cfg_error",
    "phase_gate_busy",
    "claude_md_merge_error",
];
