#!/usr/bin/env bash
#
# secret-guard.sh — shared secret-leak protection for the daily-commit scripts.
#
# Source this file, then call `staged_is_safe "<repo-path-for-logs>"` AFTER you
# have staged the changes you intend to commit. It returns 0 if the staged
# changes are safe to commit, non-zero if anything sensitive was detected.
# It only inspects the index (git diff --cached); it never commits or unstages.
#
# Design goal: fail closed. Any hit -> the caller must NOT commit.

# Provide a log() if the caller didn't define one.
if ! declare -F log >/dev/null 2>&1; then
  log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
fi

# Max size (KB) for any single staged file. 0 = no limit.
GUARD_MAX_FILE_KB="${GUARD_MAX_FILE_KB:-${MAX_FILE_KB:-1024}}"

# Filenames/paths that should NEVER be auto-committed (case-insensitive).
# .example/.sample/.template variants are intentionally allowed.
GUARD_SENSITIVE_NAME_RE='(^|/)(\.env(\.[^/]*)?|\.envrc|\.netrc|\.npmrc|\.pypirc|\.dockercfg|\.htpasswd|id_(rsa|dsa|ecdsa|ed25519)|.*\.(pem|key|pfx|p12|jks|keystore|ppk|asc|gpg|kdbx)|.*credentials.*|.*secret.*|service[-_]?account.*\.json|.*-key\.json|.*\.kubeconfig|kubeconfig)$'
GUARD_SENSITIVE_NAME_ALLOW_RE='\.(example|sample|template|dist|tpl)$'

# Content patterns that indicate a secret in the staged diff.
GUARD_SECRET_CONTENT_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{22,}|xox[baprs]-[0-9A-Za-z-]{10,}|AIza[0-9A-Za-z_\-]{35}|sk_live_[0-9A-Za-z]{16,}|rk_live_[0-9A-Za-z]{16,}|sk-[A-Za-z0-9]{20,}|"private_key"[[:space:]]*:|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}|(aws_secret_access_key|client_secret|api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)[[:space:]]*[:=][[:space:]]*["'\'']?[A-Za-z0-9/+_.=-]{8,}'

# staged_is_safe <repo-label>
# Returns 0 if safe, non-zero if a secret/risk was found.
staged_is_safe() {
  local repo="${1:-$(pwd)}"
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

  # Layer 2 + 3: filename / path checks and oversized-blob checks.
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if echo "$f" | grep -qiE "$GUARD_SENSITIVE_NAME_RE" \
       && ! echo "$f" | grep -qiE "$GUARD_SENSITIVE_NAME_ALLOW_RE"; then
      log "BLOCK $repo — sensitive filename staged: $f"
      safe=1
    fi
    if [ "$GUARD_MAX_FILE_KB" -gt 0 ] && [ -f "$f" ]; then
      bytes=$(wc -c < "$f" 2>/dev/null || echo 0)
      kb=$(( bytes / 1024 ))
      if [ "$kb" -gt "$GUARD_MAX_FILE_KB" ]; then
        log "BLOCK $repo — oversized file staged (${kb}KB > ${GUARD_MAX_FILE_KB}KB): $f"
        safe=1
      fi
    fi
  done < <(git diff --cached --name-only)

  # Layer 4: content pattern scan of the staged diff (added lines only).
  # The `--` stops grep from treating the leading dashes of the private-key
  # pattern as command-line options.
  if git diff --cached -U0 | grep -E '^\+' | grep -qE -- "$GUARD_SECRET_CONTENT_RE"; then
    log "BLOCK $repo — staged content matches a secret pattern (key/token/credential)."
    safe=1
  fi

  return $safe
}
