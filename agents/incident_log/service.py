"""
Core logic for the Incident Log Agent.

Flow:
  1. GET /repos/{owner}/{repo}/actions/runs?status=failure  -> recent failed runs
  2. GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs    -> jobs within that run
  3. GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs    -> raw plain-text log
     (this endpoint returns a 302 redirect to a temporary blob URL —
      httpx needs follow_redirects=True or it'll just get an empty 302 body)
  4. Regex-scan the log text for error signatures
"""

import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from .models import (
    FailedJobSummary,
    IncidentLogReport,
    IncidentLogRequest,
    LogFinding,
    Severity,
)

GITHUB_API_BASE = "https://api.github.com"

# Common CI failure signatures. Each tuple is (regex, severity).
# Deliberately simple patterns — real log-parsing tools use far more,
# but this demonstrates the mechanism end to end.
ERROR_PATTERNS: list[tuple[re.Pattern, Severity]] = [
    (re.compile(r"##\[error\]"), Severity.ERROR),
    (re.compile(r"##\[warning\]"), Severity.WARNING),
    (re.compile(r"Traceback \(most recent call last\)"), Severity.ERROR),
    (re.compile(r"npm ERR!"), Severity.ERROR),
]


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


async def _fetch_recent_failed_runs(
    client: httpx.AsyncClient, owner: str, repo: str, limit: int
) -> list[dict]:
    resp = await client.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions/runs",
        params={"status": "failure", "per_page": limit},
    )
    _raise_with_context(resp)
    return resp.json().get("workflow_runs", [])


async def _fetch_failed_jobs_for_run(
    client: httpx.AsyncClient, owner: str, repo: str, run_id: int
) -> list[dict]:
    resp = await client.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
    )
    _raise_with_context(resp)
    jobs = resp.json().get("jobs", [])
    return [job for job in jobs if job.get("conclusion") == "failure"]


async def _fetch_job_log_text(
    client: httpx.AsyncClient, owner: str, repo: str, job_id: int
) -> Optional[str]:
    resp = await client.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
        follow_redirects=True,
    )
    if resp.status_code == 404:
        # Logs can expire/be deleted after a retention window
        return None
    if resp.status_code == 403:
        # Insufficient token scope, or logs restricted for this job — skip, don't crash the report
        return None
    _raise_with_context(resp)
    return resp.text

def _scan_log_for_findings(run_id: int, job_name: str, log_text: str) -> list[LogFinding]:
    findings: list[LogFinding] = []
    for line_number, line in enumerate(log_text.splitlines(), start=1):
        for pattern, severity in ERROR_PATTERNS:
            if pattern.search(line):
                findings.append(
                    LogFinding(
                        run_id=run_id,
                        job_name=job_name,
                        severity=severity,
                        matched_line=line.strip()[:300],  # cap length, logs can have huge lines
                        line_number=line_number,
                    )
                )
                break  # one match per line is enough; don't double-count
    return findings


async def get_incident_log_report(request: IncidentLogRequest) -> IncidentLogReport:
    async with httpx.AsyncClient(headers=_auth_headers(), timeout=30.0) as client:
        failed_runs = await _fetch_recent_failed_runs(
            client, request.owner, request.repo, request.max_failed_runs
        )

        failed_job_summaries: list[FailedJobSummary] = []
        for run in failed_runs:
            failed_jobs = await _fetch_failed_jobs_for_run(
                client, request.owner, request.repo, run["id"]
            )
            for job in failed_jobs:
                log_text = await _fetch_job_log_text(client, request.owner, request.repo, job["id"])
                findings = _scan_log_for_findings(run["id"], job["name"], log_text) if log_text else []

                failed_job_summaries.append(
                    FailedJobSummary(
                        run_id=run["id"],
                        job_id=job["id"],
                        job_name=job["name"],
                        workflow_name=run.get("name", "unknown"),
                        ran_at=run.get("run_started_at"),
                        findings=findings,
                    )
                )

    total_findings = sum(len(j.findings) for j in failed_job_summaries)
    summary = (
        f"{len(failed_job_summaries)} failed job(s) inspected, "
        f"{total_findings} error/warning line(s) found"
        if failed_job_summaries
        else "No recent failed runs found."
    )

    return IncidentLogReport(
        owner=request.owner,
        repo=request.repo,
        generated_at=datetime.now(timezone.utc),
        failed_jobs_inspected=len(failed_job_summaries),
        total_findings=total_findings,
        failed_jobs=failed_job_summaries,
        summary=summary,
    )