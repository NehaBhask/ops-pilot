"""
MCP server for ops-copilot.

Wraps the three agent microservices (repo_health, deploy_status,
incident_log) as MCP tools, callable by any MCP-compatible client
(Claude Desktop, Claude Code, or your own orchestrator).

The `instructions` string below is server-level guidance returned at
connection time — distinct from a tool's docstring, which only describes
ONE tool. `instructions` describes how to use the server AS A WHOLE,
including cross-tool sequencing advice the model wouldn't otherwise know.
"""

from fastmcp import FastMCP

from orchestrator.clients import call_deploy_status, call_incident_log, call_repo_health

mcp = FastMCP(
    name="ops-copilot",
    instructions="""
This server reports on the health of a GitHub repository across three
dimensions: open PR/issue staleness, deployment status, and CI failure
details.

Recommended usage:
- Call `repo_health` and `deploy_status` first — they're fast (single-digit
  API calls) and give a quick overall picture.
- Only call `incident_log` if repo_health or deploy_status indicate a
  problem (status is "critical"/"warning", or any_environment_failing is
  true). incident_log downloads and scans real CI log text, so it's
  noticeably slower and more expensive than the other two — don't call it
  speculatively "just in case."
- All three tools require `owner` and `repo` (a GitHub org/user and repo
  name, e.g. owner="octocat", repo="Hello-World").
""",
)


@mcp.tool()
async def repo_health(owner: str, repo: str) -> dict:
    """
    Check a GitHub repo's PR/issue staleness and recent CI workflow status.

    Args:
        owner: GitHub organization or username (e.g. "octocat")
        repo: Repository name (e.g. "Hello-World")

    Returns a report with status ("healthy"/"warning"/"critical"), counts
    of open/stale PRs and issues, and recent workflow run outcomes.
    """
    return await call_repo_health(owner, repo)


@mcp.tool()
async def deploy_status(owner: str, repo: str) -> dict:
    """
    Check the latest deployment state across all environments for a repo.

    Args:
        owner: GitHub organization or username
        repo: Repository name

    Returns each environment's latest deployment state (success/failure/
    error/in_progress/etc.) and whether any environment is failing.
    """
    return await call_deploy_status(owner, repo)


@mcp.tool()
async def incident_log(owner: str, repo: str) -> dict:
    """
    Inspect the most recent failed CI runs and extract error/warning lines
    from their logs.

    Args:
        owner: GitHub organization or username
        repo: Repository name

    This is slower than repo_health/deploy_status — it downloads real log
    text and regex-scans it for GitHub Actions' structured ##[error]/
    ##[warning] annotations. Use it to get specifics AFTER repo_health or
    deploy_status has already indicated something is wrong.
    """
    return await call_incident_log(owner, repo)


if __name__ == "__main__":
    mcp.run()