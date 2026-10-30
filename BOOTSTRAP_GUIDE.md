# Architecture & Extension Guide

How the accelerator is put together, and how to grow a generated app.

## The supervisor loop

Every turn flows through a LangGraph state machine:

```
guardrails → supervisor → (conditional) specialist → supervisor → … → terminal
```

- **guardrails** ([app/agents/guardrails.py](app/agents/guardrails.py)) runs first:
  trims history, flags prompt injection, can escalate.
- **supervisor** ([app/agents/nodes/supervisor.py](app/agents/nodes/supervisor.py))
  picks the next node via `next_agent(state)` and enforces a per-turn step budget
  so the loop can't run away.
- **specialists** do one job and return to the supervisor. The baseline ships one
  (`example_agent`); real apps add many (KYC, pricing, risk, …).
- **terminal nodes** (`respond_and_wait`, `human_review`) end the turn.

State is a single `AgentState` TypedDict ([app/agents/state.py](app/agents/state.py))
carried through the graph and persisted to Postgres.

## Durability with Temporal

The example router runs the graph **inline** so the app works with zero extra
infra. For production, run each turn as a Temporal activity inside a workflow so
it's durable, retryable, and observable:

- [app/workflows/example_workflow.py](app/workflows/example_workflow.py) — the workflow
- [app/workflows/activities.py](app/workflows/activities.py) — `run_agent_turn` + persistence
- [app/workers/worker.py](app/workers/worker.py) — registers workflow + activities,
  auto-creates the namespace (survives ACA scale-from-zero), enables TLS on `:443`

Switch the router from `compiled_graph.ainvoke(...)` to `client.execute_workflow(...)`
(the commented block in [app/api/routers/example.py](app/api/routers/example.py)).

## Observability

[app/observability/tracing.py](app/observability/tracing.py) wires OpenTelemetry to
Phoenix over OTLP/HTTP and instruments LangChain + OpenAI, so every LLM call and
agent turn shows up as a trace. Both the API and the worker call `init_tracing()`
with distinct `service_name`s so you can tell the two execution paths apart.

## Configuration & secrets

All config lives in [app/shared/config.py](app/shared/config.py) (pydantic-settings,
`.env`-backed). Any field with a matching `*_kv_uri` is transparently resolved from
Azure Key Vault at startup by [app/security/vault.py](app/security/vault.py) — code
reads plain fields and never knows about KV.

---

## How to add …

### …an agent
1. Create `app/agents/nodes/my_agent.py` with `def my_agent_node(state): …` (copy
   `example_agent.py`).
2. Add its system prompt at `app/config/prompts/my_agent.yaml`.
3. Register it in [app/agents/graph.py](app/agents/graph.py): `add_node`, add to the
   supervisor's conditional-edge map, and loop it back to `supervisor`.
4. Teach the supervisor when to pick it in
   [app/agents/nodes/supervisor.py](app/agents/nodes/supervisor.py) `next_agent()`.

### …an API route
1. Create `app/api/routers/my_router.py` with an `APIRouter`.
2. Register it in [app/api/main.py](app/api/main.py) with a `prefix` and `tags`.

### …a DB table
1. Add the model to [app/db/models.py](app/db/models.py).
2. `cd app && alembic revision --autogenerate -m "add my table"` then `alembic upgrade head`.

### …a UI screen
1. Add `app/ui/src/pages/MyPage.tsx`.
2. Add a route in [app/ui/src/App.tsx](app/ui/src/App.tsx) and a nav item in
   [app/ui/src/components/layout/AppShell.tsx](app/ui/src/components/layout/AppShell.tsx).
3. Add API calls in [app/ui/src/services/api.ts](app/ui/src/services/api.ts).

---

## ACA ingress — why the defaults are what they are

The single most common breakage in this stack is the FE→BE proxy. The React app
calls the relative path `/api/v1/...`; nginx proxies that to the backend. Two rules
keep it working:

1. **Backend ingress must be `internal` + `--allow-insecure`.** The nginx proxy
   targets `http://<name>-be.internal.<env>/…`. If the backend is `external`, that
   internal hostname doesn't route (→ 502). If it's internal **without**
   `--allow-insecure`, ACA 301-redirects http→https and the browser's XHR can't
   follow it (→ "Failed to start — is the API running?").
2. **The FE `BACKEND_URL` must use `http://` and the `.internal.` FQDN.**

`infra/aca-setup.sh` and the pipelines' *create* paths already encode this. A plain
`az containerapp update --image` never changes ingress, so once created correctly it
stays correct — but a re-`create` (or a script that sets `external`) will break it.
