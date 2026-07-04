"""
FastAPI wrapper for the Repo Health Agent.

Run standalone with:
    uvicorn agents.repo_health.api:app --reload --port 8001

This is designed to run as its own microservice — the orchestrator/MCP
layer talks to it over HTTP, not by importing it directly.
"""

from fastapi import FastAPI, HTTPException

from .models import RepoHealthReport, RepoHealthRequest
from .service import get_repo_health

app = FastAPI(title="Repo Health Agent", version="0.1.0")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/repo-health", response_model=RepoHealthReport)
async def repo_health(request: RepoHealthRequest):
    try:
        return await get_repo_health(request)
    except Exception as exc:  # narrow this to httpx.HTTPStatusError etc. as you harden it
        raise HTTPException(status_code=502, detail=f"Failed to fetch repo data: {exc}")