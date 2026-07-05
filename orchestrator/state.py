"""
Shared state for the ops-copilot LangGraph orchestrator.

Every node in the graph receives this state, does its work, and returns
a partial update to it. LangGraph merges each node's return value into
the running state automatically.
"""

from typing import Optional, TypedDict


class OpsState(TypedDict):
    owner: str
    repo: str

    # Each of these starts as None and gets filled in by its own node.
    # Because each node writes to a DIFFERENT key, they can run in
    # parallel with no risk of overwriting each other's results.
    repo_health: Optional[dict]
    deploy_status: Optional[dict]
    incident_log: Optional[dict]

    # Filled in last, after all three above are populated
    final_summary: Optional[str]