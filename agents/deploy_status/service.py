"""
Core logic for the Deploy Status Agent.

Uses GitHub's Deployments API:
  GET /repos/{owner}/{repo}/deployments        -> list of deployments
  GET /repos/{owner}/{repo}/deployments/{id}/statuses -> status history for one deployment

We only care about each deployment's *latest* status.
"""

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from .models import (
    DeployStatusReport,
    DeployStatusRequest,
    DeploymentState,
    EnvironmentDeployStatus,
)

GITHUB_API_BASE = "https://api.github.com"


def _auth_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _raise_with_context(resp: httpx.Response) -> None:
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise RuntimeError(
            "GitHub API rate limit exceeded. Set a GITHUB_TOKEN env var "
            "to raise the limit from 60/hr to 5000/hr."
        )
    resp.raise_for_status()


def _parse_state(raw_state: str) -> DeploymentState:
    try:
        return DeploymentState(raw_state)
    except ValueError:
        return DeploymentState.UNKNOWN


async def _fetch_latest_status_for_deployment(
    client: httpx.AsyncClient, owner: str, repo: str, deployment_id: int
) -> Optional[dict]:
    resp = await client.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/deployments/{deployment_id}/statuses",
        params={"per_page": 1},  # statuses are returned newest-first
    )
    _raise_with_context(resp)
    statuses = resp.json()
    return statuses[0] if statuses else None


async def get_deploy_status(request: DeployStatusRequest) -> DeployStatusReport:
    async with httpx.AsyncClient(headers=_auth_headers(), timeout=15.0) as client:
        params = {"per_page": 20}
        if request.environment:
            params["environment"] = request.environment

        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{request.owner}/{request.repo}/deployments",
            params=params,
        )
        _raise_with_context(resp)
        deployments = resp.json()
        seen_environments: set[str] = set()
        latest_deployments = []
        for dep in deployments:
            env_name = dep["environment"]
            if env_name not in seen_environments:
                seen_environments.add(env_name)
                latest_deployments.append(dep)

        environments: list[EnvironmentDeployStatus] = []
        for dep in latest_deployments:
            latest_status = await _fetch_latest_status_for_deployment(
                client, request.owner, request.repo, dep["id"]
            )
            state = _parse_state(latest_status["state"]) if latest_status else DeploymentState.UNKNOWN

            environments.append(
                EnvironmentDeployStatus(
                    environment=dep["environment"],
                    deployment_id=dep["id"],
                    ref=dep["ref"],
                    state=state,
                    created_at=dep["created_at"],
                    updated_at=dep["updated_at"],
                    description=latest_status.get("description") if latest_status else None,
                )
            )

    any_failing = any(
        env.state in (DeploymentState.FAILURE, DeploymentState.ERROR) for env in environments
    )

    if not environments:
        summary = "No deployments found for this repo."
    else:
        summary = f"{len(environments)} deployment(s) checked; " + (
            "failures detected" if any_failing else "all healthy"
        )

    return DeployStatusReport(
        owner=request.owner,
        repo=request.repo,
        generated_at=datetime.now(timezone.utc),
        environments=environments,
        any_environment_failing=any_failing,
        summary=summary,
    )