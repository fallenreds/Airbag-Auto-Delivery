#!/usr/bin/env bash
# PreToolUse hook for Bash — git safety rules.
#
# Blocks:
#   - git push --force without --force-with-lease
#   - git commit --no-verify (bypasses pre-commit)
#   - git commit / git push while on a protected branch (master|main|develop)
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

# === Block: commit/push directly into a protected branch ===
if echo "$CMD" | grep -qE 'git[[:space:]]+.*\b(commit|push)\b'; then
    # honour `git -C <path> ...` so the rule also covers the frontend submodule
    REPO_DIR=$(echo "$CMD" | grep -oE 'git[[:space:]]+-C[[:space:]]+[^[:space:]]+' | head -1 | awk '{print $3}' || true)
    REPO_DIR=${REPO_DIR:-.}

    BRANCH=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)

    if echo "${BRANCH:-}" | grep -qE '^(master|main|develop)$'; then
        cat >&2 <<EOF
✗ Прямой commit/push в основную ветку ($BRANCH) запрещён.

Новые изменения всегда идут в отдельной ветке. Создайте её:
  git -C $REPO_DIR checkout -b feat/<описание>

Затем повторите команду. Интеграция в $BRANCH — только через Pull Request.
EOF
        exit 2
    fi
fi

# === Warn (non-blocking): commit without pre-commit installed ===
if echo "$CMD" | grep -qE 'git[[:space:]]+commit\b' && \
   [ -d .git ] && [ ! -f .git/hooks/pre-commit ]; then
    echo "⚠ pre-commit hook not installed locally. Run: pre-commit install" >&2
fi

exit 0
