"""Gate primitives - GateBlocked + ValidationResult + PathFingerprint.

design §4.1.1. ``code`` values are machine-readable labels; Reporter
(``§9.7.2 KOREAN_GATE_TEMPLATES``) maps each to a localized user-facing string.

``ValidationResult`` and ``PathFingerprint`` are consumed by Hook #1
(``taskspec_validate.py``, design §6.3 Hook #1) — both are leaf contracts so
Hook #1 can import them without crossing into engine/conductor layers.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GateBlocked(Exception):
    """Single exception type. `code` is one of the constants below."""

    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


class PathFingerprint(BaseModel):
    """Inode + SHA pin for a referenced file path — used by Hook #1 TOCTOU
    check (design §6.3 Hook #1). The gateway records a fingerprint at
    ``TaskSpec`` validate time; at dispatch time Hook #1 recomputes and
    compares to reject files that were replaced in between."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    inode: int = Field(ge=0)
    sha256: str | None = None    # None = content not pinned (e.g. directory)


class ValidationResult(BaseModel):
    """Hook-layer outcome passed back to the gateway / Reporter. ``ok=True``
    with ``reason=""`` is the pass case. Hooks that want to surface a warning
    without blocking use ``ok=True`` + ``reason="…"`` — the gateway logs but
    does not raise."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    reason: str = ""
    rule_id: str = ""


# Standard code set (§4.1.1; Reporter KOREAN_GATE_TEMPLATES maps 1:1).
# When adding a new code:
#   1) Add it to this constant.
#   2) Add the localized Reporter KOREAN_GATE_TEMPLATES entry (§9.7.2).
#   3) Confirm tests/test_gate_codes_roundtrip.py passes.
STANDARD_CODES = frozenset({
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
    # v0.6 ADR 2/3 (Independent Review M5)
    "preserve_tamper_blocked",
    "phase_gate_unmet",
    "phase_gate_unknown_phase",
    "phase_gate_cfg_error",
    "phase_gate_busy",
    "claude_md_merge_error",
})
