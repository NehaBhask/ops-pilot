"""
FastAPI wrapper for the Deploy Status Agent.

Run standalone with:
    uvicorn agents.deploy_status.api:app --reload --port 8002
"""
from prometheus_fastapi_instrumentator import Instrumentator

from fastapi import FastAPI, HTTPException

from .models import DeployStatusReport, DeployStatusRequest
from .service import get_deploy_status

app = FastAPI(title="Deploy Status Agent", version="0.1.0")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/deploy-status", response_model=DeployStatusReport)
async def deploy_status(request: DeployStatusRequest):
    try:
        return await get_deploy_status(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch deployment data: {exc}")

Instrumentator().instrument(app).expose(app)