"""
Pydantic models for the Incident Log Agent.

Unlike the other two agents (which map structured JSON fields directly),
this agent parses unstructured plain-text CI log output looking for
error signatures — so the models describe *extracted* findings, not
a direct mirror of GitHub's API response shape.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class LogFinding(BaseModel):
    run_id: int
    job_name: str
    severity: Severity
    matched_line: str
    line_number: int


class FailedJobSummary(BaseModel):
    run_id: int
    job_id: int
    job_name: str
    workflow_name: str
    ran_at: Optional[datetime] = None
    findings: list[LogFinding] = Field(default_factory=list)


class IncidentLogRequest(BaseModel):
    owner: str
    repo: str
    max_failed_runs: int = 3  # how many recent failed runs to inspect (log downloads are expensive)


class IncidentLogReport(BaseModel):
    owner: str
    repo: str
    generated_at: datetime
    failed_jobs_inspected: int
    total_findings: int
    failed_jobs: list[FailedJobSummary] = Field(default_factory=list)
    summary: str