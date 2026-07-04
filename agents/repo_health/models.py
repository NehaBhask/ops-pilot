from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


class OpenPullRequest(BaseModel):
    number: int
    title: str
    author: str
    created_at: datetime
    days_open: int
    is_draft: bool = False


class StaleIssue(BaseModel):
    number: int
    title: str
    created_at: datetime
    days_open: int
    labels: list[str] = Field(default_factory=list)


class WorkflowRunStatus(BaseModel):
    name: str
    status: str  # "completed", "in_progress", "queued"
    conclusion: Optional[str] = None  # "success", "failure", "cancelled", None
    ran_at: Optional[datetime] = None


class RepoHealthRequest(BaseModel):
    owner: str
    repo: str
    stale_issue_threshold_days: int = 30
    stale_pr_threshold_days: int = 14


class RepoHealthReport(BaseModel):
    owner: str
    repo: str
    generated_at: datetime
    status: HealthStatus
    open_pr_count: int
    stale_pr_count: int
    open_issue_count: int
    stale_issue_count: int
    recent_workflow_runs: list[WorkflowRunStatus] = Field(default_factory=list)
    stale_prs: list[OpenPullRequest] = Field(default_factory=list)
    stale_issues: list[StaleIssue] = Field(default_factory=list)
    summary: str