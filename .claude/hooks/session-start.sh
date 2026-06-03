#!/usr/bin/env bash
# SessionStart hook — fetch latest, warn if branch is stale or working tree dirty.

set -uo pipefail

# Only run inside a git repo
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    exit 0
fi

# Background fetch (don't block session start on slow network)
(git fetch --all --quiet 2>/dev/null &) >/dev/null 2>&1

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

if [ -n "$BRANCH" ] && [ "$BRANCH" != "main" ] && [ "$BRANCH" != "develop" ] && [ "$BRANCH" != "HEAD" ]; then
    # Find merge-base with develop
    MERGE_BASE=$(git merge-base HEAD develop 2>/dev/null || echo "")
    if [ -n "$MERGE_BASE" ]; then
        BASE_TS=$(git log -1 --format=%ct "$MERGE_BASE" 2>/dev/null || echo "0")
        NOW_TS=$(date +%s)
        AGE_DAYS=$(( (NOW_TS - BASE_TS) / 86400 ))
        if [ "$AGE_DAYS" -gt 5 ]; then
            cat >&2 <<EOF
⚠ Branch '$BRANCH' is $AGE_DAYS days behind develop.

Sidis Dev Process v1.0 section 4.1.5 (D): branches >5 days are at risk of
heavy merge conflicts. Consider:
  - rebasing onto latest develop:  git fetch && git rebase develop
  - splitting Story into smaller subtasks (use /sidis-decompose-story)
  - using a feature flag for incremental delivery
EOF
        fi
    fi
fi

# Warn about uncommitted changes
DIRTY=$(git status --porcelain 2>/dev/null || echo "")
if [ -n "$DIRTY" ]; then
    LINES=$(echo "$DIRTY" | wc -l | tr -d ' ')
    echo "ℹ Working tree has $LINES uncommitted change(s). Run 'git status' to see them." >&2
fi

exit 0
