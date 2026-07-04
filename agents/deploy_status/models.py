"""
Pydantic models for the Deploy Status Agent.

Tracks GitHub "Deployments" (distinct from CI workflow runs) — these
represent actual releases to named environments like "production" or
"staging", each with its own status history.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeploymentState(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    QUEUED = "queued"
    UNKNOWN = "unknown"


class EnvironmentDeployStatus(BaseModel):
    environment: str
    deployment_id: int
    ref: str  # branch or tag that was deployed
    state: DeploymentState
    created_at: datetime
    updated_at: datetime
    description: Optional[str] = None


class DeployStatusRequest(BaseModel):
    owner: str
    repo: str
    environment: Optional[str] = None  # filter to one environment, or None for all


class DeployStatusReport(BaseModel):
    owner: str
    repo: str
    generated_at: datetime
    environments: list[EnvironmentDeployStatus] = Field(default_factory=list)
    any_environment_failing: bool
    summary: str