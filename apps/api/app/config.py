from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_env_file = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_env_file), extra="ignore")

    SUPABASE_URL: str
    DATABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str
    SECRET_KEY: str
    ANTHROPIC_API_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"
    FRONTEND_URL: str = "http://localhost:3000"
    # Comma-separated additional allowed CORS origins (e.g. apex domain, old deploy URL).
    CORS_ORIGINS: str = ""
    # Optional regex for allowed origins (e.g. r"https://(.*\.)?riphere\.com").
    CORS_ORIGIN_REGEX: str = ""
    API_URL: str = "http://localhost:8000"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""
    SLACK_SIGNING_SECRET: str = ""
    SLACK_HITL_CHANNEL: str = "general"
    HUNTER_API_KEY: str = ""
    # Gmail push notifications (Google Pub/Sub)
    GMAIL_WEBHOOK_SECRET: str = ""  # shared secret appended to webhook URL
    GMAIL_PUBSUB_TOPIC: str = ""    # e.g. projects/myproject/topics/gmail-push

    # ── F3: per-request DB tenant context (RLS backstop) ─────────────────────
    # When True, each request transaction emits `SET LOCAL app.current_workspace_id`
    # (+ request.jwt.claims) carrying the authenticated user's workspace, so the
    # workspace RLS policies in migration 013 resolve under a non-BYPASSRLS role.
    # DEFAULT False: INERT in prod. The current DATABASE_URL connects as a
    # BYPASSRLS/owner role for which FORCE RLS does nothing, so toggling this on
    # without the ops role-swap changes NOTHING observable. Flip to True only as
    # part of the cutover documented atop migrations/013_force_rls.sql.
    DB_RLS_CONTEXT_ENABLED: bool = False
    # GUC key the SET LOCAL writes. Must match the policy expression if a future
    # policy reads a GUC directly; 013's policies read auth.uid() via
    # request.jwt.claims, which is also set, so this is a defense-in-depth alias.
    DB_RLS_GUC_KEY: str = "app.current_workspace_id"

    # ── F5: per-workspace LLM spend cap (Redis token budget) ─────────────────
    # Generous / effectively-off defaults so prod is NOT throttled unexpectedly
    # by enabling this code. Tune down per ops once observed.
    LLM_BUDGET_ENABLED: bool = False           # master switch; off by default
    LLM_BUDGET_TOKENS_PER_WINDOW: int = 50_000_000  # tokens per workspace per window
    LLM_BUDGET_WINDOW_SECONDS: int = 86_400    # rolling window length (24h)
    # Heuristic token estimate for one full-workspace reprocess pass, used to
    # check-and-reserve before enqueuing the (otherwise unbounded) fan-out.
    LLM_BUDGET_TOKENS_PER_MESSAGE: int = 4_000  # ~4 model calls (3 Haiku + 1 Sonnet)
    # Hard ceiling on messages processed per single reprocess call. Bounds the
    # per-call model fan-out regardless of workspace size.
    REPROCESS_MAX_MESSAGES: int = 2_000

    # ── F5: per-tenant rate limiting ─────────────────────────────────────────
    # Rate limit applied to POST /messages/reprocess (the heaviest amplifier,
    # previously un-decorated).
    REPROCESS_RATE_LIMIT: str = "3/minute"

    # ── F5: long-job queue isolation (opt-in, deploy-safe) ───────────────────
    # When True, heavy/long-running tasks (reprocess + transcribe) are routed to a
    # dedicated low-concurrency `long` Celery queue so they cannot pin the 2-slot
    # pool that serves short enrich/scoring jobs. DEFAULT False so this is safe to
    # DEPLOY ALONE: with it off, those tasks stay on the `default` queue and the
    # existing worker keeps consuming them. Flip to True ONLY once a `long`-queue
    # consumer exists (worker started with `-Q default,long`); see
    # workers/celery_app.py.
    LONG_QUEUE_ENABLED: bool = False


settings = Settings()
