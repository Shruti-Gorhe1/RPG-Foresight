# RPG Foresight

RPG Foresight is a tender-signal and pursuit workspace for collecting tender
records, organizing bid activity, evaluating routing rules, notifying selected
recipients, and preparing evidence-based bid reviews.

The application has a React/TypeScript web interface, a FastAPI backend, and a
PostgreSQL database. LangGraph coordinates the conversational and ingestion
workflows. The configured chat model is used for conversational assistance and
selected document-review tasks; tender ingestion and rule-based notification
routing use deterministic application logic.

## What the application does

- **Pipeline dashboard** — shows tender records, stages, estimated win
  probabilities when available, and subsidiary views.
- **Source connections** — shows registered connectors and their sync status.
- **Tender operations** — creates and updates tenders, imports CSV/Excel files,
  records feedback and follow-ups, and provides reports and CSV exports.
- **Rules and policies** — defines tender stages, probability/freshness limits,
  material, region, value, currency, and closing-date conditions; previews
  matches before enabling a rule.
- **Recipient management** — maintains a tenant-scoped email address book used
  by routing rules.
- **Signal history and delivery status** — displays routing decisions, delivery
  attempts, delivery statistics, and email-provider status; supports test email
  and eligible failed-delivery retries.
- **Tender Pursuit Copilot** — reviews a tender and uploaded documents, cites
  extracted evidence, identifies risks, and prepares a provisional
  bid/review/no-bid recommendation and next steps for human review.
- **Tender Operations assistant** — answers questions using tenant-scoped tender
  search, enabled-connector lookup, and routing-rule lookup tools.
- **Observability** — exports API, agent, connector, routing, and model-call
  traces to Arize Phoenix or a configured Arize collector.

## Workflows

### Sync Signals

1. The user starts a sync from the dashboard or the sync API.
2. The ingestion workflow discovers enabled connectors and loads stored tender
   event/revision identifiers for deduplication.
3. Enabled connectors fetch and normalize their source records.
4. New records and associated outcome snapshots are saved to PostgreSQL. Existing
   event/revision pairs are skipped.
5. Available win-probability estimates are calculated from tenant-scoped
   historical outcome snapshots.
6. Newly saved tender events are evaluated against enabled routing rules.
7. Matching recipient decisions and delivery attempts are recorded. The selected
   notification adapter attempts delivery, and the sync result reports sent and
   failed delivery counts.

Sync is not a continuous change stream: connectors run when a sync is triggered.
The primary routing flow evaluates newly created records, so an unchanged
record does not generate another alert on every sync.

### Rule-based email routing

Rules can be previewed against recent tenders before being enabled. Previewing a
rule does not send email. During a sync, a newly saved tender can trigger a
delivery when it matches an enabled rule and the selected recipient belongs to
the tenant's address book. Conditions can include stage, minimum win
probability, data freshness, material route, region, tender value/currency, and
days until closing.

Email delivery is implemented through the configured SMTP or Resend adapter.
The Delivery Status page shows provider configuration and delivery/attempt
history. Matching tender alerts are delivered to the selected recipients'
inboxes.

### Tender Pursuit Copilot

The Copilot validates a stored tender, then runs qualification, document
evidence, risk review, and action-planning specialists in sequence. It supports
PDF, DOCX, and UTF-8 text uploads, extracts cited text locations, and can use
the configured chat model to summarize evidence. Qualification and risk
checks use explicit application logic; recommendations are decision support
and require human review. The Copilot does not submit bids or send tender
notifications.

### Tender Operations assistant

The conversational assistant uses the configured model and can call these
read-only, tenant-scoped tools:

- Search tenders by project name, tender reference, or stage.
- List enabled connectors.
- List enabled routing rules without exposing recipients.

### Temporal workflow

The API currently runs interactive graph sessions inline. The repository also
contains a Temporal example workflow, worker, and activities for durable
orchestration. The Temporal status-notification activity currently logs status
changes; it is separate from the operational tender-routing email flow.

## Architecture

```text
React + TypeScript UI
        |
        | /api/v1
        v
FastAPI
  |-- LangGraph agent and ingestion workflows
  |-- Connector registry and normalization
  |-- Tender operations, rules, recipients, and delivery APIs
  |-- Pursuit Copilot and document processing
  |-- SMTP / Resend / Teams adapters
        |
        v
PostgreSQL
```

| Component | Location | Responsibility |
|---|---|---|
| Web UI | `agent-registry/app/ui` | Dashboard and tender-management pages |
| API | `agent-registry/app/api` | FastAPI routes, request validation, and tenant scoping |
| Agents and graphs | `agent-registry/app/agents` | LangGraph supervisors, specialists, and internal tools |
| Connectors | `agent-registry/app/ingestion/connectors` | CRM/demo connectors and source normalization |
| Domain services | `agent-registry/app/services` | Routing, delivery, probability, document, and Copilot logic |
| Database | `agent-registry/app/db` and `agent-registry/app/alembic` | SQLAlchemy models and migrations |
| Tests | `agent-registry/app/tests` | Backend unit and integration tests |

## Data sources and integrations

- **Zoho CRM** has an OAuth2 read-only connector. It must be enabled and supplied
  with valid OAuth credentials, the correct Zoho data-center domains, module,
  tenant, and sender-entity configuration before it can provide live records.
- **iTrack-style records** are available through a local demonstration
  connector. Replace or disable that source when using live CRM data.
- **Subsidiary views** have a separate demonstration connector. Connect the
  relevant subsidiary CRM sources to replace those records with live data.
- **Public tender portals** (CPPP, Government eTenders, and KEC disclosures)
  are represented by placeholder adapters and are not currently live ingestion
  sources in the main Sync Signals workflow.
- **Email** supports SMTP and Resend. **Teams** has a separate adapter.
  Configure the required provider credentials and verify the provider's
  delivery domain before relying on alerts.
- **LLM provider** supports local Ollama and optional Azure OpenAI. Tender
  ingestion and routing do not require the LLM; the conversational assistant
  and some Copilot document-summarization tasks do.

Demo tender records and probabilities trained from demonstration outcomes are
not production tender data or calibrated bid forecasts. Use validated,
time-stamped historical outcomes for real probability estimates.

## Requirements

- Windows, macOS, or Linux development environment.
- Python with the packages in `agent-registry/app/requirements.txt`.
- Node.js and npm for the web UI.
- PostgreSQL 16 or a compatible PostgreSQL service.
- Ollama with a supported local model, or Azure OpenAI configuration, if using
  model-backed assistant and document-summary features.
- SMTP or Resend configuration if using email alerts.

Redis is not required.

## Local development

The commands below are for PowerShell from the repository root.

### 1. Configure the backend

Create `agent-registry/app/.env` from the example if it does not already exist:

```powershell
Copy-Item agent-registry\app\.env.example agent-registry\app\.env
```

Edit that file for your local environment. At minimum, configure the database
connection. For model-backed assistant features, configure Ollama or Azure
OpenAI. For real routing emails, set `EMAIL_PROVIDER=smtp` and configure
`SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, TLS, and the credentials required by your
mail server. Never commit `.env` or put production credentials in source
control.

To start the PostgreSQL service defined in the development Compose file:

```powershell
Set-Location agent-registry\app
docker compose up -d postgres
```

That Compose database uses development-only credentials. Change them and the
database URL before using any shared or production environment.

Install backend dependencies in your chosen virtual environment, then apply
database migrations:

```powershell
Set-Location agent-registry\app
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

Start the API:

```powershell
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8010
```

The API is available at `http://localhost:8010`; interactive API documentation
is at `http://localhost:8010/docs`.

### 2. Configure and start the web UI

In another terminal:

```powershell
Set-Location agent-registry\app\ui
Copy-Item .env.example .env
npm install
npm run dev
```

The Vite development server is normally available at
`http://localhost:5173` and proxies `/api` requests to
`http://localhost:8010`. Set `VITE_API_URL` in the UI `.env` if the API runs at
a different address.

### 3. Optional model setup

For local inference, install Ollama and download the configured model. The
example configuration uses:

```powershell
ollama pull qwen2.5:3b
```

Make sure the Ollama service is running and that `OLLAMA_BASE_URL` and
`OLLAMA_MODEL` in the backend environment match your local setup. To use Azure
OpenAI instead, configure the Azure endpoint, API key, deployment, and set
`LLM_PROVIDER=azure_openai`.

### 4. Optional services

The API and Sync Signals flow can be developed with PostgreSQL and the backend
alone. Temporal and Phoenix are optional for the usual local UI/API workflow.
To run Phoenix locally for tracing:

```powershell
Set-Location agent-registry\app
docker compose up -d phoenix
```

Phoenix is available at `http://localhost:6006`. The development Compose file
also defines a Temporal server, worker, and Temporal UI. Its Docker and
Temporal configuration includes template values such as
`__BACKEND_PORT__`, `__NAMESPACE__`, and `__TASK_QUEUE__`; replace these with
valid values before starting those services. The worker runs the Temporal
workflow path; it is not required for API-triggered inline Sync Signals.

## API areas

The API is versioned under `/api/v1`.

| Area | Base path | Purpose |
|---|---|---|
| Health | `/health` | Service health check |
| Data ingestion | `/data-ingestion` | List tenders, sync connectors, inspect connector status, and access subsidiary views |
| Tender operations | `/tenders` | Create/edit/import tenders, feedback, follow-ups, previews, and reports |
| Rules | `/rules` | Create, list, enable/disable, and delete routing rules |
| Recipients | `/recipients` | Manage email recipients and view routing decisions |
| Signal history | `/signal-history` | View delivery/signal history and audit entries |
| Delivery status | `/delivery-status` | View delivery attempts, test email, and retry eligible failures |
| Pursuit Copilot | `/pursuit` | Analyze tenders, chat about assessments, and record bid/no-bid decisions |
| Example sessions | `/example` | Start, resume, and retrieve conversational agent sessions |

OpenAPI documentation is available at `/docs` while the API is running.

## Tender data and probability notes

Tender win probability is calculated by the application from tenant-scoped
historical outcome snapshots. The estimator uses stage, primary material,
region, currency, and a currency-relative tender-value band. An estimate is
unavailable when there are fewer than 10 distinct historical tenders at that
stage or the history does not contain both wins and losses. Source-provided
probability values are not trusted as the calculated estimate.

Demonstration history is kept separate from non-demonstration history. Validate
any estimate against held-out, time-separated outcomes before using it for
business decisions. See [Tender Operations](agent-registry/app/TENDER_OPERATIONS.md)
for details on imports, routing rules, probabilities, delivery, follow-ups, and
Copilot review.

## Development and tests

Run backend tests from the application directory:

```powershell
Set-Location agent-registry\app
python -m pytest
```

Build and type-check the frontend:

```powershell
Set-Location agent-registry\app\ui
npm run build
```

Tests use isolated databases and substitute external services where
appropriate; they do not send real notifications.

## Security and operational notes

- Tenant scope is applied to tender, rule, recipient, and Copilot data.
- Development authentication supports local development tokens/default
  identity. It is not a production identity provider. Configure and validate a
  production OIDC/Entra ID integration before deployment.
- Use a unique application secret, production database credentials, restricted
  CORS origins, and a verified outbound email domain outside local development.
- Apply Alembic migrations during deployment; development mode can create
  missing ORM tables automatically.
- Scanned PDFs without selectable text are not OCR-processed. Uploaded
  originals are processed in memory and are not persisted by the Copilot.
- Copilot recommendations and risk flags are decision support. Human review
  remains required; the application does not submit bids or perform external
  procurement actions.

## Further documentation

- [Tender Operations guide](agent-registry/app/TENDER_OPERATIONS.md)
- [Agentic workflow design](RPG_Foresight_Agentic_Workflow_DarkMode.md)
>>>>>>> github/main
