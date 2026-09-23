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
    # Bounds every Anthropic client (see app/services/llm.py). Without a request
    # timeout the SDK retries with unbounded exponential backoff on rate-limit /
    # credit-exhaustion and the calling task hangs ("enrichment times out").
    ANTHROPIC_TIMEOUT: float = 30.0
    ANTHROPIC_MAX_RETRIES: int = 2
    # ── Ingest token-safety bounds ──────────────────────────────────────────
    # Hard cap on how many Gmail messages a single sync run will process, so one
    # ingest can never fan out LLM calls across an entire multi-year mailbox.
    INGEST_MAX_MESSAGES: int = 200
    # Only ingest mail newer than this many days (Gmail `newer_than:` filter),
    # so connecting an account pulls recent history, not years of backlog.
    INGEST_SINCE_DAYS: int = 30
    # Backstop per-run ceiling on Claude calls (relevance checks + 3 per enrich
    # dispatch). Sized above the INGEST_MAX_MESSAGES worst case (200 relevance +
    # 200×3 enrich = 800) so it never trips in normal operation, but bounds the
    # expensive enrich fan-out if the message cap ever regresses.
    INGEST_MAX_LLM_CALLS: int = 1000
    # ── Sequence-sender tick fan-out bound ──────────────────────────────────
    # The 'tick-sequences' beat (every 5 min, per workspace) drafts one Claude
    # Haiku body per due enrollment whose step has ai_generate=True. With no
    # bound, bulk-enrolling N leads fires ~N uncapped Claude drafts in a single
    # tick (same shape as the ingest burn). Cap how many due enrollments one
    # tick processes; the rest are due-ordered (next_run_at) and picked up on
    # the next tick — deferred, never dropped.
    SEQUENCE_TICK_MAX_ENROLLMENTS: int = 100
    # ── Reprocess ("Re-run enrichment") token-safety bounds ─────────────────
    # reprocess_workspace_messages re-runs up to 4 Claude calls per message
    # (relevance + extract + sentiment + clarity) over EVERY non-graph_only
    # message in a workspace. Hard cap on messages per run so one click can't
    # fan LLM calls across an entire mailbox; the remainder defers to the next
    # run (dedupe-safe, never dropped).
    REPROCESS_MAX_MESSAGES: int = 500
    # Backstop per-run ceiling on Claude calls for reprocess (mirrors
    # INGEST_MAX_LLM_CALLS). Sized above the REPROCESS_MAX_MESSAGES worst case
    # (500 × 4 = 2000) so it never trips in normal operation, but bounds the
    # fan-out if the message cap ever regresses.
    REPROCESS_MAX_LLM_CALLS: int = 2500
    # ── Slack-sync token-safety bounds ──────────────────────────────────────
    # process_slack_sync walks up to 3×100 conversations and enqueues one
    # enrich_message (≈3 Claude calls) per NEW non-duplicate text message. With
    # no bound, the first sync of a busy workspace fans ~180k unbounded Claude
    # calls (the Gmail-ingest bug's twin). Hard cap on how many new Slack
    # messages a single sync inserts + enqueues, so one connect can never fan
    # LLM calls across an entire workspace history. Deferred messages are NOT
    # stored, so the next sync re-fetches them (dedupe misses) and they enter the
    # pipeline then — bounded per sync, never dropped.
    SLACK_MAX_MESSAGES: int = 200
    # Backstop per-run ceiling on Claude calls for one Slack sync (each enrich
    # dispatch ≈ 3 Claude calls). Sized above the SLACK_MAX_MESSAGES worst case
    # (200×3 = 600) so it never trips in normal operation, but bounds the enrich
    # fan-out if the message cap ever regresses (mirrors INGEST_MAX_LLM_CALLS).
    SLACK_MAX_LLM_CALLS: int = 1000
    # ── Followup-HITL fan-out bound ─────────────────────────────────────────
    # The 'daily-hitl-followup' beat (09:00) drafts one Claude email per stale
    # deal, inner-capped at .limit(5) deals/workspace but with no bound on the
    # OUTER loop over all Slack+Gmail workspaces => 5×(#tenants) unbounded Claude
    # drafts/day. Cap how many eligible workspaces one run drafts for; the rest
    # are deferred to a subsequent run and log()'d, never dropped.
    FOLLOWUP_MAX_WORKSPACES: int = 50
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


settings = Settings()
