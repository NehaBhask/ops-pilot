from datetime import datetime, timezone

import respx
import pytest
from httpx import Response

from agents.deploy_status.models import DeployStatusRequest,DeploymentState
from agents.deploy_status.service import get_deploy_status

OWNER, REPO = "github", "docs"
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"


@pytest.mark.asyncio
@respx.mock
async def test_healthy_deploy_reports_no_failures():
    tst={
      "environment": "preview-env-36425",
      "id": 2233969529,
      "ref": "codespace-zany-waddle-v6qwjrpvv5x9cxqrx",
      "state": "failure",
      "created_at": "2025-02-24T08:34:35Z",
      "updated_at": "2025-02-24T08:34:51Z",
      "description": ""
    }
    status = {
        "state": "success",
        "description": "",
    }
    respx.get(f"{BASE}/deployments").mock(return_value=Response(200, json=[tst]))
    respx.get(f"{BASE}/deployments/2233969529/statuses").mock(
        return_value=Response(200, json=[status])
    )
    res=await get_deploy_status(DeployStatusRequest(owner=OWNER, repo=REPO))
    assert res.any_environment_failing is False
    assert res.environments[0].state == DeploymentState.SUCCESS
    