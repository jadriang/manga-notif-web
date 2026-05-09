"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, cron, manga, subscriptions, telegram_routes, user
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Manga Notifier", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(manga.router, prefix="/api")
app.include_router(subscriptions.router, prefix="/api")
app.include_router(cron.router, prefix="/api")
app.include_router(telegram_routes.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(auth.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
