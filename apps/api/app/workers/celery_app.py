import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from celery import Celery
from celery.schedules import crontab

# Load REDIS_URL from env (Celery runs outside FastAPI lifespan)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "crm_agentic",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.ingest", "app.workers.score_contact", "app.workers.pipeline", "app.workers.slack_ingest", "app.workers.embed_contacts", "app.workers.deal_health_worker", "app.workers.transcribe", "app.workers.enrich_contact", "app.workers.followup_sequences", "app.workers.pm_agent"],
)

# ── F5: queue isolation (opt-in via LONG_QUEUE_ENABLED, deploy-safe) ──────────
# The worker pool is hard-pinned to --concurrency=2 (railway-worker.toml). With a
# single undifferentiated queue, one long job (full-workspace reprocess or a
# long-audio Whisper transcription) pins a slot for its entire duration and two
# such jobs starve every other tenant's short async work (enrich/scoring/health).
#
# When ENABLED we split traffic into two queues:
#   * "long"    — heavy, long-running, high-fan-out jobs: reprocess + transcribe.
#   * "default" — everything else (short enrich/scoring/embeds/health/PM/dispatchers).
#
# GATING (LONG_QUEUE_ENABLED, default False): routing is OFF by default so this is
# safe to DEPLOY ALONE. With it off, reprocess/transcribe take the "default" queue
# and the existing worker (started without -Q) keeps consuming them — no regression.
# A default worker started WITHOUT -Q consumes only task_default_queue, so the
# `long` queue would otherwise queue-but-never-run.
#
# TO ENABLE ISOLATION (coordinated, same deploy): set LONG_QUEUE_ENABLED=true AND
# start a consumer for the long queue, e.g. run the worker with
#     -Q default,long           (single worker consumes both), or split:
#     celery -A app.workers.celery_app.celery_app worker -Q long --concurrency=1
#     celery -A app.workers.celery_app.celery_app worker -Q default --concurrency=2
_LONG_QUEUE = "long"
_DEFAULT_QUEUE = "default"
# Read the gate from the env directly (Celery boots outside the FastAPI lifespan);
# the same env var backs settings.LONG_QUEUE_ENABLED that the API reads.
_LONG_QUEUE_ENABLED = os.getenv("LONG_QUEUE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
_task_routes = {
    "app.workers.ingest.reprocess_workspace_messages": {"queue": _LONG_QUEUE},
    "app.workers.transcribe.transcribe_call": {"queue": _LONG_QUEUE},
} if _LONG_QUEUE_ENABLED else {}

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_default_queue=_DEFAULT_QUEUE,
    # prefetch=1 so a worker holding a long job doesn't also reserve queued short
    # jobs it can't start, which would amplify the starvation it's meant to avoid.
    worker_prefetch_multiplier=1,
    task_routes=_task_routes,
    beat_schedule={
        "nightly-pipeline-optimize": {
            # Dispatcher fans out per-workspace; the bare optimize_pipeline task
            # requires a workspace_id that beat cannot supply (it would crash).
            "task": "app.workers.pipeline.optimize_pipeline_all",
            "schedule": crontab(hour=2, minute=0),
            "args": [],
        },
        "nightly-deal-health": {
            # Dispatcher fans out per-workspace; the bare compute_deal_health task
            # requires a workspace_id that beat cannot supply (it would crash).
            "task": "app.workers.deal_health_worker.compute_deal_health_all",
            "schedule": crontab(hour=2, minute=15),
            "args": [],
        },
        "daily-hitl-followup": {
            "task": "app.workers.followup_sequences.check_stale_deals_hitl",
            "schedule": crontab(hour=9, minute=0),
            "args": [],
        },
        "pm-health-check": {
            "task": "app.workers.pm_agent.run_health_check",
            "schedule": crontab(minute="*/30"),
            "args": [],
        },
    },
)
