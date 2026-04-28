from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, workspaces, contacts, deals, agents, messages, tasks, gmail, slack


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


@app.get("/health")
async def health():
    return {"status": "ok"}
