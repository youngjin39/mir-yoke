//! The thirteen-state vocabulary reached by interrupt_handler.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RunState {
    Idle,
    Discover,
    Plan,
    NeedApproval,
    Act,
    Verify,
    Report,
    Done,
    Replan,
    Blocked,
    Cancelling,
    Rollback,
    Interrupted,
}
impl RunState {
    pub const ALL: [Self; 13] = [
        Self::Idle,
        Self::Discover,
        Self::Plan,
        Self::NeedApproval,
        Self::Act,
        Self::Verify,
        Self::Report,
        Self::Done,
        Self::Replan,
        Self::Blocked,
        Self::Cancelling,
        Self::Rollback,
        Self::Interrupted,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "IDLE",
            Self::Discover => "DISCOVER",
            Self::Plan => "PLAN",
            Self::NeedApproval => "NEED_APPROVAL",
            Self::Act => "ACT",
            Self::Verify => "VERIFY",
            Self::Report => "REPORT",
            Self::Done => "DONE",
            Self::Replan => "REPLAN",
            Self::Blocked => "BLOCKED",
            Self::Cancelling => "CANCELLING",
            Self::Rollback => "ROLLBACK",
            Self::Interrupted => "INTERRUPTED",
        }
    }
}
