import respx
import pytest
from httpx import Response

from agents.incident_log.models import IncidentLogRequest, Severity
from agents.incident_log.service import get_incident_log_report

OWNER, REPO = "github", "docs"
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"


@pytest.mark.asyncio
@respx.mock
async def test_finds_error_marker_in_log():
    respx.get(f"{BASE}/actions/runs", params={"status": "failure", "per_page": 3}).mock(
        return_value=Response(200, json={"workflow_runs": [{"id": 123, "name": "Test Run", "run_started_at": "2024-01-01T00:00:00Z"}]})
    )

    respx.get(f"{BASE}/actions/runs/123/jobs").mock(
        return_value=Response(200, json={"jobs": [{"id": 456, "name": "Test Job", "conclusion": "failure"}]})
    )

    respx.get(f"{BASE}/actions/jobs/456/logs").mock(
        return_value=Response(200, text="some log line\n##[error]something broke\nmore lines")
    )

    report = await get_incident_log_report(IncidentLogRequest(owner=OWNER, repo=REPO))

    assert report.total_findings == 1
    assert report.failed_jobs[0].findings[0].severity == Severity.ERROR
    assert "##[error]something broke" in report.failed_jobs[0].findings[0].matched_line