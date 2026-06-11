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

# Filenames/paths that should NEVER be auto-committed (case-insensitive regex).
# .example/.sample/.template variants are intentionally allowed.
SENSITIVE_NAME_RE='(^|/)(\.env(\.[^/]*)?|\.envrc|\.netrc|\.npmrc|\.pypirc|\.dockercfg|\.htpasswd|id_(rsa|dsa|ecdsa|ed25519)|.*\.(pem|key|pfx|p12|jks|keystore|ppk|asc|gpg|kdbx)|.*credentials.*|.*secret.*|service[-_]?account.*\.json|.*-key\.json|.*\.kubeconfig|kubeconfig)$'
SENSITIVE_NAME_ALLOW_RE='\.(example|sample|template|dist|tpl)$'

# Content patterns that indicate a secret in the staged diff.
SECRET_CONTENT_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{22,}|xox[baprs]-[0-9A-Za-z-]{10,}|AIza[0-9A-Za-z_\-]{35}|sk_live_[0-9A-Za-z]{16,}|rk_live_[0-9A-Za-z]{16,}|sk-[A-Za-z0-9]{20,}|"private_key"[[:space:]]*:|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}|(aws_secret_access_key|client_secret|api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)[[:space:]]*[:=][[:space:]]*["'\'']?[A-Za-z0-9/+_.=-]{8,}'

# Returns 0 (success) if the staged changes are SAFE, non-zero if a secret/risk
# was found. Logs every reason it flags.
staged_is_safe() {
  local repo="$1"
  local safe=0 f bytes kb

  # Layer 1: external scanners, if installed (most authoritative).
  if command -v gitleaks >/dev/null 2>&1; then
    if ! gitleaks protect --staged --no-banner >/dev/null 2>&1; then
      log "BLOCK $repo — gitleaks flagged a secret in staged changes."
      safe=1
    fi
  elif command -v git-secrets >/dev/null 2>&1; then
    if ! git secrets --scan >/dev/null 2>&1; then
      log "BLOCK $repo — git-secrets flagged a secret."
      safe=1
    fi
  fi

  # Layer 2: filename / path checks on staged files.
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if echo "$f" | grep -qiE "$SENSITIVE_NAME_RE" \
       && ! echo "$f" | grep -qiE "$SENSITIVE_NAME_ALLOW_RE"; then
      log "BLOCK $repo — sensitive filename staged: $f"
      safe=1
    fi
    # Layer 3: oversized blob check.
    if [ "$MAX_FILE_KB" -gt 0 ] && [ -f "$f" ]; then
      bytes=$(wc -c < "$f" 2>/dev/null || echo 0)
      kb=$(( bytes / 1024 ))
      if [ "$kb" -gt "$MAX_FILE_KB" ]; then
        log "BLOCK $repo — oversized file staged (${kb}KB > ${MAX_FILE_KB}KB): $f"
        safe=1
      fi
    fi
  done < <(git diff --cached --name-only)

  # Layer 4: content pattern scan of the staged diff (added lines only).
  if git diff --cached -U0 | grep -E '^\+' | grep -qE -- "$SECRET_CONTENT_RE"; then
    log "BLOCK $repo — staged content matches a secret pattern (key/token/credential)."
    safe=1
  fi

  return $safe
}

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
