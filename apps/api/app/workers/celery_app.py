import os

from celery import Celery
from celery.schedules import crontab

# Load REDIS_URL from env (Celery runs outside FastAPI lifespan)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "crm_agentic",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.ingest", "app.workers.score_contact", "app.workers.pipeline", "app.workers.slack_ingest", "app.workers.embed_contacts"],
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
            # TODO: workspace_id needed — iterate all workspaces when multi-tenant Beat support is added
            "task": "app.workers.pipeline.optimize_pipeline",
            "schedule": crontab(hour=2, minute=0),  # 2am UTC daily
            "args": [],  # workspace_id left empty — needs workspace-aware Beat runner
        },
    },
)
