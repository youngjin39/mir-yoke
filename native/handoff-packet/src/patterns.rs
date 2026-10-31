// Patterns transcribed from the unchanged Python reference.
pub const RECIPIENT: &[&str] = &[
    "[*`]",
    "handoff pins:|\\bpins\\s*:|sha256[^\\n]*[0-9a-f]{64}",
    "(?<![\\w:/])[\\w.-]+:[\\w./-]+",
];
pub const DETECT: &[&str] = &[
    "```[\\s\\S]*?```|~~~[\\s\\S]*?~~~",
    "^(?:please\\s+)?(?:do not|don.t|never)\\b",
    "(?:\\uc791\\uc131|\\uc704\\uc784)\\ud558\\uc9c0\\s*\\ub9c8",
    "(?:\\ub2e4\\ub978|\\ub2e4\\uc74c|\\ud558\\uc704)\\s*\\uc5d0\\uc774\\uc804\\ud2b8.*(?:\\ud578\\ub4dc\\uc624\\ud504|\\ube0c\\ub9ac\\ud504|\\uc9c0\\uc2dc\\ubb38|\\uc778\\uacc4\\ubb38).*(?:\\uc791\\uc131|\\uc368\\s*(?:\\uc918|\\uc8fc))",
    "(?:\\ud578\\ub4dc\\uc624\\ud504|\\ube0c\\ub9ac\\ud504|\\uc9c0\\uc2dc\\ubb38|\\uc778\\uacc4\\ubb38).*(?:\\ub2e4\\ub978|\\ub2e4\\uc74c|\\ud558\\uc704)\\s*\\uc5d0\\uc774\\uc804\\ud2b8(?:\\uc5d0\\uac8c|\\ud55c\\ud14c).*(?:\\ub118\\uae30|\\ub118\\uae38|\\uc804\\ub2ec|\\uc778\\uacc4|\\ub9e1\\uae30|\\ub9e1\\uae38)",
    "^(?:please\\s+)?(?:write|prepare|draft|create|give|send)\\b.*\\b(?:handoff|brief)\\b.*\\b(?:agent|codex|claude)\\b",
    "^(?:please\\s+)?delegate\\b.*\\b(?:agent|codex|claude)\\b",
];
pub const OWNER_SECTIONS: &[&str] = &[
    "\\b(?:do not|don.t|never)\\s+(?:include|forward|copy)\\b[^.!?;]*$|\\bauthor-only\\s+marker\\s*$",
    "(?:\\ub294|\\uc740|\\ub97c|\\uc744)?\\s*(?:\\uc804\\ub2ec|\\ud3ec\\ud568|\\ubcf5\\uc0ac)\\ud558\\uc9c0\\s*(?:\\ub9c8|\\ub9d0)",
    "^\\s*[-*]\\s+",
    "(?<=[.!?])(?=\\s|$|[\\uac00-\\ud7a3])\\s*",
    ";|\\n",
];
pub const RESTRICTED: &[&str] = &[
    ";|\\n|(?<=[.!?])(?:\\s+|$)",
    "\\b(?:other than|except|besides|apart from)\\b|\\uc774\\uc678|\\uc81c\\uc678",
    "\\b(?:run|execute) (?:any )?(?:commands|shell|python)\\b",
    "\\b(?:no commands|commands (?:are )?(?:forbidden|prohibited)|do not (?:run|execute) (?:any )?commands)\\b",
    "(?:\\uba85\\ub839|\\ucee4\\ub9e8\\ub4dc|\\uc250|\\ud30c\\uc774\\uc36c)[^\\n.!?]*(?:\\uc9c0\\s*(?:\\ub9d0|\\ub9c8|\\uc54a\\uace0)|\\uc2e4\\ud589\\s*\\uc5c6\\uc774|\\uae08\\uc9c0)",
];
pub const FILES_RESTRICTED: &[&str] = &[
    ";|\\n|(?<=[.!?])(?:\\s+|$)",
    "\\b(?:outside|other than|except|beyond|besides|under|in|not listed|only)\\b|(?:\\uc678|\\ubc16|\\uc774\\uc678|\\uc81c\\uc678|\\ubc94\\uc704\\s*\\ubc16)",
    "\\b(?:no (?:file changes|scratch writes)|(?:edit|modify|change|write|create|delete) (?:any )?files?|file (?:changes|writes) (?:are )?(?:forbidden|prohibited))\\b|(?:\\ud30c\\uc77c|\\uc2a4\\ud06c\\ub798\\uce58)[^\\n.!?]*(?:\\uc218\\uc815|\\ubcc0\\uacbd|\\ud3b8\\uc9d1|\\uc4f0\\uae30|\\uc791\\uc131|\\uc0dd\\uc131|\\uc0ad\\uc81c)",
];
pub const HOOK_PROMPTS: &[&str] =
    &["\\s*<hook_prompt\\s+hook_run_id=\"([^\"]+)\">([\\s\\S]*)</hook_prompt>\\s*"];
pub const CODE_SHELL_CALLS: &[&str] = &["\\\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\\r?\\n|.)"];
pub const TOOL_KIND: &[&str] =
    &["(?:^|__)(node_repl|python(?:_repl)?|js_repl|javascript_repl)(?:__|$)"];
pub const LABEL: &str = "^\\s*(?:#{1,6}\\s+|[-*]\\s+)?(?:\\*\\*)?(May not|May-not|May|Sources|Exclude|Do not forward|Not read|Protected)(?:\\*\\*)?\\s*(?:\\([^\\n)]*\\)\\s*)?(?::\\s*(?:\\*\\*)?(.*)|$)";
pub const PROHIBITION: &str = "\\b(?:do not|don.t|never|no (?:commands|file changes|scratch writes))\\b|\\b(?:commands|writes) (?:are )?(?:forbidden|prohibited)\\b|(?:\\uc9c0\\s*\\ub9d0(?!\\ub77c\\ub294|\\ub77c\\uace0)|\\uc9c0\\s*\\ub9c8(?:\\uc138\\uc694|\\ub77c)?|\\uc9c0\\s*\\uc54a\\uace0|\\uc2e4\\ud589\\s*\\uc5c6\\uc774|\\uae08\\uc9c0(?!\\s*\\ubc94\\uc704|\\ub41c)|\\ud558\\uba74\\s*\\uc548)";
pub const QUOTED: &str = "`([^`\\n]+)`|\"([^\"\\n]+)\"|(?<!\\w)\\'([^\\'\\n]+)\\'(?!\\w)";
pub const UNQUOTED_EXCLUSION: &str = "(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{3,})(?:\\ub294|\\uc740|\\ub97c|\\uc744|\\uc774|\\uac00)?\\s*(?:\\uc804\\ub2ec|\\ud3ec\\ud568)\\ud558\\uc9c0\\s*(?:\\uc54a|\\ub9d0)|\\b(?i:do not (?:forward|include))\\s+([A-Z][A-Z0-9_]{3,})(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{3,})\\s+(?i:must not be forwarded)\\b";
pub const TARGET_NAME: &str = "(?:qualified target|\\ub300\\uc0c1)\\b(?:[ \\t]*\\([^\\n)]*\\))?";
