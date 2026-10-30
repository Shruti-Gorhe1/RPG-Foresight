# RPG Foresight — Agentic Workflow (Dark Mode Optimized)

All diagrams below are plain-text flowcharts — no mermaid.js required. Every step is numbered and explained so you can understand exactly how the application works from start to end.

---

## 1. Master Architecture — 5 Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 5 — USERS                                     │
│                                                                             │
│   [Dashboard] [Connectors Page] [Rules & Policies] [Signal History] [Delivery│
│    React Frontend                                                       Status]│
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 4 — API GATEWAY                               │
│                                                                             │
│   [GET /tenders] [POST /sync] [GET /connectors] [Auth + Tenant Isolation]   │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       LAYER 3 — AGENTIC PIPELINE                            │
│                                                                             │
│   [Supervisor Node] → [Identify Connectors] → [Connector Runner] → [DB Writer│
│                                                           → [Error Handler]   │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LAYER 2 — CONNECTORS                               │
│                                                                             │
│   [iTrack CRM] [CPPP Portal] [Govt eTenders] [KEC Portal] [New CRM Adapter] │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LAYER 1 — DATABASE                                 │
│                                                                             │
│   [tender_events] [connectors] [routing_rules] [sharing_policies] [notifi-  │
│                                         cation_deliveries] [audit_events]   │
└─────────────────────────────────────────────────────────────────────────────┘
                                │
                                └──────────────── (data feeds back to Users) ───┘

FLOW: Users → API Gateway → Agentic Pipeline → Connectors → Database → Users
```

---

## 2. Agentic Pipeline — Master Flow (Step-by-Step)

```
STEP 1: [User clicks "Sync Signals"]
        │
        ▼
STEP 2: POST /api/v1/data-ingestion/sync  (API receives the request)
        │
        ▼
STEP 3: [Ingestion Supervisor Node] — decides which agent runs next
        │
        ▼
STEP 4: [Router] — checks current state and picks the next node:
        │
        ├─► If connectors NOT identified    → [Identify Connectors Node]
        ├─► If identified, NOT run          → [Connector Runner Node]
        ├─► If run, NOT written             → [DB Writer Node]
        ├─► If all_done OR failed           → [Return Sync Summary]
        └─► If step_status failed           → [Error Handler Node]
        │
        ▼ (each node returns to Supervisor after completing)
        │
STEP 5: [Identify Connectors Node]  → fetches existing event IDs, lists enabled connectors
STEP 6: [Connector Runner Node]     → runs all connectors concurrently (fetch → normalize → dedup)
STEP 7: [DB Writer Node]            → writes new tender events to database
STEP 8: [Error Handler Node]        → logs any errors gracefully
        │
        ▼
STEP 9: [Return Sync Summary to User] — pipeline complete
```

---

## 3. Turn-by-Turn Execution Trace

```
TURN 1: Supervisor initializes ingestion state (turn_count = 1)
TURN 2: Identify Connectors — queries DB for existing (event_id, source_revision) pairs
TURN 3: Connector Runner — iTrack fetches 3 records, normalizes, deduplicates
TURN 4: DB Writer — inserts 3 new tender events, commits transaction

RESULT: { total_created: 3, connectors_run: 1, errors: [] }

┌──────────────┬──────────────────────────────────────────────────────────────┐
│ Turn         │ Action                                                       │
├──────────────┼──────────────────────────────────────────────────────────────┤
│ 1            │ Supervisor starts, sets up ingestion context                 │
│ 2            │ Identify Connectors fetches existing IDs from DB             │
│ 3            │ Connector Runner runs iTrack, gets 3 records                 │
│ 4            │ DB Writer inserts 3 new events into tender_events table      │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

---

## 4. Node-by-Node Execution Detail

### 4.1 Identify Connectors Node

```
START
  │
  ▼
[1] Open AsyncSessionLocal DB session
  │
  ▼
[2] Query tender_events: SELECT event_id, source_revision
  │
  ▼
[3] Build existing_event_ids set of tuples (for deduplication)
  │
  ▼
[4] Call registry.list() to get all registered connectors
  │
  ▼
[5] Filter: keep only is_active AND is_enabled connectors
  │
  ▼
[6] Store existing_event_ids in state.collected.ingestion
  │
  ▼
[7] Store connector_ids list in state
  │
  ▼
[8] Set connectors_identified = True
  │
  ▼
[9] Set step_status = completed
  │
  ▼
RETURN to Supervisor
  │
  └─► (If DB error at step 2: log error, continue with empty set, go to step 4)
```

### 4.2 Connector Runner Node

```
START
  │
  ▼
[1] Get enabled connectors from registry
  │
  ▼
[2] Decision: Any connectors?
  │
  ├─ NO ──► Set all_done = True, step_status = completed, RETURN
  │
  └─ YES ─► [3] Run all connectors concurrently via registry.run_all(existing_ids)
            │
            ▼
        [4] For each connector result:
            │
            ├─► fetch()      — raw records from source
            ├─► normalize()  — map to TenderEvent schema
            ├─► deduplicate()— remove existing revisions
            ├─► Store records in connector_results dict
            │
            ▼
        [5] Calculate total_fetched, total_normalized
        [6] Collect all errors from all connectors
        │
        ▼
        [7] Set connectors_run = True
        │
        ▼
RETURN to Supervisor
  │
  └─► (If fetch throws exception: log exception, add to errors, continue)
```

### 4.3 DB Writer Node

```
START
  │
  ▼
[1] Open AsyncSessionLocal DB session
  │
  ▼
[2] Get connector_results from state
  │
  ▼
[3] Decision: Any results?
  │
  ├─ NO ─► Set all_done = True, RETURN
  │
  └─ YES ─► [4] For each connector result:
            │
            ├─► [5] Create ConnectorRun record (status, counts, errors)
            ├─► [6] flush() to get run ID
            │
            ▼
            [7] For each normalized record:
                │
                ├─► [8] Check: does (event_id + source_revision) exist?
                │   │
                │   ├─ YES ──► Skip (duplicate)
                │   │
                │   └─ NO  ─► [9] Insert new TenderEvent row
                │
                ▼
                [10] Next record (loop back to step 8)
            │
            ▼
        [11] commit() transaction
        │
        ▼
        [12] Set results_written = True, all_done = True
        [13] Set total_created count
        │
        ▼
RETURN to Supervisor
  │
  └─► (If insert throws exception: log error, add to errors list, continue to next record)
```

### 4.4 Error Handler Node

```
START
  │
  ▼
[1] Retrieve errors from state.collected.ingestion.errors
  │
  ▼
[2] Log all errors with severity
  │
  ▼
[3] Set step_status = completed
  │
  ▼
[4] Set ingestion.all_done = True
  │
  ▼
RETURN to Supervisor
```

---

## 5. Connector Execution Sub-Graph (Per Connector)

```
┌─────────────────────────────────────────────────────────────────┐
│              Single Connector Execution (iTrack example)        │
│                                                                   │
│   STEP 1: fetch()                                                │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Raw API/DB call to iTrack CRM                          │   │
│   │  Returns: 3 mock tender records                         │   │
│   └─────────────────────────────────────────────────────────┘   │
│                           │                                       │
│                           ▼                                       │
│   STEP 2: normalize()                                            │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Map iTrack fields → TenderEvent schema                 │   │
│   │  itrack_tender_id → event_id                            │   │
│   │  revision → source_revision                             │   │
│   │  current_stage → stage                                  │   │
│   │  materials → material_categories                        │   │
│   └─────────────────────────────────────────────────────────┘   │
│                           │                                       │
│                           ▼                                       │
│   STEP 3: deduplicate()                                          │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Check: (event_id, source_revision) already in DB?      │   │
│   │  If exists → skip                                       │   │
│   │  If new → keep                                          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                           │                                       │
│                           ▼                                       │
│   STEP 4: Return filtered records (ConnectorResult)              │
└─────────────────────────────────────────────────────────────────┘
```

### iTrack Connector Field Mapping

| iTrack Raw Field | → | TenderEvent Field | Example Value |
|-----------------|---|-------------------|---------------|
| itrack_tender_id | → | event_id | IT-2026-1001 |
| revision | → | source_revision | Daily mock revision (for example, `rev-YYYYMMDD`) |
| current_stage | → | stage | Bid Submitted |
| prior_stage | → | prior_stage | Technical evaluation |
| win_probability_percent | → | existing_win_probability_percent | 88.0 |
| materials | → | material_categories | ["Power cables", "Cable accessories"] |
| last_updated | → | occurred_at | Current UTC time at mock connector initialization |
| tenant_id | → | tenant_id | KEC-001 |
| source_type | → | source_type | crm |
| data_provenance | → | data_provenance | CRM: iTrack - internally authorized bid data |

---

## 6. Complete State Diagram

```
START
  │
  ▼
[Supervisor] ──► connectors not identified ──► [Identify Connectors]
  │                                                  │
  │                                                  └────── completed ──────┘
  │                                                  │
  │ identified, not run                              ▼
  │                                      [Connector Runner]
  │                                                  │
  │                                                  └────── completed ──────┘
  │                                                  │
  │ run, not written                                 ▼
  │                                      [DB Writer]
  │                                                  │
  │                                                  └────── completed ──────┘
  │                                                  │
  │ all_done OR failed                               ▼
  └─────────────────────────────────► [Respond & Wait] ──► END
                                      │
                                      └────── step_status failed ──────┘
                                         │
                                         ▼
                                    [Error Handler] ── completed ──┘
```

States:
- **Supervisor** — Ingestion Supervisor Node
- **Identify Connectors** — Identify Connectors Node
- **Connector Runner** — Connector Runner Node
- **DB Writer** — DB Writer Node
- **Error Handler** — Ingestion Error Handler Node
- **Respond & Wait** — Return sync summary to user

---

## 7. Turn Budget Guard

```
START (Turn Starts)
  │
  ▼
[turn_count = 0]
  │
  ▼
[Supervisor executes next agent node]
  │
  ▼
{turn_count >= 10?}
  │
  ├─ YES ──► respond_and_wait — hand control back to user
  │
  └─ NO  ──► Run next agent node ──────────────────┐
        │                                         │
        └─────────────────────────────────────────┘ (loops back)
```

Purpose: Prevents infinite supervisor loops. Maximum 10 steps per ingestion turn.

---

## 8. Error Handling & Partial Failure Flow

```
START (Connector Execution)
  │
  ▼
[Run all connectors concurrently]
  │
  ▼
{Connector A Success?}
  │
  ├─ YES ─► [Store Connector A records]
  │
  └─ NO  ─► [Log Connector A error, continue] ─┐
        │                                      │
        ▼                                      ▼
{Connector B Success?}  ◄──────────────────────┘
  │
  ├─ YES ─► [Store Connector B records]
  │
  └─ NO  ─► [Log Connector B error, continue]
        │
        ▼
[Merge all results + errors]
  │
  ▼
{Any errors?}
  │
  ├─ YES ─► step_status = completed, ingestion.errors populated
  │         │
  │         ▼
  │   [Return summary with errors]
  │
  └─ NO  ─► step_status = completed, clean success
            │
            ▼
      [Return summary]
```

### Example Partial Failure Output:

```json
{
  "status": "completed",
  "steps": 4,
  "connectors_run": 2,
  "connector_ids": ["itrack", "cppp"],
  "total_fetched": 3,
  "total_normalized": 3,
  "total_created": 3,
  "errors": ["cppp: API timeout after 30s"],
  "connector_results": {
    "itrack": { "records": 3, "errors": [], "count": 3 },
    "cppp": { "records": 0, "errors": ["API timeout"], "count": 0 }
  }
}
```

---

## 9. Routing & Policy Flow — Signals to Sister Companies

```
START (Tender Event Ingested into tender_events)
  │
  ▼
[Evaluator loads rules FROM routing_rules table]
  │
  ▼
{Match trigger_stages against event.stage?}
  │
  ├─ NO ─► [Disposition: suppressed — Reason: No matching route]
  │
  └─ YES ─► {Win probability ≥ min threshold?}
            │
            ├─ NO ─► [Disposition: suppressed — Reason: Below threshold]
            │
            └─ YES ─► [Find subsidiary routes FROM subsidiary_routes table]
                      │
                      ▼
                {Check sharing policy FOR each subsidiary?}
                      │
                      ├─ Approved + Not expired ─► [RecipientDecision: candidate]
                      │                              Store in recipient_decisions
                      │                              │
                      │                              ▼
                      │                    [Notification Delivery Adapter]
                      │                              │
                      │                              ▼
                      │                    [Filter payload to allowed_fields only]
                      │                              │
                      │                              ▼
                      │                    [Send via approved channel]
                      │                              │
                      │                              ▼
                      │                    [Record NotificationDelivery sent/failed]
                      │
                      └─ Denied / Revoked / Expired ─► [RecipientDecision: suppressed]
                                                        Reason: No valid policy
                                                        │
                                                        ▼
                                                  [Audit: suppressed]
```

---

## 10. Notification Delivery Flow

```
START (RecipientDecision: candidate)
  │
  ▼
[Notification Adapter]
  │
  ▼
{Check sharing policy: status == approved?}
  │
  ├─ NO ─► [Status: suppressed — Reason: No policy]
  │
  └─ YES ─► [Filter payload to allowed_fields only]
            │
            ▼
      [Send via approved channel — email / Teams / internal]
            │
            ├─ Success ─► [Status: sent — message_id assigned]
            │             │
            │             ▼
            │       [Record NotificationDelivery]
            │
            └─ Failure ─► [Status: failed — error_message + retry_count++]
                          │
                          ▼
                    [Record NotificationDelivery]
                          │
                          ▼
                  [Dashboard: Delivery Status — pending / sent / failed]
```

---

## 11. Data Transformation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ SOURCE: iTrack CRM — Raw Data                                               │
│                                                                             │
│   itrack_tender_id: IT-2026-1001                                            │
│   revision: Daily mock revision (for example, rev-YYYYMMDD)                  │
│   current_stage: Bid Submitted                                              │
│   win_probability: 88.0                                                     │
│   materials: Power cables · Cable accessories                               │
│   last_updated: Current UTC time at mock connector initialization             │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ NORMALIZATION: connector.normalize()                                        │
│                                                                             │
│   event_id ← itrack_tender_id                                               │
│   source_revision ← revision                                                │
│   stage ← current_stage                                                     │
│   existing_win_probability_percent ← win_probability                        │
│   material_categories ← split(materials, "·")                               │
│   occurred_at ← parse_iso(last_updated)                                     │
│   source_type ← crm                                                         │
│   data_provenance ← CRM: iTrack - internally authorized                     │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ DEDUPLICATION: connector.deduplicate()                                      │
│                                                                             │
│   Check: (event_id, source_revision) in existing_ids?                       │
│   ├─ If exists → SKIP                                                       │
│   └─ If new → KEEP                                                          │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ DATABASE: tender_events Table                                               │
│                                                                             │
│   id: auto-increment                                                        │
│   event_id: IT-2026-1001                                                    │
│   source_revision: Daily mock revision                                     │
│   stage: Bid Submitted                                                      │
│   existing_win_probability_percent: 88.0                                    │
│   material_categories: [Power cables, Cable accessories]                    │
│   source_type: crm                                                          │
│   data_provenance: CRM: iTrack - internally authorized bid data             │
│   ingested_at: NOW()                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Frontend Navigation Flow

```
[App Loads]
  │
  ▼
[BrowserRouter]
  │
  ├─► [/ Dashboard]
  │     ├─ Auto-fetch GET /tenders on mount
  │     ├─ Sync Signals → POST /sync
  │     └─ Display signal cards
  │
  ├─► [/playground]
  ├─► [/settings]
  ├─► [/connectors]
  │     ├─ List all connectors
  │     ├─ Per-connector sync button
  │     └─ Show last run status + errors
  │
  ├─► [/rules]
  │     ├─ Routing rules table
  │     └─ Sharing policies table
  │
  ├─► [/recipients]
  │     ├─ Approved recipients
  │     └─ Channel, purpose, expiry
  │
  ├─► [/signal-history]
  │     ├─ Full audit history
  │     └─ Tender, stage, source, probability
  │
  └─► [/delivery-status]
        ├─ Stats: total, pending, sent, failed
        └─ Delivery queue table
```

---

## 13. File Locations — Agentic Components

| Component | File | Role |
|-----------|------|------|
| Supervisor Node | `app/agents/nodes/ingestion_supervisor.py` | Decides which agent runs next |
| Router Logic | `app/agents/nodes/ingestion_supervisor.py: next_ingestion_agent()` | Conditional edge routing |
| Identify Connectors | `app/agents/nodes/identify_connectors.py` | Fetch existing IDs, list connectors |
| Connector Runner | `app/agents/nodes/connector_runner.py` | Run connectors concurrently |
| DB Writer | `app/agents/nodes/db_writer.py` | Persist events, dedup, write runs |
| Error Handler | `app/agents/nodes/ingestion_error_handler.py` | Handle failures gracefully |
| Pipeline Service | `app/services/ingestion_service.py` | Orchestrates all nodes sequentially |
| Connector Base | `app/ingestion/connectors/base.py` | BaseConnector abstract interface |
| Connector Registry | `app/ingestion/connectors/registry.py` | Register, list, run_all connectors |
| iTrack Connector | `app/ingestion/connectors/itrack.py` | Mock CRM connector (3 sample tenders) |
| Notification Adapter | `app/services/notification.py` | Policy-aware delivery adapter |

---

**Quick Summary:**

1. **User** clicks "Sync Signals" in the frontend
2. **API** receives POST /sync and triggers the ingestion pipeline
3. **Supervisor** routes to Identify Connectors → Connector Runner → DB Writer → Error Handler
4. **Connectors** fetch raw data, normalize it, and remove duplicates
5. **Database** stores new tender events and audit records
6. **Notifications** check sharing policies and send to approved recipients
7. **User** receives a sync summary with counts and any errors

---

## Agents Overview — What Agents Are There and How They Work

The RPG Foresight application uses a **LangGraph supervisor pattern** with 5 agent nodes. Each agent is a Python function that receives the shared `AgentState`, does its work, and returns the updated state. The Supervisor acts as the router that decides which agent runs next.

---

### Agent 1: Ingestion Supervisor Node

**File:** `app/agents/nodes/ingestion_supervisor.py`

**What it does:**
This is the "brain" of the pipeline. It starts every ingestion turn and decides which specialist agent should run next based on the current state.

**How it works:**
1. Receives the `AgentState` with `turn_count` and `collected` data.
2. Initializes the ingestion context (sets up `connectors_to_run`, `results`, `total_fetched`, `total_created`, `errors`).
3. Calls `next_ingestion_agent()` to determine the next step.
4. Increments `turn_count` on each call.
5. Returns the updated state to the pipeline service.

**Key logic in `next_ingestion_agent()`:**
- If `step_status == "failed"` → route to Error Handler
- If `all_done == True` → route to Respond (return summary to user)
- If connectors not identified → route to Identify Connectors
- If identified but not run → route to Connector Runner
- If run but not written → route to DB Writer
- Otherwise → route to Respond

**Turn budget:** Maximum 10 steps per turn. If exceeded, control returns to the user.

---

### Agent 2: Identify Connectors Node

**File:** `app/agents/nodes/identify_connectors.py`

**What it does:**
Discovers which connectors are enabled and fetches existing tender event IDs from the database for deduplication.

**How it works:**
1. Opens a database session (`AsyncSessionLocal`).
2. Queries `tender_events` table for all existing `(event_id, source_revision)` pairs.
3. Builds a set of existing IDs to skip duplicates later.
4. Calls `registry.enabled()` to get all active, enabled connectors.
5. Stores `existing_event_ids`, `connector_count`, `connector_ids`, and sets `connectors_identified = True` in state.
6. If the DB query fails, logs the error and continues with an empty set.
7. Sets `step_status = completed` and returns to Supervisor.

---

### Agent 3: Connector Runner Node

**File:** `app/agents/nodes/connector_runner.py`

**What it does:**
Runs all enabled connectors concurrently. Each connector fetches raw data, normalizes it to the TenderEvent schema, and deduplicates against existing records.

**How it works:**
1. Gets `existing_event_ids` from state (populated by Identify Connectors).
2. Gets enabled connectors from `registry.enabled()`.
3. If no connectors are enabled, sets `all_done = True` and returns.
4. Calls `registry.run_all(existing_ids)` which runs each connector's `run()` method:
   - **fetch()** — gets raw records from the source (e.g., iTrack API returns 3 mock tenders)
   - **normalize()** — maps raw fields to TenderEvent schema (e.g., `itrack_tender_id` → `event_id`)
   - **deduplicate()** — removes records already in the database
5. Collects results: `source_name`, `records`, `errors`, `count` for each connector.
6. Calculates `total_fetched`, `total_normalized`, and all errors.
7. Sets `connectors_run = True` and returns to Supervisor.

---

### Agent 4: DB Writer Node

**File:** `app/agents/nodes/db_writer.py`

**What it does:**
Persists normalized tender events to the database. Creates connector run records and inserts new tender events while skipping duplicates.

**How it works:**
1. Opens a database session.
2. Gets `connector_results` from state.
3. If no results, sets `all_done = True` and returns.
4. For each connector result:
   - Creates a `ConnectorRun` record (status, records_fetched, records_normalized, errors).
   - Flushes to get the run ID.
   - For each normalized record:
     - Checks if `(event_id, source_revision)` already exists (defensive dedup).
     - If exists → skips the record.
     - If new → inserts a new `TenderEvent` row with all fields (tenant_id, event_id, stage, source_type, data_provenance, etc.).
     - If insert fails → logs error and continues to next record.
5. Commits the transaction.
6. Sets `results_written = True`, `all_done = True`, and `total_created` count.
7. Returns to Supervisor.

---

### Agent 5: Error Handler Node

**File:** `app/agents/nodes/ingestion_error_handler.py`

**What it does:**
Handles ingestion errors gracefully. Logs all errors and ensures the pipeline completes even if some steps failed.

**How it works:**
1. Retrieves errors from `state.collected.ingestion.errors`.
2. Logs all errors with severity.
3. Sets `step_status = completed`.
4. Sets `ingestion.all_done = True`.
5. Returns to Supervisor, which then routes to Respond.

---

### How Agents Interact (The Supervisor Loop)

```
┌─────────────────────────────────────────────────────────────┐
│                    Ingestion Pipeline Loop                  │
│                                                             │
│  Supervisor ───► next_ingestion_agent() ───► Router        │
│       ▲                                          │          │
│       │                                          ▼          │
│       │     ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│       │     │ Identify │ │ Connector│ │  DB      │        │
│       │     │ Connectors│ │ Runner   │ │ Writer   │        │
│       │     └──────────┘ └──────────┘ └──────────┘        │
│       │              │          │           │              │
│       │              └──────────┴───────────┘              │
│       │                        │                            │
│       └──────────── completed ◄┘                            │
│                                                             │
│  If step_status == "failed" → Error Handler → Supervisor   │
│  If all_done == True → Respond (return summary to user)    │
└─────────────────────────────────────────────────────────────┘
```

### Agent Summary Table

| # | Agent | File | Primary Responsibility |
|---|-------|------|------------------------|
| 1 | Ingestion Supervisor | `ingestion_supervisor.py` | Routes to next agent, manages turn budget |
| 2 | Identify Connectors | `identify_connectors.py` | Fetches existing DB IDs, lists enabled connectors |
| 3 | Connector Runner | `connector_runner.py` | Runs connectors: fetch → normalize → deduplicate |
| 4 | DB Writer | `db_writer.py` | Writes tender events and connector runs to DB |
| 5 | Error Handler | `ingestion_error_handler.py` | Logs errors, ensures pipeline completes |

### State Flow

All agents share the same `AgentState` object which contains:
- `session_id` — unique ID for this ingestion run
- `turn_count` — current step number (max 10)
- `step_status` — pending/in_progress/completed/failed
- `collected.ingestion` — bag of domain data (existing IDs, connector results, counts, errors)

Each agent reads what it needs from state, performs its work, updates state, and returns control to the Supervisor for routing.
