#!/usr/bin/env bash
#
# daily-commit.sh — commit and push the REAL work you've done in this repo.
#
# This is intentionally honest automation: it only creates a commit when there
# are actual uncommitted changes in your working tree. On days you don't touch
# the project, nothing happens and nothing is faked. It just stops your genuine
# work from sitting uncommitted and missing the contribution graph.
#
# Recommended use: run it on a schedule via cron (see install instructions at
# the bottom of this file), and/or run it manually at the end of a work session.
#
set -euo pipefail

# Shared secret-leak protection (provides staged_is_safe).
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/secret-guard.sh"

# --- Configuration -----------------------------------------------------------
# Absolute path to the repository this script should commit in.
# Defaults to the repo this script lives in.
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Branch to commit/push to. Empty = use the currently checked-out branch.
TARGET_BRANCH="${TARGET_BRANCH:-}"

# By default, stage only already-tracked modifications. Untracked files (the
# usual home of a stray .env/key) are excluded unless you opt in.
INCLUDE_UNTRACKED="${INCLUDE_UNTRACKED:-0}"
# -----------------------------------------------------------------------------

cd "$REPO_DIR"

# Bail out cleanly if there's nothing real to commit. No empty/filler commits.
if [ -z "$(git status --porcelain)" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') — no changes to commit, skipping."
  exit 0
fi

if [ -n "$TARGET_BRANCH" ]; then
  git checkout "$TARGET_BRANCH"
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
stamp="$(date '+%Y-%m-%d')"

# Stage conservatively, starting from a clean index so the secret scan only
# sees what we are about to commit.
git reset -q
if [ "$INCLUDE_UNTRACKED" = "1" ]; then
  git add -A
else
  git add -u
fi

if [ -z "$(git diff --cached --name-only)" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') — only untracked files present (set INCLUDE_UNTRACKED=1 to include); nothing to commit."
  git reset -q
  exit 0
fi

# SECRET GATE — fail closed. If anything looks sensitive, commit nothing.
if ! staged_is_safe "$REPO_DIR"; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') — left uncommitted for manual review. Fix/ignore the flagged item, then commit by hand." >&2
  git reset -q
  exit 1
fi

# Build a commit message that reflects what actually changed.
files_changed="$(git diff --cached --name-only | wc -l | tr -d ' ')"
summary="$(git diff --cached --name-only | head -5 | paste -sd ', ' -)"

git commit -m "chore: daily work checkpoint ($stamp)" \
           -m "${files_changed} file(s) changed: ${summary}"

# Push with a few retries for flaky networks.
for attempt in 1 2 3 4; do
  if git push -u origin "$branch"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') — committed and pushed to $branch."
    exit 0
  fi
  wait=$((2 ** attempt))
  echo "push failed, retrying in ${wait}s..."
  sleep "$wait"
done

echo "ERROR: commit succeeded but push failed after retries." >&2
exit 1

# --- How to schedule this with cron ------------------------------------------
#
# 1. Make it executable (already done if you cloned this):
#       chmod +x scripts/daily-commit.sh
#
# 2. Open your crontab:
#       crontab -e
#
# 3. Add a line. This runs every day at 6:00 PM, committing whatever real work
#    you did that day. Adjust the path and time to taste:
#
#       0 18 * * * REPO_DIR="$HOME/path/to/crm-agentic" /bin/bash "$HOME/path/to/crm-agentic/scripts/daily-commit.sh" >> "$HOME/daily-commit.log" 2>&1
#
#    (cron has a minimal environment, so use absolute paths and set REPO_DIR.)
#
# 4. Check it's installed:
#       crontab -l
#
# Tip: this only greens days you actually worked. If you want more consistent
# green, the real lever is committing more often — not faking days. Running this
# at end-of-session, or committing per-feature, will reflect your work honestly.
#
# --- Secret-leak protection --------------------------------------------------
# This script shares the same fail-closed secret gate as daily-commit-all.sh
# (scripts/lib/secret-guard.sh):
# - Stages tracked changes only by default; set INCLUDE_UNTRACKED=1 to include
#   new files (riskier — that's where stray .env/keys usually live).
# - Blocks sensitive filenames (.env, *.pem/*.key, id_rsa, *credentials*, ...),
#   secret content patterns (private keys, AWS/GitHub/Slack/Google/Stripe/OpenAI
#   tokens, JWTs, api_key/password assignments), oversized files, and uses
#   gitleaks/git-secrets if installed.
# - On ANY hit it unstages and exits WITHOUT committing, for manual review.
#
# Also install the global gitignore template as a first line of defense:
#   cp scripts/gitignore_global.template ~/.gitignore_global
#   git config --global core.excludesfile ~/.gitignore_global
# -----------------------------------------------------------------------------
