"""
Entry point for running the ops-copilot orchestrator.

Requires all three agent services running:
    uvicorn agents.repo_health.api:app --reload --port 8001
    uvicorn agents.deploy_status.api:app --reload --port 8002
    uvicorn agents.incident_log.api:app --reload --port 8003

Usage:
    python -m orchestrator.run octocat Hello-World
"""

import asyncio
import sys

from .graph import build_graph


async def main(owner: str, repo: str):
    graph = build_graph()

    initial_state = {
        "owner": owner,
        "repo": repo,
        "repo_health": None,
        "deploy_status": None,
        "incident_log": None,
        "final_summary": None,
    }

    result = await graph.ainvoke(initial_state)

    print("=" * 60)
    print(f"OPS REPORT: {owner}/{repo}")
    print("=" * 60)
    print(result["final_summary"])


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m orchestrator.run <owner> <repo>")
        sys.exit(1)

    asyncio.run(main(sys.argv[1], sys.argv[2]))