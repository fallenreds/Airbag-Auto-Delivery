#!/usr/bin/env bash
# PreToolUse hook for Bash — enforce Sidis flow rules.
#
# Blocks:
#   - git push to main/develop (must use PR flow)
#   - git push --force without --force-with-lease
#   - git commit --no-verify (bypasses pre-commit)
#
# Runs (warns but does not block):
#   - pre-commit on git commit (warning if pre-commit not installed)

set -euo pipefail

INPUT="$(cat 2>/dev/null || true)"

if command -v jq >/dev/null 2>&1; then
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
    CMD=$(echo "$INPUT" | grep -oE '"command"\s*:\s*"[^"]+"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/' || true)
fi

if [ -z "${CMD:-}" ]; then
    exit 0
fi

# === Block: push to main/develop ===
if echo "$CMD" | grep -qE 'git[[:space:]]+push.*\b(main|develop)\b' && \
   ! echo "$CMD" | grep -q -- '--dry-run'; then
    cat >&2 <<EOF
✗ Sidis flow violation: push directly to main/develop is forbidden.

Use the Pull Request flow:
  - For feature work: branch off develop, open PR via /sidis-create-pr
  - For hotfix:       branch off main, follow /sidis-hotfix flow

If this is a backmerge after merged hotfix, use:
  git push origin develop --dry-run     # to preview, then drop --dry-run
EOF
    exit 2  # exit code 2 → Claude Code displays as error and aborts the tool call
fi

# === Block: force push without lease ===
if echo "$CMD" | grep -qE 'git[[:space:]]+push.*--force\b' && \
   ! echo "$CMD" | grep -q -- '--force-with-lease'; then
    cat >&2 <<EOF
✗ Sidis flow violation: 'git push --force' without --force-with-lease is forbidden.

Use --force-with-lease instead:
  git push --force-with-lease origin <branch>

This protects from overwriting concurrent pushes.
EOF
    exit 2
fi

# === Block: --no-verify ===
if echo "$CMD" | grep -qE 'git[[:space:]]+commit.*--no-verify\b'; then
    cat >&2 <<EOF
✗ Sidis flow violation: 'git commit --no-verify' bypasses pre-commit hooks.

Per Sidis Dev Process v1.0 section 4.1.6 — fix the issue, don't bypass.
EOF
    exit 2
fi

# === Warn (non-blocking): commit without pre-commit installed ===
if echo "$CMD" | grep -qE 'git[[:space:]]+commit\b' && \
   [ -d .git ] && [ ! -f .git/hooks/pre-commit ]; then
    echo "⚠ pre-commit hook not installed locally. Run: pre-commit install" >&2
fi

exit 0
