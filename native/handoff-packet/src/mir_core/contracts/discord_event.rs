//! Ordered field specs mirror the Python reference class.
use super::Kind::*;
use serde_json::json;
super::contract!(DiscordEvent;
    ("chat_id", String, None, None, None),
    ("message_id", String, None, None, None),
    ("user", String, None, None, None),
    ("user_id", String, None, None, None),
    ("timestamp", String, None, None, None),
    ("content", String, None, None, None),
    ("attachments", Tuple(&AnyDict), Some(json!([])), None, None),
    ("reply_to", Nullable(&String), Some(json!(null)), None, None),
    ("source", String, Some(json!("discord")), None, None),
);
