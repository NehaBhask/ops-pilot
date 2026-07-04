from datetime import datetime, timedelta, timezone

import respx
import pytest
from httpx import Response

from agents.repo_health.models import HealthStatus, RepoHealthRequest
from agents.repo_health.service import get_repo_health

OWNER, REPO = "octocat", "hello-world"
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"


def _iso_days_ago(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.asyncio
@respx.mock
async def test_healthy_repo_reports_healthy_status():
    respx.get(f"{BASE}/pulls").mock(return_value=Response(200, json=[]))
    respx.get(f"{BASE}/issues").mock(return_value=Response(200, json=[]))
    respx.get(f"{BASE}/actions/runs").mock(return_value=Response(200, json={"workflow_runs": []}))

    report = await get_repo_health(RepoHealthRequest(owner=OWNER, repo=REPO))

    assert report.status == HealthStatus.HEALTHY
    assert report.open_pr_count == 0
    assert report.stale_pr_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_stale_prs_trigger_warning_status():
    stale_pr = {
        "number": 1,
        "title": "Old PR",
        "user": {"login": "someone"},
        "created_at": _iso_days_ago(20),
        "draft": False,
    }
    respx.get(f"{BASE}/pulls").mock(return_value=Response(200, json=[stale_pr]))
    respx.get(f"{BASE}/issues").mock(return_value=Response(200, json=[]))
    respx.get(f"{BASE}/actions/runs").mock(return_value=Response(200, json={"workflow_runs": []}))

    report = await get_repo_health(
        RepoHealthRequest(owner=OWNER, repo=REPO, stale_pr_threshold_days=14)
    )

    assert report.stale_pr_count == 1
    assert report.status == HealthStatus.WARNING
    assert report.stale_prs[0].number == 1


@pytest.mark.asyncio
@respx.mock
async def test_failed_workflow_run_triggers_critical_status():
    respx.get(f"{BASE}/pulls").mock(return_value=Response(200, json=[]))
    respx.get(f"{BASE}/issues").mock(return_value=Response(200, json=[]))
    failed_run = {
        "name": "CI",
        "status": "completed",
        "conclusion": "failure",
        "run_started_at": _iso_days_ago(0),
    }
    respx.get(f"{BASE}/actions/runs").mock(
        return_value=Response(200, json={"workflow_runs": [failed_run]})
    )

    report = await get_repo_health(RepoHealthRequest(owner=OWNER, repo=REPO))

    assert report.status == HealthStatus.CRITICAL
    assert "failure" in report.summary


@pytest.mark.asyncio
@respx.mock
async def test_issues_endpoint_excludes_pull_requests():
    # GitHub's /issues endpoint returns PRs too; a "pull_request" key marks them.
    pr_disguised_as_issue = {
        "number": 5,
        "title": "Actually a PR",
        "created_at": _iso_days_ago(1),
        "labels": [],
        "pull_request": {"url": "..."},
    }
    real_issue = {
        "number": 6,
        "title": "Real issue",
        "created_at": _iso_days_ago(1),
        "labels": [{"name": "bug"}],
    }
    respx.get(f"{BASE}/pulls").mock(return_value=Response(200, json=[]))
    respx.get(f"{BASE}/issues").mock(
        return_value=Response(200, json=[pr_disguised_as_issue, real_issue])
    )
    respx.get(f"{BASE}/actions/runs").mock(return_value=Response(200, json={"workflow_runs": []}))

    report = await get_repo_health(RepoHealthRequest(owner=OWNER, repo=REPO))

    assert report.open_issue_count == 1