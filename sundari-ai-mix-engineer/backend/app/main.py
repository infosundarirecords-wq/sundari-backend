"""
main.py
=======
FastAPI application entrypoint for Sundari AI Mix Engineer.
"""

from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.api.routes_analysis import router as analysis_router
from app.api.routes_report import router as report_router
from app.api.routes_decision import router as decision_router
from app.api.routes_mix import router as mix_router

logger = logging.getLogger("sundari")

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "AI Mixing & Mastering Engine — Phase 1: Audio Analysis Engine."
    ),
    version="0.1.0-phase1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s\n%s", request.url.path, exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Server error: {exc.__class__.__name__}: {exc}"},
    )


app.include_router(analysis_router, prefix=settings.api_v1_prefix)
app.include_router(report_router, prefix=settings.api_v1_prefix)
app.include_router(decision_router, prefix=settings.api_v1_prefix)
app.include_router(mix_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["Health"])
async def root():
    return {
        "app": settings.app_name,
        "status": "running",
        "phase": "Phase 1 - Audio Analysis Engine",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
