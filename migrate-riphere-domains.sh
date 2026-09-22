#!/usr/bin/env bash
# ============================================================================
# NovaCRM domain migration — riphere.com  ->  app.riphere.com (web) + api.riphere.com (api)
# Frees the riphere.com apex + www for the personal portfolio (Cloudflare Pages).
#
# Prereqs:
#   - railway CLI logged in (it is), project NovaCRM linked (it is)
#   - export CLOUDFLARE_API_TOKEN=...   (scoped: Zone:DNS:Edit + Zone:Read on riphere.com)
#
# Run phases IN ORDER. Each phase is idempotent-ish and prints what it does.
# Phase A is safe NOW. Phases B/C mutate the live CRM — read the guards.
# ============================================================================
set -euo pipefail

ZONE="riphere.com"
API_TARGET="f6scelgo.up.railway.app"                 # railway api-service CNAME target (already issued)
API_VERIFY="railway-verify=16ac6966fc8fd3744dcc5366bd282bb2aa92cb89af1e33c46b36b28b36f7e7f4"
WEB_TARGET="40jthhou.up.railway.app"                 # railway web-service CNAME target for app.riphere.com (LIVE)
APP_VERIFY="railway-verify=aaacfa44cd8bb2b5c1bae0fa96fd88cc4511b0b70bb1860770118cf32bbcbd9f"

: "${CLOUDFLARE_API_TOKEN:?export CLOUDFLARE_API_TOKEN first (Zone:DNS:Edit on riphere.com)}"
CF="https://api.cloudflare.com/client/v4"
auth=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json")

zone_id() {
  curl -s "${auth[@]}" "${CF}/zones?name=${ZONE}" | jq -r '.result[0].id // empty'
}
# upsert <type> <name> <content> <proxied true|false>
upsert() {
  local type="$1" name="$2" content="$3" proxied="$4" zid; zid="$(zone_id)"
  [ -n "$zid" ] || { echo "!! could not resolve zone id for ${ZONE} (token scope?)"; exit 1; }
  local existing; existing=$(curl -s "${auth[@]}" "${CF}/zones/${zid}/dns_records?type=${type}&name=${name}" | jq -r '.result[0].id // empty')
  local body; body=$(jq -nc --arg t "$type" --arg n "$name" --arg c "$content" --argjson p "$proxied" \
    '{type:$t,name:$n,content:$c,proxied:$p,ttl:1}')
  if [ -n "$existing" ]; then
    echo ">> updating ${type} ${name} -> ${content} (proxied=${proxied})"
    curl -s "${auth[@]}" -X PUT "${CF}/zones/${zid}/dns_records/${existing}" --data "$body" | jq -r '.success'
  else
    echo ">> creating ${type} ${name} -> ${content} (proxied=${proxied})"
    curl -s "${auth[@]}" -X POST "${CF}/zones/${zid}/dns_records" --data "$body" | jq -r '.success'
  fi
}

phase="${1:-help}"
case "$phase" in
  # ---- PHASE A: api DNS (SAFE NOW — api.riphere.com is already added in Railway) ----
  A|api)
    echo "== Phase A: Cloudflare DNS for api.riphere.com =="
    # DNS-only (grey cloud) so Railway can validate ownership + issue the cert cleanly.
    upsert CNAME "api.${ZONE}"            "$API_TARGET"  false
    upsert TXT   "_railway-verify.api.${ZONE}" "$API_VERIFY" false
    echo ">> now poll: railway domain status 3d900fb5-6796-4dee-9357-2db36d183423"
    echo ">> verify:   curl -s https://api.${ZONE}/health"
    ;;

  # ---- PHASE B: app DNS (SAFE NOW — app.riphere.com already added to web; apex slot freed) ----
  B|app)
    echo "== Phase B: Cloudflare DNS for app.riphere.com =="
    # DNS-only (grey cloud) so Railway can validate ownership + issue the cert cleanly.
    upsert CNAME "app.${ZONE}"            "$WEB_TARGET"  false
    upsert TXT   "_railway-verify.app.${ZONE}" "$APP_VERIFY" false
    echo ">> poll:   railway domain status 3cd66a09-2330-4e8e-add6-be7265e564b6"
    echo ">> verify: curl -sI https://app.${ZONE}/   # expect the CRM"
    ;;

  # ---- PHASE C: flip CRM env vars to the new domains (BREAKS logins until OAuth updated) ----
  C|env)
    echo "== Phase C: Railway env vars =="
    echo "!! Do step 4 (Google + Slack OAuth redirect URIs) in the consoles FIRST, or logins break."
    read -rp "OAuth redirect URIs already updated for api.riphere.com? [yes/N] " ok
    [ "$ok" = "yes" ] || { echo "aborted"; exit 1; }
    railway variables --set "API_URL=https://api.${ZONE}"               -s api    -e production
    railway variables --set "API_URL=https://api.${ZONE}"               -s worker -e production
    railway variables --set "API_URL=https://api.${ZONE}"               -s beat   -e production
    railway variables --set "NEXT_PUBLIC_FASTAPI_URL=https://api.${ZONE}" -s web  -e production
    railway variables --set "FRONTEND_URL=https://app.${ZONE}"          -s web    -e production
    railway variables --set "FRONTEND_URL=https://app.${ZONE}"          -s api    -e production
    echo ">> redeploys triggered. Verify a real Gmail + Slack OAuth round-trip."
    ;;

  *)
    cat <<EOF
Usage: CLOUDFLARE_API_TOKEN=... ./migrate-riphere-domains.sh <phase>
  A | api   DNS for api.riphere.com         (SAFE — run now)
  B | app   app.riphere.com on web + DNS    (needs free web slot / plan upgrade)
  C | env   flip CRM env vars to new domains (run AFTER OAuth consoles updated)
Manual step (no good CLI): add redirect URIs in Google Cloud Console + Slack app.
Then in Cloudflare, repoint riphere.com + www to the Pages project for the portfolio.
EOF
    ;;
esac
