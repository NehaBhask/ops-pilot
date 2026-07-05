"""
FastAPI wrapper for the Incident Log Agent.

Run standalone with:
    uvicorn agents.incident_log.api:app --reload --port 8003

Note: this endpoint is slower than the other two agents — it downloads
and regex-scans full CI log text across multiple jobs, not just small
JSON metadata payloads.
"""

from fastapi import FastAPI, HTTPException

from .models import IncidentLogReport, IncidentLogRequest
from .service import get_incident_log_report

app = FastAPI(title="Incident Log Agent", version="0.1.0")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/incident-log", response_model=IncidentLogReport)
async def incident_log(request: IncidentLogRequest):
    try:
        return await get_incident_log_report(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch/parse incident logs: {exc}")