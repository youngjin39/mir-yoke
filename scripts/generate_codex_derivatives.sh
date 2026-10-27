#!/bin/bash
# Compatibility entrypoint; the portable generator owns all behavior.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/generate_codex_derivatives.py" "$@"
