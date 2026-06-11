#!/usr/bin/env bash
#
# daily-commit-all.sh — sweep ALL your local git repos and commit the real work.
#
# Scans one or more parent directories for git repositories and, for each repo
# that has actual uncommitted changes, makes a "daily checkpoint" commit and
# pushes it. Repos with a clean working tree are skipped — no empty or filler
# commits are ever created.
#
# This captures whatever you genuinely worked on that day across every project,
# not just one. Run it on a schedule via cron (see bottom of this file).
#
set -uo pipefail   # note: no -e, so one bad repo doesn't abort the whole sweep

# --- Configuration -----------------------------------------------------------
# Space-separated list of directories to scan for git repos. Each is searched
# recursively (up to MAXDEPTH levels) for ".git" folders.
# Override by exporting SCAN_DIRS, e.g.:
#   SCAN_DIRS="$HOME/code $HOME/projects" ./daily-commit-all.sh
SCAN_DIRS="${SCAN_DIRS:-$HOME/code $HOME/projects $HOME/src}"

# How deep to look for repos under each scan dir.
MAXDEPTH="${MAXDEPTH:-3}"

# Set to 1 to see what would happen without committing/pushing.
DRY_RUN="${DRY_RUN:-0}"
# -----------------------------------------------------------------------------

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

commit_repo() {
  local repo="$1"
  cd "$repo" || return

  # Skip if nothing real changed.
  if [ -z "$(git status --porcelain)" ]; then
    return
  fi

  local branch files_changed summary stamp
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || return
  if [ "$branch" = "HEAD" ]; then
    log "SKIP $repo — detached HEAD, leaving it alone."
    return
  fi

  files_changed="$(git status --porcelain | wc -l | tr -d ' ')"
  summary="$(git status --porcelain | awk '{print $2}' | head -5 | paste -sd ', ' -)"
  stamp="$(date '+%Y-%m-%d')"

  if [ "$DRY_RUN" = "1" ]; then
    log "DRY-RUN $repo ($branch): would commit ${files_changed} file(s): ${summary}"
    return
  fi

  log "COMMIT $repo ($branch): ${files_changed} file(s): ${summary}"
  git add -A
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
    # Find .git directories, hand each repo root to commit_repo.
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
# 2. First, do a dry run to confirm it finds the repos you expect:
#       SCAN_DIRS="$HOME/code $HOME/projects" DRY_RUN=1 ./scripts/daily-commit-all.sh
#
# 3. Open your crontab:
#       crontab -e
#
# 4. Add a line. Runs every evening at 11:00 PM across all your repos. Edit the
#    paths and time to match where your code lives and when you finish working:
#
#       0 23 * * * SCAN_DIRS="$HOME/code $HOME/projects" /bin/bash "$HOME/path/to/crm-agentic/scripts/daily-commit-all.sh" >> "$HOME/daily-commit.log" 2>&1
#
#    (cron runs with a minimal environment — use absolute paths and set
#    SCAN_DIRS explicitly. $HOME is usually available; if not, hardcode it.)
#
# 5. Verify it's installed:
#       crontab -l
#
# 6. Watch the log to confirm it's behaving:
#       tail -f "$HOME/daily-commit.log"
#
# Notes:
# - Only repos with real uncommitted changes get a commit. Clean repos are
#   skipped, so days you didn't work stay blank — this records work, it doesn't
#   invent it.
# - For the green squares to count on github.com, the commit's author email must
#   match a verified email on your GitHub account. Check with:
#       git config user.email
#   and make sure that address is listed under GitHub > Settings > Emails.
# -----------------------------------------------------------------------------
