"""ConductorMode - FSM state enum.

design §4.1.2 · §6 Conductor FSM.
Transition rule: NORMAL -> META_REQUESTED -> META_APPROVED -> META_APPLYING -> NORMAL.
"""
from __future__ import annotations

from enum import StrEnum


class ConductorMode(StrEnum):
    NORMAL = "normal"
    META_REQUESTED = "meta_requested"
    META_APPROVED = "meta_approved"
    META_APPLYING = "meta_applying"
