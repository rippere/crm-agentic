#!/usr/bin/env bash
#
# daily-commit-all.sh — sweep ALL your local git repos and commit the real work,
#                       with secret-leak protection.
#
# Scans one or more parent directories for git repositories and, for each repo
# that has actual uncommitted changes, makes a "daily checkpoint" commit and
# pushes it. Repos with a clean working tree are skipped — no empty or filler
# commits are ever created.
#
# SAFETY MODEL (fail-closed): before committing, every staged change is scanned
# for secrets. If anything sensitive is detected, the repo is UNSTAGED and
# SKIPPED entirely — nothing is committed or pushed. The default is to never
# leak; you have to consciously fix the finding before that repo is committed.
#
set -uo pipefail   # note: no -e, so one bad repo doesn't abort the whole sweep

# Shared secret-leak protection (provides staged_is_safe).
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/secret-guard.sh"

# --- Configuration -----------------------------------------------------------
# Space-separated list of directories to scan for git repos.
SCAN_DIRS="${SCAN_DIRS:-$HOME/code $HOME/projects $HOME/src}"

# How deep to look for repos under each scan dir.
MAXDEPTH="${MAXDEPTH:-3}"

# Set to 1 to see what would happen without committing/pushing.
DRY_RUN="${DRY_RUN:-0}"

# By default we ONLY stage already-tracked modified files (git add -u). New
# untracked files are the most common way secrets slip in (a fresh .env, a
# downloaded key), so they are NOT auto-committed unless you opt in.
INCLUDE_UNTRACKED="${INCLUDE_UNTRACKED:-0}"

# Max size (KB) for any single staged file. Large blobs are often DB dumps,
# key bundles, or archives and are skipped as a precaution. 0 = no limit.
MAX_FILE_KB="${MAX_FILE_KB:-1024}"
# -----------------------------------------------------------------------------

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

# staged_is_safe() is provided by lib/secret-guard.sh (sourced above).

commit_repo() {
  local repo="$1"
  cd "$repo" || return

  # Per-repo opt-out: drop a `.no-auto-commit` file in any repo to exclude it.
  if [ -f ".no-auto-commit" ]; then
    log "SKIP $repo — .no-auto-commit marker present."
    return
  fi

  # Skip if nothing real changed.
  if [ -z "$(git status --porcelain)" ]; then
    return
  fi

  local branch stamp
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || return
  if [ "$branch" = "HEAD" ]; then
    log "SKIP $repo — detached HEAD, leaving it alone."
    return
  fi

  # Start from a clean index so our scan only sees what WE are about to commit.
  git reset -q

  # Stage conservatively: tracked modifications only, unless untracked opted in.
  if [ "$INCLUDE_UNTRACKED" = "1" ]; then
    git add -A
  else
    git add -u
  fi

  # Nothing ended up staged (e.g. only untracked files and we excluded them).
  if [ -z "$(git diff --cached --name-only)" ]; then
    log "SKIP $repo — only untracked files present (set INCLUDE_UNTRACKED=1 to include)."
    git reset -q
    return
  fi

  # SECRET GATE — fail closed. If anything looks sensitive, commit nothing.
  if ! staged_is_safe "$repo"; then
    log "SKIPPED $repo — left uncommitted for manual review. Fix/ignore the flagged item, then commit by hand."
    git reset -q
    return
  fi

  local files_changed summary
  files_changed="$(git diff --cached --name-only | wc -l | tr -d ' ')"
  summary="$(git diff --cached --name-only | head -5 | paste -sd ', ' -)"
  stamp="$(date '+%Y-%m-%d')"

  if [ "$DRY_RUN" = "1" ]; then
    log "DRY-RUN $repo ($branch): would commit ${files_changed} file(s): ${summary}"
    git reset -q
    return
  fi

  log "COMMIT $repo ($branch): ${files_changed} file(s): ${summary}"
  git commit -q -m "chore: daily work checkpoint ($stamp)" \
                -m "${files_changed} file(s) changed: ${summary}" || return

  # Push with retries for flaky networks. Only push if a remote exists.
  if git remote | grep -q .; then
    local attempt wait
    for attempt in 1 2 3 4; do
      if git push -q -u origin "$branch" 2>/dev/null; then
        log "PUSHED $repo -> $branch"
        return
      fi
      wait=$((2 ** attempt))
      log "push failed for $repo, retry in ${wait}s..."
      sleep "$wait"
    done
    log "WARN $repo — committed locally but push failed after retries."
  else
    log "NOTE $repo — committed locally (no remote configured)."
  fi
}

main() {
  for dir in $SCAN_DIRS; do
    [ -d "$dir" ] || continue
    while IFS= read -r gitdir; do
      commit_repo "$(dirname "$gitdir")"
    done < <(find "$dir" -maxdepth "$MAXDEPTH" -type d -name .git 2>/dev/null)
  done
  log "sweep complete."
}

main "$@"

# --- How to schedule this with cron ------------------------------------------
#
# 1. Make it executable:
#       chmod +x scripts/daily-commit-all.sh
#
# 2. (Strongly recommended) install a real secret scanner so Layer 1 is active:
#       brew install gitleaks        # macOS
#       # or see https://github.com/gitleaks/gitleaks for other platforms
#
# 3. Dry-run to confirm which repos it finds and that nothing unexpected stages:
#       SCAN_DIRS="$HOME/code $HOME/projects" DRY_RUN=1 ./scripts/daily-commit-all.sh
#
# 4. Schedule via crontab -e (edit paths/time):
#       0 23 * * * SCAN_DIRS="$HOME/code $HOME/projects" /bin/bash "$HOME/path/to/crm-agentic/scripts/daily-commit-all.sh" >> "$HOME/daily-commit.log" 2>&1
#
# 5. Watch the log, especially for BLOCK/SKIPPED lines:
#       tail -f "$HOME/daily-commit.log"
#
# --- Secret-leak safeguards in this script -----------------------------------
# 1. Tracked-only by default: new untracked files (the usual home of a stray
#    .env or key) are NOT committed unless INCLUDE_UNTRACKED=1.
# 2. Filename gate: blocks .env, *.pem/*.key/*.p12, id_rsa, *credentials*,
#    serviceAccount*.json, kubeconfig, etc. (.example/.sample are allowed).
# 3. Content gate: scans the staged diff for private keys, AWS/GitHub/Slack/
#    Google/Stripe/OpenAI tokens, JWTs, and api_key/password=... assignments.
# 4. External scanner: uses gitleaks or git-secrets if installed.
# 5. Size gate: skips files larger than MAX_FILE_KB (default 1MB).
# 6. Fail-closed: ANY hit -> the repo is unstaged and skipped, never committed.
# 7. Per-repo opt-out: drop a `.no-auto-commit` file in a repo to exclude it.
#
# DEFENSE IN DEPTH — do these too, they matter more than any script:
# - Keep a solid global gitignore covering .env, *.pem, *.key, etc.:
#       git config --global core.excludesfile ~/.gitignore_global
# - Never store real secrets inside the repo working tree; use a secrets
#   manager or files OUTSIDE the repo.
# - A blocked finding means STOP and fix it by hand. Do not "just commit it"
#   to clear the warning — if a secret is ever pushed, rotate it immediately;
#   deleting it later does not un-leak it (history, forks, and caches remain).
# -----------------------------------------------------------------------------
