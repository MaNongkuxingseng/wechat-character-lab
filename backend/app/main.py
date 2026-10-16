from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import candidates, events, health, imports, profiles, roles, sessions, voice
from app.config import get_settings

app = FastAPI(title=get_settings().app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(health.router)
app.include_router(roles.router)
app.include_router(sessions.router)
app.include_router(events.router)
app.include_router(voice.router)
app.include_router(imports.router)
app.include_router(profiles.router)
app.include_router(candidates.router)
