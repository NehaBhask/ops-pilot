r"""
LangGraph supervisor for ops-copilot.

Graph shape:

        START
       /      \
  repo_health   deploy_status        <- run in PARALLEL (both cheap)
       \      /
        (conditional routing)         <- decides whether logs are worth checking
       /              \
  incident_log    skip_incidents
       \              /
        synthesize                    <- runs once the chosen path completes
            |
           END

repo_health and deploy_status write to different state keys, so LangGraph
can safely run them concurrently. Once either one finishes, the routing
function checks whatever's in state so far to decide whether the expensive
incident_log agent is worth calling, or whether it's safe to skip.
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


async def skip_incidents(state: OpsState) -> dict:
    """No-op node — records that we deliberately skipped the expensive check."""
    return {
        "incident_log": {
            "summary": "Skipped — repo_health and deploy_status both looked healthy."
        }
    }


def should_check_incidents(state: OpsState) -> str:
    """
    Routing function: decide whether incident_log is worth calling.

    Returns a label string, not a real node name — the mapping passed to
    add_conditional_edges() translates that label into the actual next node.

    NOTE: this fires as soon as EITHER repo_health or deploy_status finishes,
    since both point into this same conditional check. Whichever one hasn't
    finished yet will still be None in state at that moment — .get(...) and
    the `and` checks below handle that by defaulting to "not unhealthy",
    so this fails safe (skips) rather than crashing. A more robust version
    would add an explicit join node that waits for both before routing.
    """
    rh = state.get("repo_health")
    ds = state.get("deploy_status")

    repo_is_unhealthy = bool(rh and rh["status"] in ("warning", "critical"))
    deploy_is_failing = bool(ds and ds["any_environment_failing"])

    if repo_is_unhealthy or deploy_is_failing:
        return "check_incidents"
    return "skip_incidents"


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

async def check_gate(state: OpsState) -> dict:
    """
    No-op join node. Both repo_health and deploy_status point here, and
    LangGraph waits for ALL incoming edges before running a node — so this
    guarantees the routing decision below only happens once, after both
    fetches have genuinely completed, instead of firing twice in a race.
    """
    return {}


def build_graph():
    graph = StateGraph(OpsState)

    graph.add_node("repo_health", fetch_repo_health)
    graph.add_node("deploy_status", fetch_deploy_status)
    graph.add_node("check_gate", check_gate)
    graph.add_node("incident_log", fetch_incident_log)
    graph.add_node("skip_incidents", skip_incidents)
    graph.add_node("synthesize", synthesize)

    graph.add_edge(START, "repo_health")
    graph.add_edge(START, "deploy_status")

    # Both fetches feed into the SAME gate node — LangGraph waits for
    # both before running it, so routing only happens once.
    graph.add_edge("repo_health", "check_gate")
    graph.add_edge("deploy_status", "check_gate")

    graph.add_conditional_edges(
        "check_gate",
        should_check_incidents,
        {"check_incidents": "incident_log", "skip_incidents": "skip_incidents"},
    )

    graph.add_edge("incident_log", "synthesize")
    graph.add_edge("skip_incidents", "synthesize")

    graph.add_edge("synthesize", END)

    return graph.compile()