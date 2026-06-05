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

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
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
