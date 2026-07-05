r"""
LangGraph supervisor for ops-copilot.

Graph shape:

        START
       /  |  \
  repo_health  deploy_status  incident_log      <- run in PARALLEL
       \  |  /
       synthesize                                <- runs once all 3 are done
          |
         END

Each of the three fetch nodes only writes to its own state key, so
LangGraph can safely execute them concurrently — see orchestrator/state.py
for why that's true.
"""

from langgraph.graph import StateGraph, START, END

from .clients import call_deploy_status, call_incident_log, call_repo_health
from .state import OpsState


async def fetch_repo_health(state: OpsState) -> dict:
    result = await call_repo_health(state["owner"], state["repo"])
    return {"repo_health": result}


async def fetch_deploy_status(state: OpsState) -> dict:
    result = await call_deploy_status(state["owner"], state["repo"])
    return {"deploy_status": result}


async def fetch_incident_log(state: OpsState) -> dict:
    result = await call_incident_log(state["owner"], state["repo"])
    return {"incident_log": result}


async def synthesize(state: OpsState) -> dict:
    """Combine all three agent reports into one human-readable summary."""
    lines = []

    rh = state.get("repo_health")
    if rh:
        lines.append(f"Repo health: {rh['status'].upper()} — {rh['summary']}")

    ds = state.get("deploy_status")
    if ds:
        deploy_state = "FAILING" if ds["any_environment_failing"] else "OK"
        lines.append(f"Deploy status: {deploy_state} — {ds['summary']}")

    il = state.get("incident_log")
    if il:
        lines.append(f"Incident log: {il['summary']}")

    return {"final_summary": "\n".join(lines)}


def build_graph():
    graph = StateGraph(OpsState)

    graph.add_node("repo_health", fetch_repo_health)
    graph.add_node("deploy_status", fetch_deploy_status)
    graph.add_node("incident_log", fetch_incident_log)
    graph.add_node("synthesize", synthesize)

    # All three fetch nodes start directly from START -> they run in parallel
    graph.add_edge(START, "repo_health")
    graph.add_edge(START, "deploy_status")
    graph.add_edge(START, "incident_log")

    # synthesize waits until ALL THREE have completed before running
    graph.add_edge("repo_health", "synthesize")
    graph.add_edge("deploy_status", "synthesize")
    graph.add_edge("incident_log", "synthesize")

    graph.add_edge("synthesize", END)

    return graph.compile()