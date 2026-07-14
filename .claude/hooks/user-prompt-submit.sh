#!/bin/bash
# UserPromptSubmit hook: emit a [context-pull] candidate retrieval directive.
# ADR-53 D3: deterministic, no LLM, no network, <100ms.
#
# Reads JSON from stdin: {"prompt": "..."}
# Skips: prompts < 40 chars; prompts starting with '/' (slash commands).
# Emits: exactly one "[context-pull] Candidate retrieval: uv run mir context pull \"<terms>\""
#
# tier: warn — advisory only, never blocks.
_MIR_HOOK_TIER="warn"

# Read stdin JSON
_INPUT=$(cat)
_PROMPT=$(printf '%s' "$_INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    p = d.get('prompt', '')
    print(p, end='')
except Exception:
    pass
" 2>/dev/null)

# Skip short prompts (< 40 chars)
_LEN="${#_PROMPT}"
if [ "$_LEN" -lt 40 ]; then
  exit 0
fi

# Skip slash commands (first non-space char is '/')
_TRIMMED="${_PROMPT#"${_PROMPT%%[![:space:]]*}"}"
if [ "${_TRIMMED:0:1}" = "/" ]; then
  exit 0
fi

# Skip XML-ish system content (first non-space char is '<', e.g. <task-notification>)
if [ "${_TRIMMED:0:1}" = "<" ]; then
  exit 0
fi

# Extract meaningful Unicode terms: lowercase, split on punctuation,
# drop common stopwords, take first 6 remaining tokens.
_TERMS=$(printf '%s' "$_PROMPT" | python3 -c "
import sys, re

STOPWORDS = {
    'a','an','the','is','it','in','on','at','to','for','of','and','or',
    'but','be','are','was','were','been','by','with','as','this','that',
    'these','those','from','into','how','what','why','when','where','which',
    'do','does','did','have','has','had','not','no','all','if','its','i',
    'we','you','he','she','they','them','their','our','my','your','can',
    'will','would','could','should','may','about','up','out','over','then',
    'so','than','more','also','just','some','any','such','each','both',
}

raw = sys.stdin.read().lower()
tokens = re.findall(r'[^\W_]+', raw, flags=re.UNICODE)
kept = [t for t in tokens if t and len(t) > 2 and t not in STOPWORDS]
terms = kept[:6]
print(' '.join(terms), end='')
" 2>/dev/null)

if [ -z "$_TERMS" ]; then
  exit 0
fi

echo "[context-pull] Candidate retrieval: uv run mir context pull \"$_TERMS\""
