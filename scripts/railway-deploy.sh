#!/usr/bin/env bash
# Railway deployment helper for NovaCRM
# Run AFTER: railway login
# Usage: bash scripts/railway-deploy.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== NovaCRM Railway Deploy ==="
echo ""

# ── Check login ──────────────────────────────────────────────────────────────
if ! railway whoami &>/dev/null; then
  echo "ERROR: Not logged in. Run: railway login"
  exit 1
fi

echo "Logged in as: $(railway whoami)"
echo ""

# ── Project setup ─────────────────────────────────────────────────────────────
echo "Step 1: Initialize Railway project"
echo "  This will prompt you to create or link a project."
cd "$ROOT"
railway init

PROJECT_ID=$(railway status --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['projectId'])" 2>/dev/null || echo "")
echo "  Project ready."
echo ""

# ── Add Redis plugin ──────────────────────────────────────────────────────────
echo "Step 2: Adding Redis plugin..."
railway add --plugin redis || echo "  Redis may already exist, continuing."
echo ""

# ── Environment variables ────────────────────────────────────────────────────
echo "Step 3: Setting environment variables..."

# Load local env to use as defaults
API_ENV="$ROOT/apps/api/.env"
WEB_ENV="$ROOT/apps/web/.env.local"

# Source them safely
if [ -f "$API_ENV" ]; then
  export $(grep -v '^#' "$API_ENV" | xargs -d '\n') 2>/dev/null || true
fi
if [ -f "$WEB_ENV" ]; then
  export $(grep -v '^#' "$WEB_ENV" | xargs -d '\n') 2>/dev/null || true
fi

# Prompt for missing DATABASE_URL
if [ -z "${DATABASE_URL_SUPABASE:-}" ]; then
  echo ""
  echo "  REQUIRED: Supabase database URL"
  echo "  Go to: Supabase Dashboard → Settings → Database → Connection string"
  echo "  Copy the 'Transaction pooler' URI and change 'postgresql://' to 'postgresql+asyncpg://'"
  echo "  Example: postgresql+asyncpg://postgres.ilfibxflnelssllgszex:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
  echo ""
  read -r -p "  Paste DATABASE_URL: " DATABASE_URL_SUPABASE
fi

FRONTEND_URL=$(railway status --json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for svc in data.get('services', []):
    if svc.get('name', '').lower() == 'web':
        print(svc.get('url', ''))
" 2>/dev/null || echo "https://novacrm.up.railway.app")

echo "  Setting API service vars..."
railway variables --service api set \
  DATABASE_URL="$DATABASE_URL_SUPABASE" \
  SUPABASE_URL="${SUPABASE_URL}" \
  SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY}" \
  SUPABASE_JWT_SECRET="${SUPABASE_JWT_SECRET}" \
  SECRET_KEY="${SECRET_KEY}" \
  ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  FRONTEND_URL="${FRONTEND_URL}" \
  GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}" \
  GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}" \
  SLACK_CLIENT_ID="${SLACK_CLIENT_ID:-}" \
  SLACK_CLIENT_SECRET="${SLACK_CLIENT_SECRET:-}" \
  2>/dev/null || echo "  (vars set manually — check Railway dashboard)"

echo "  Setting web service vars..."
railway variables --service web set \
  NEXT_PUBLIC_SUPABASE_URL="${NEXT_PUBLIC_SUPABASE_URL}" \
  NEXT_PUBLIC_SUPABASE_ANON_KEY="${NEXT_PUBLIC_SUPABASE_ANON_KEY}" \
  NEXT_PUBLIC_DEMO_MODE="false" \
  SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY}" \
  SUPABASE_JWT_SECRET="${SUPABASE_JWT_SECRET}" \
  2>/dev/null || echo "  (vars set manually — check Railway dashboard)"

echo ""
echo "Step 4: Deploying..."
echo "  NOTE: worker and beat services need to be created manually in Railway dashboard"
echo "  pointing to apps/api with start commands:"
echo "    worker: celery -A app.workers.celery_app worker --loglevel=info --concurrency=2"
echo "    beat:   celery -A app.workers.celery_app beat --loglevel=info"
echo ""

railway up --service api --detach
railway up --service web --detach

echo ""
echo "=== Deploy queued ==="
echo "Monitor at: https://railway.app/dashboard"
echo ""
echo "NEXT_PUBLIC_FASTAPI_URL must be set on the web service after the API URL is known."
echo "Go to: Railway → web service → Variables → Add NEXT_PUBLIC_FASTAPI_URL=<api-url>"
