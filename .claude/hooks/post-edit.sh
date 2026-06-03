#!/usr/bin/env bash
# PostToolUse hook for Edit|Write — auto-format edited files.
#
# Claude Code passes tool input as JSON on stdin. We extract file_path and run
# the appropriate formatter based on extension.

set -euo pipefail

INPUT="$(cat 2>/dev/null || true)"

# Extract file_path from tool input (best-effort; jq is optional)
if command -v jq >/dev/null 2>&1; then
    FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
    # Fallback: rough grep
    FILE=$(echo "$INPUT" | grep -oE '"file_path"\s*:\s*"[^"]+"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/' || true)
fi

if [ -z "${FILE:-}" ] || [ ! -f "$FILE" ]; then
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
REL="${FILE#$REPO_ROOT/}"

case "$FILE" in
    *.ts|*.tsx|*.js|*.jsx|*.json|*.md)
        if [[ "$REL" == frontend/* ]]; then
            (cd "$REPO_ROOT/frontend" && pnpm prettier --write --log-level=silent "$FILE" 2>/dev/null || true)
        fi
        ;;
esac

exit 0
