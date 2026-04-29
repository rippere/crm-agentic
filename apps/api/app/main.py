from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.limiter import limiter
from app.routers import auth, workspaces, contacts, deals, agents, messages, tasks, gmail, slack, search, calls, ai, events, slack_interactions, mcp_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="CRM-Agentic API",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — allow Next.js dev + configured frontend origin
origins = [
    settings.FRONTEND_URL,
    "http://localhost:3000",
    "http://localhost:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, tags=["auth"])
app.include_router(workspaces.router, tags=["workspaces"])
app.include_router(contacts.router, tags=["contacts"])
app.include_router(deals.router, tags=["deals"])
app.include_router(agents.router, tags=["agents"])
app.include_router(messages.router, tags=["messages"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(gmail.router, tags=["gmail"])
app.include_router(slack.router, tags=["slack"])
app.include_router(search.router, tags=["search"])
app.include_router(calls.router, tags=["calls"])
app.include_router(ai.router, tags=["ai"])
app.include_router(events.router, tags=["events"])
app.include_router(slack_interactions.router, tags=["slack"])
app.include_router(mcp_server.router, tags=["mcp"])


@app.get("/health")
async def health():
    return {"status": "ok"}
