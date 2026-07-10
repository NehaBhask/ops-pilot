# ops-pilot

A multi-agent operations assistant that reports on the health of a GitHub repository — pull request/issue staleness, deployment status across environments, and CI failure details — via three independent microservices, orchestrated two different ways: a deterministic LangGraph supervisor, and an autonomous local LLM using MCP.

Built as a hands-on way to practice the same architecture pattern used in production multi-agent systems: independent FastAPI services, each exposed as a tool, coordinated by a central orchestrator.

## Why this exists

Most "AI agent" demos are a single LLM with a couple of tool calls bolted on. This project instead mirrors how a real multi-agent system is actually built: **independent, individually testable microservices**, each owning one concern, coordinated by a supervisor that doesn't know or care how each service gets its answer internally.

## Architecture

```
                    ┌─────────────────┐
                    │   GitHub API    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                     │
┌───────▼────────┐  ┌────────▼─────────┐  ┌───────▼────────┐
│  repo_health    │  │  deploy_status   │  │  incident_log  │
│  (FastAPI :8001)│  │  (FastAPI :8002) │  │ (FastAPI :8003)│
│                 │  │                  │  │                │
│ PR/issue        │  │ Deployment state │  │ Downloads &    │
│ staleness, CI   │  │ per environment  │  │ regex-scans    │
│ workflow status │  │                  │  │ real CI logs   │
└───────┬────────┘  └────────┬─────────┘  └───────┬────────┘
        │                    │                     │
        └──────────┬─────────┴──────────┬──────────┘
                    │                    │
         ┌──────────▼──────────┐  ┌──────▼───────────────┐
         │ LangGraph orchestrator│  │   MCP server         │
         │ (deterministic)       │  │  (autonomous)        │
         │                       │  │                      │
         │ Parallel fan-out →    │  │ 3 tools + server-    │
         │ join gate → condi-    │  │ level instructions,  │
         │ tional routing →      │  │ driven by a local     │
         │ synthesis             │  │ LLM (Ollama/Qwen2.5)  │
         └───────────────────────┘  └──────────────────────┘
```

Each agent follows the same internal structure:
```
agents/<name>/
├── models.py    # Pydantic request/response schema
├── service.py   # Real GitHub API calls + business logic
├── api.py       # Thin FastAPI wrapper (POST endpoint, error handling)
└── (tests/test_<name>.py — mocked HTTP, no live network calls)
```

## The two orchestration approaches — and why both

**LangGraph (deterministic):** the supervisor's logic is hardcoded in Python. It fans out to `repo_health` and `deploy_status` in parallel, waits for both at an explicit join node, then conditionally routes to the expensive `incident_log` agent *only if* something looks unhealthy — otherwise it skips straight to synthesis. Fast, predictable, easy to test in isolation (the routing function is pure and unit-tested with no mocking needed).

**MCP + local LLM (autonomous):** the same three agents are exposed as MCP tools with a server-level `instructions` string guiding sequencing (cheap checks first, expensive log-parsing only if something's already flagged as a problem). A local Qwen2.5:7b model, running via Ollama, decides for itself which tool(s) to call based on the user's actual question — verified to correctly discriminate between "is X healthy?" (→ `repo_health`) and "are there deployment failures?" (→ `deploy_status`) without being told which tool to use.

Building both surfaced a genuine, concrete tradeoff: the deterministic graph is faster and cheaper to run since routing is just Python logic, while the MCP/LLM approach is more flexible for open-ended questions but depends on the model reliably following the server's guidance — a real reliability gap smaller open models are known to have.

## Real problems hit and fixed along the way

This section exists because most of the actual engineering happened here, not in the "happy path" code.

**Concurrent write to shared state (LangGraph).** Initially wired the conditional routing function directly off both parallel branches (`repo_health` and `deploy_status` each independently deciding whether to trigger `incident_log`). When both branches were unhealthy in the same run, both fired the routing decision and both tried to write to the same state key in one step — LangGraph raised `InvalidUpdateError: Can receive only one value per step`. Fixed by adding an explicit no-op join node that both branches feed into; LangGraph waits for all incoming edges before running a node, so the routing decision now fires exactly once, only after both branches have genuinely completed.

**GitHub API permission scoping.** `/actions/jobs/{id}/logs` returned 403 with a scope-less token, even for a fully public repo — unlike the other endpoints used, which work fine unauthenticated. GitHub gates raw log downloads behind the `repo` scope specifically, since logs can contain sensitive build output. Fixed by regenerating the token with the correct scope, and hardened the code to treat 403 the same way as an expired-log 404 (skip that one job, don't crash the whole report) rather than assuming it can only mean a rate limit.

**Regex false positives in log scanning.** An early version flagged any line containing the word "error" — which matched benign text like a dependency name (`@octokit/request-error@7.1.0`) inside an `npm warn` line. Replaced loose keyword matching with GitHub Actions' own structured `##[error]`/`##[warning]` annotations, which are unambiguous by design. Tradeoff accepted deliberately: precision went up, but a genuine failure that isn't wrapped in GitHub's own annotation syntax could now be missed — a real precision/recall tradeoff, not a free win.

**MCP subprocess environment isolation.** `fastmcp.Client()` launches the MCP server as a fresh subprocess that does **not** inherit the parent process's environment by default — meaning a working `PYTHONPATH` in the calling terminal had no effect on the spawned server process, which then failed to import its own internal packages. Fixed by explicitly constructing a `StdioTransport` with `env=dict(os.environ)` to opt in to environment inheritance.


## Observability

All three agents are instrumented with `prometheus-fastapi-instrumentator`, exposing a `/metrics` endpoint automatically for every route (request counts, latency histograms, status codes) with no manual metric-writing. Prometheus scrapes all three every 15s (see `prometheus.yml`).

This turned an anecdotal observation ("incident_log feels slower") into an actual measurement: `http_request_duration_seconds_sum` showed incident_log at roughly 3x the latency of repo_health for a comparable single call — directly validating the reasoning behind treating it as the "expensive" agent in the conditional routing logic.

## Running it

**With Docker (recommended):**
```bash
export GITHUB_TOKEN=ghp_your_token   # needs the `repo` scope for log downloads
docker-compose up --build
```
This starts all three agents plus Prometheus. Check scrape status at `http://localhost:9090/targets`.

**Without Docker:**
```bash
pip install -r requirements.txt
export GITHUB_TOKEN=ghp_your_token
uvicorn agents.repo_health.api:app --reload --port 8001
uvicorn agents.deploy_status.api:app --reload --port 8002
uvicorn agents.incident_log.api:app --reload --port 8003
```

**Run the LangGraph orchestrator:**
```bash
python -m orchestrator.run <github-owner> <github-repo>
```

**Run the MCP server standalone (for Claude Desktop or the MCP Inspector):**
```bash
fastmcp dev inspector mcp_server/server.py
```

**Talk to it via a local LLM:**
```bash
ollama pull qwen2.5:7b
python -m mcp_server.llm_client "is octocat/Hello-World healthy?"
```

**Run the tests** (all mocked — no live network calls, no token required):
```bash
python -m pytest tests/ -v
```

## Stack

FastAPI · Pydantic · httpx · LangGraph · FastMCP · Ollama · Prometheus · Docker Compose · pytest/respx

## Possible next steps

- Rebuild the join-then-route pattern as an explicit two-stage join (repo_health + deploy_status → gate → route) to eliminate the same-step race condition class entirely, rather than relying on the join node alone
- Add Grafana back once on a clean Docker Desktop install, for an actual visual dashboard on top of the existing Prometheus metrics
- Extend the `instructions`-driven MCP approach with a genuine comparison benchmark: same set of questions, run against both the LangGraph orchestrator and the local-LLM/MCP path, measuring latency and correctness of each