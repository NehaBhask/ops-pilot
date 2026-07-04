"""
Core logic for the Repo Health Agent.

Talks to the real GitHub REST API (public repos work with no auth token,
though you'll want one set as GITHUB_TOKEN env var to avoid the 60
req/hour unauthenticated rate limit).
"""

import os
from datetime import datetime, timezone

import httpx

from .models import (
    HealthStatus,
    OpenPullRequest,
    RepoHealthReport,
    RepoHealthRequest,
    StaleIssue,
    WorkflowRunStatus,
)

GITHUB_API_BASE = "https://api.github.com"


def _auth_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _days_since(iso_timestamp: str) -> int:
    created = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - created).days


def _raise_with_context(resp: httpx.Response) -> None:
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise RuntimeError(
            "GitHub API rate limit exceeded. Set a GITHUB_TOKEN env var "
            "(a classic PAT with no scopes is enough for public repos) "
            "to raise the limit from 60/hr to 5000/hr."
        )
    resp.raise_for_status()


async def _fetch_open_prs(client: httpx.AsyncClient, owner: str, repo: str) -> list[OpenPullRequest]:
    resp = await client.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
        params={"state": "open", "per_page": 50},
    )
    _raise_with_context(resp)
    prs = []
    for item in resp.json():
        prs.append(
            OpenPullRequest(
                number=item["number"],
                title=item["title"],
                author=item["user"]["login"],
                created_at=item["created_at"],
                days_open=_days_since(item["created_at"]),
                is_draft=item.get("draft", False),
            )
        )
    return prs


async def _fetch_open_issues(client: httpx.AsyncClient, owner: str, repo: str) -> list[StaleIssue]:
    resp = await client.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
        params={"state": "open", "per_page": 50},
    )
    _raise_with_context(resp)
    issues = []
    for item in resp.json():
        # GitHub's /issues endpoint also returns PRs; skip those, we counted them above
        if "pull_request" in item:
            continue
        issues.append(
            StaleIssue(
                number=item["number"],
                title=item["title"],
                created_at=item["created_at"],
                days_open=_days_since(item["created_at"]),
                labels=[label["name"] for label in item.get("labels", [])],
            )
        )
    return issues


async def _fetch_recent_workflow_runs(
    client: httpx.AsyncClient, owner: str, repo: str
) -> list[WorkflowRunStatus]:
    try:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions/runs",
            params={"per_page": 5},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        # Actions might not be enabled on this repo — not a fatal error
        return []

    runs = []
    for item in resp.json().get("workflow_runs", []):
        runs.append(
            WorkflowRunStatus(
                name=item["name"],
                status=item["status"],
                conclusion=item.get("conclusion"),
                ran_at=item.get("run_started_at"),
            )
        )
    return runs


def _determine_status(stale_pr_count: int, stale_issue_count: int, failed_runs: int) -> HealthStatus:
    if failed_runs > 0 or stale_pr_count > 5:
        return HealthStatus.CRITICAL
    if stale_pr_count > 0 or stale_issue_count > 10:
        return HealthStatus.WARNING
    return HealthStatus.HEALTHY


def _build_summary(report_data: dict) -> str:
    parts = []
    parts.append(f"{report_data['open_pr_count']} open PRs ({report_data['stale_pr_count']} stale)")
    parts.append(f"{report_data['open_issue_count']} open issues ({report_data['stale_issue_count']} stale)")
    failed = [r for r in report_data["recent_workflow_runs"] if r.conclusion == "failure"]
    if failed:
        parts.append(f"{len(failed)} recent workflow failure(s)")
    return "; ".join(parts)


async def get_repo_health(request: RepoHealthRequest) -> RepoHealthReport:
    """Fetch live data from GitHub and assemble a RepoHealthReport."""
    async with httpx.AsyncClient(headers=_auth_headers(), timeout=15.0) as client:
        open_prs = await _fetch_open_prs(client, request.owner, request.repo)
        open_issues = await _fetch_open_issues(client, request.owner, request.repo)
        workflow_runs = await _fetch_recent_workflow_runs(client, request.owner, request.repo)

    stale_prs = [pr for pr in open_prs if pr.days_open >= request.stale_pr_threshold_days]
    stale_issues = [i for i in open_issues if i.days_open >= request.stale_issue_threshold_days]
    failed_runs = sum(1 for r in workflow_runs if r.conclusion == "failure")

    status = _determine_status(len(stale_prs), len(stale_issues), failed_runs)

    report_data = {
        "open_pr_count": len(open_prs),
        "stale_pr_count": len(stale_prs),
        "open_issue_count": len(open_issues),
        "stale_issue_count": len(stale_issues),
        "recent_workflow_runs": workflow_runs,
    }

    return RepoHealthReport(
        owner=request.owner,
        repo=request.repo,
        generated_at=datetime.now(timezone.utc),
        status=status,
        summary=_build_summary(report_data),
        stale_prs=stale_prs,
        stale_issues=stale_issues,
        **report_data,
    )