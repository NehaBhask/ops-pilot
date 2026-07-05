"""
HTTP clients for calling the three ops-copilot agent microservices.

Each agent runs as its own FastAPI service (see agents/*/api.py).
This module is the ONLY place that knows their URLs/ports — if you
containerize later, this is the one file that changes.
"""

import httpx

REPO_HEALTH_URL = "http://localhost:8001/repo-health"
DEPLOY_STATUS_URL = "http://localhost:8002/deploy-status"
INCIDENT_LOG_URL = "http://localhost:8003/incident-log"


async def call_repo_health(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(REPO_HEALTH_URL, json={"owner": owner, "repo": repo})
        resp.raise_for_status()
        return resp.json()


async def call_deploy_status(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(DEPLOY_STATUS_URL, json={"owner": owner, "repo": repo})
        resp.raise_for_status()
        return resp.json()


async def call_incident_log(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:  # longer timeout — this one downloads logs
        resp = await client.post(
            INCIDENT_LOG_URL, json={"owner": owner, "repo": repo, "max_failed_runs": 2}
        )
        resp.raise_for_status()
        return resp.json()