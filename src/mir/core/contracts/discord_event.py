"""DiscordEvent - Conductor input event (frozen).

design §4.1.8 · integrations/discord-adapter.md.
v0.5.3 R4: `frozen=True` + canonical_json fingerprint.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DiscordEvent(BaseModel):
    """Single input event received by Conductor; mutation is forbidden after receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chat_id: str
    message_id: str
    user: str
    user_id: str
    timestamp: str                      # ISO8601
    content: str
    attachments: tuple[dict, ...] = ()  # v0.5.3 R4: immutable container
    reply_to: str | None = None
    source: str = "discord"             # extension point (Telegram/Slack, etc.)
