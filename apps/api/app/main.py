import logging
import logging.config
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.limiter import limiter
from app.routers import auth, workspaces, contacts, deals, agents, messages, tasks, gmail, slack, search, calls, ai, events, slack_interactions, mcp_server, projects

# ── Structured logging (JSON-like key=value to stdout) ───────────────────────
_LOG_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["stdout"],
    },
    # Silence noisy third-party loggers in production
    "loggers": {
        "uvicorn.access": {"level": "WARNING"},
        "sqlalchemy.engine": {"level": "WARNING"},
    },
}
logging.config.dictConfig(_LOG_CONFIG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("event=startup version=0.1.0")
    yield
    logger.info("event=shutdown")


app = FastAPI(
    title="CRM-Agentic API",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — allow Next.js dev + the configured frontend origin(s).
# Explicit allowlist = FRONTEND_URL + comma-separated CORS_ORIGINS (apex domain,
# old deploy URL, etc.) + localhost. An optional CORS_ORIGIN_REGEX covers whole
# domain families (e.g. www + apex) so a domain cutover doesn't need a code change.
_extra_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
origins = [
    settings.FRONTEND_URL,
    *_extra_origins,
    "http://localhost:3000",
    "http://localhost:3001",
]
# De-duplicate while preserving order, drop empties.
origins = list(dict.fromkeys(o for o in origins if o))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request logging middleware ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if request.url.path != "/health":
        logger.info(
            "method=%s path=%s status=%s duration_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    return response

# Routers
# search.router must precede contacts.router: GET /contacts/search would otherwise
# be shadowed by contacts.router's GET /contacts/{contact_id} parameterized route.
app.include_router(auth.router, tags=["auth"])
app.include_router(workspaces.router, tags=["workspaces"])
app.include_router(search.router, tags=["search"])
app.include_router(contacts.router, tags=["contacts"])
app.include_router(deals.router, tags=["deals"])
app.include_router(agents.router, tags=["agents"])
app.include_router(messages.router, tags=["messages"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(gmail.router, tags=["gmail"])
app.include_router(slack.router, tags=["slack"])
app.include_router(calls.router, tags=["calls"])
app.include_router(ai.router, tags=["ai"])
app.include_router(events.router, tags=["events"])
app.include_router(slack_interactions.router, tags=["slack"])
app.include_router(mcp_server.router, tags=["mcp"])
app.include_router(projects.router, tags=["projects"])


@app.get("/health")
async def health() -> dict:
    """Liveness + readiness probe: checks DB connectivity."""
    db_ok = False
    db_error: str | None = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)
        logger.error("event=health_check_failed component=database error=%s", db_error)

    status_str = "ok" if db_ok else "degraded"
    payload: dict = {"status": status_str, "database": "ok" if db_ok else "error"}
    if db_error:
        payload["database_error"] = db_error
    # Railway healthcheck: return 200 even when degraded so the container is not
    # killed on a transient DB blip.  A dedicated alerting layer should monitor
    # `status != "ok"` in the response body.
    return payload
