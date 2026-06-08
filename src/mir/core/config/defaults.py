"""Default values — **single source**. Other modules either reference these constants directly or access them through `ResolvedConfig`.

design §9.6 · §9.6.3 · §9.6.4 · §9.6.5 · §7.5.
Principles:
- Do not define default-value literals outside this file.
- When adding a new default, update this file and the corresponding `ResolvedConfig` field together.
"""
from __future__ import annotations

# v0.5.3 R1: self-modification blocked paths (PolicyStore.denied_paths default).
DEFAULT_DENIED_PATHS: tuple[str, ...] = (
    "core/**",
    ".claude/hooks/**",
    ".mir/**",
    "harness_*.toml",
    "guides.toml",
    "pyproject.toml",
    "core/registry/**",
)

# v0.5.3 R8: env var prefixes not inherited by Worker CLI. HOME moved in v0.5.4-6.
DEFAULT_DENIED_ENV_PREFIXES: tuple[str, ...] = (
    "AWS_", "GOOGLE_", "GCP_", "AZURE_",
    "OPENAI_", "ANTHROPIC_", "GEMINI_", "COHERE_", "HUGGINGFACE_",
    "SLACK_", "DISCORD_", "TELEGRAM_",
    "NPM_", "NODE_AUTH_", "PYPI_", "CARGO_",
    "GITHUB_", "GITLAB_", "BITBUCKET_",
    "SSH_", "GPG_", "AGE_",
    "MIR_SIGNING", "MIR_USER_PUBKEY",
)

# v0.5.3 R8 + v0.5.4-6: blocked by name (HOME must be replaced with `user_home` before injection).
DEFAULT_DENIED_ENV_KEYS: frozenset[str] = frozenset({
    "PATH",                     # inject only the sanitized minimal PATH
    "HOME",                     # v0.5.4-6: forcibly replace with user_home
    "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "DYLD_FORCE_FLAT_NAMESPACE",
    "PYTHONPATH", "PYTHONSTARTUP",
    "BASH_ENV", "ENV",
    "HISTFILE", "HISTFILESIZE",
})

# Meta approval sensitive TOML keys (v0.5.3 R8 extension).
# Diffs containing these keys require the `allows_sensitive=true` flag plus separate approval.
SENSITIVE_KEYS: frozenset[tuple[str, ...]] = frozenset({
    ("conductor", "model"),
    ("harness_b", "hooks"),
    ("mcp", "allowlist"),
    ("audit", "signer_mode"),
    ("audit", "anchor"),                # v0.5.3 R6
    ("providers", "allowlist"),         # v0.5.3 R7
    ("memory", "embedding"),            # D1 replacement
    ("roles",),                         # all role mappings
    ("mir", "signing_key_path"),
})

# --- Default config values (base before load_config applies TOML overrides) ---

DEFAULT_EMBEDDING_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_EMBEDDING_MODEL = "bge-m3-mlx-fp16"           # HF: mlx-community/bge-m3-mlx-fp16 (v0.5.4-1)
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_EMBEDDING_TIMEOUT_SEC = 10
DEFAULT_EMBEDDING_NORM_TOLERANCE = 1e-3               # v0.5.3 R3
DEFAULT_EMBEDDING_API_KEY_ENV = "OMLX_API_KEY"        # v0.5.4-2

DEFAULT_CLAUDE_MEMORY_PLUGIN_MODE = "disabled"        # v0.5.5 errata E8
DEFAULT_CLAUDE_MEMORY_RECALL_POLICY = "progressive"   # v0.5.5-1 §9.18.2

DEFAULT_CODEX_FALLBACK = "claude_n_session"           # v0.5.3 A6

# Circuit breaker (llm-circuit vendored · v0.5.3 R12)
DEFAULT_BREAKER_CONSECUTIVE_THRESHOLD = 3
DEFAULT_BREAKER_WINDOW_SIZE = 20
DEFAULT_BREAKER_WINDOW_FAILURE_RATE = 0.5
DEFAULT_BREAKER_RECOVERY_TIMEOUT = 30
DEFAULT_BREAKER_HALF_OPEN_REQUIRED_SUCCESSES = 3      # v0.5.3 R12

# Hook #3 mode (v0.5.3 R1 split)
DEFAULT_HOOK3_SHELL_MODE = "enforce"
DEFAULT_HOOK3_AST_MODE = "advisory"

# Meta FSM transition lock (v0.5.3 H11)
DEFAULT_META_TRANSITION_STALE_SEC = 600               # 10 min
DEFAULT_NUKE_META_APPLYING_WAIT_SEC = 60              # v0.5.3 H12

# Minimal PATH injected into Worker subprocess
DEFAULT_WORKER_PATH = "/usr/bin:/bin:/opt/homebrew/bin"
