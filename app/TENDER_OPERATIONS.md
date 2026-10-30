# Tender operations

The Tender Operations page adds tender entry and maintenance, CSV/Excel import,
signal feedback, follow-up tracking, deadline reminders, and reporting without
replacing connector ingestion or signal routing.

## Tender input

- Add or edit tenders manually, or upload `.csv`, `.xlsx`, or `.xlsm` files.
- Imports are limited to 10 MB and 2,000 rows. Preview the header and sample
  rows, map columns, then import. Required mappings are tender ID, project name,
  stage, and at least one material category.
- Rows are validated independently; the import response and page list each
  rejected row number with its validation reason.
- Optional fields include event ID, region, tender value, currency, opening
  date, and closing date. Win probability is calculated by the application and
  is not accepted from manual entry or imports.

## Win probability

- Sync stores point-in-time tender feature snapshots and their eventual won/lost
  outcomes in `tender_outcome_snapshots`. The probability estimator trains from
  snapshots scoped to the same tenant and data class (demo or non-demo).
- At each tender stage, a Laplace-smoothed categorical naive Bayes estimate uses
  stage, primary material, region, currency, and currency-relative tender-value
  band. Source-provided probability values are ignored.
- The mock iTrack connector supplies explicitly synthetic stage snapshots for
  demo training. The UI labels these estimates as synthetic and low-confidence;
  they are not calibrated for real bids. Replace the demo outcomes with
  time-stamped historical stage snapshots and final outcomes before relying on
  production estimates. Held-out, time-separated outcomes are required to
  validate calibration.
- If a tenant and data class lack at least 10 distinct historical tenders at
  the current stage, including both won and lost outcomes, the estimate is
  unavailable. Probability-based routing therefore remains fail-closed until
  adequate labeled history is present.

## Rules and delivery

- A newly created rule is a draft. Preview evaluates up to 500 recent
  tenant-owned tenders against the same stage, probability, freshness, material,
  region, value/currency, and closing-window checks used for routing. The
  preview includes counts and per-tender exclusion reasons.
- Stage and material matching ignores capitalization and surrounding spaces.
  Rule criteria must be entered from your actual operating configuration; the
  form does not prefill demo tender criteria. Its maximum event age can be
  adjusted for historical/demo data, while live rules should keep a suitably
  short freshness window.
- Recipients are ordinary tenant-scoped email addresses in the address book.
  Add or remove them there, then select addresses on a routing rule. There are
  no recipient policies, entity IDs, approval steps, or field-scope rules.
- Enable is available after preview. Existing active rules retain their current
  state. Rules can select multiple email recipients.
- Automatic email is attempted for matching tenders during connector sync.
  Previewing a rule does not send mail; after preview, enable the rule and run
  a sync. A test email verifies provider delivery separately from rule matching.
- The mock iTrack connector creates a fresh batch of three uniquely identified
  demo tenders on each sync, so each sync can exercise delivery again without
  re-sending a prior tender. This behavior applies only to demo iTrack data.
- Delete on the Rules page permanently removes a tenant-owned routing rule
  after confirmation and records an audit entry. Existing delivery and audit
  history is retained.
- Editing a recipient email updates its references in existing routing rules.
  Removing an address also removes it from existing rules. These changes are
  tenant-scoped and audit logged.
- Delivery Status shows provider configuration without exposing credentials,
  sends test messages only to an email in the address book, records
  attempt history, and allows a failed delivery to be retried while its
  recipient remains in the address book.
- Delivery and attempt timestamps are stored/returned as UTC and displayed in
  the browser device's local timezone.
- Removing an address prevents future routing to it; previously sent emails
  cannot be recalled.
- Provider configuration does not establish that a sending domain is verified;
  provider rejection details are shown for test messages and delivery attempts.
- Phoenix tracing exports FastAPI request spans plus explicit ingestion,
  routing, and email-send spans. To run Phoenix locally without Docker, install
  app dependencies with `python -m pip install -r requirements.txt`, then run
  `phoenix serve` from `agent-registry\app` using the same virtual environment
  as the backend. Open `http://localhost:6006`. Start the API in a second
  terminal after Phoenix is running. To export to Arize AX instead, set
  `PHOENIX_COLLECTOR_ENDPOINT` to the AX HTTP collector endpoint,
  `ARIZE_SPACE_ID` to the Space ID from Space Settings, and
  `ARIZE_PHOENIX_API_KEY` to an API key authorized for that space. The AX US
  HTTP collector endpoint is `https://otlp.arize.com/v1/traces`; use the
  endpoint for your account's region if it differs. The Sync Signals workflow
  is a supervisor-led LangGraph of deterministic
  specialist agents: connector discovery, connector execution, database
  persistence, and signal routing. These agents use real tools for database
  revision lookup, enabled connector execution, event persistence, and routing
  and delivery. Phoenix shows the supervisor, each specialist, tool spans, and
  the connector/rule/delivery work nested beneath them. The pipeline uses
  deterministic business rules rather than an LLM; this keeps ingestion and
  notification decisions reproducible. iTrack is the only demo-data source;
  database writes, matching, auditing, and configured email delivery are
  operational code. Tests substitute in-memory databases and fake mail
  adapters, and do not send real messages. The Playground Tender Operations
  agent uses local Ollama by default at
  `http://localhost:11434/v1` with the `qwen2.5:3b` model. Run
  `ollama pull qwen2.5:3b` if it is not installed; Azure credentials are not
  required. Set `LLM_PROVIDER=azure_openai` only when intentionally switching
  to Azure. The agent can invoke three read-only tools: tenant-scoped tender
  search, enabled connector lookup, and
  tenant-scoped routing-rule lookup. Ask about a tender, available data source,
  or matching rule to exercise the relevant tool. The Sync Signals tool spans
  are children of their corresponding specialist-agent spans. Sync traces
  include per-event rule-selection and per-rule evaluation spans beneath the
  routing operation. Agent,
  connector, routing, and model-call spans appear only when their corresponding
  operation runs and the trace exporter accepts the request. Playground
  sessions are stored in the SQL `sessions` table. For local Phoenix, run
  `uvx arize-phoenix serve`, set
  `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces`, and leave
  `ARIZE_SPACE_ID` and `ARIZE_PHOENIX_API_KEY` blank. Local traces are exported
  without AX authentication headers.
- Zoho syncing is disabled by default; set `ZOHO_CONNECTOR_ENABLED=true` only
  when its credentials and CRM configuration are ready.

## Feedback, follow-up, and reports

- Signal feedback is Relevant, Not relevant, or Already known, with an optional
  reason. Recommendations are informational and never change rules
  automatically.
- Follow-ups include an assignee, status, notes, and scheduled date. Due and
  overdue follow-ups and tender closing dates are shown in the page as
  in-application reminders; they are not scheduled reminder emails.
- Reports include stage, material, source, region, probability, deadline, and
  recipient breakdowns. Register filters also apply to the CSV export.

## Agentic Tender Pursuit Copilot

- The Copilot runs a supervisor plus qualification, document-evidence,
  risk-review, and action-planning agents in a LangGraph workflow. Each agent
  calls a real tool for specialist selection, tenant-rule matching, document
  text/evidence extraction, risk checks, or next-step planning. The UI shows
  those tool calls under their agent; Phoenix exports the same parent/child
  spans with result counts and review metrics. The workflow uses transparent
  local rules and metadata only; it does not call a hosted LLM or modify CRM
  data.
- Upload up to 10 PDF, DOCX, or UTF-8 TXT documents (10 MB per file, 20 MB
  total). Extracted evidence includes a page, paragraph, or line reference.
  Scanned PDFs without selectable text are rejected because OCR is not included.
- Each assessment is tenant-scoped and persisted with its cited excerpts.
  Uploaded originals are processed in memory and are not stored.
- Recommendations and risk flags are heuristic decision support, not legal or
  financial advice. Win probabilities are outcome-trained estimates and must
  be validated against real held-out results; synthetic demo estimates are not
  reliable for live bid decisions. A human must record the bid/no-bid decision;
  the Copilot does not submit tenders, send email, or take external actions.
  Negated requirements such as “should not have been blacklisted” are treated
  as eligibility criteria, not as evidence that the bidder is excluded.

## Database and run requirements

Apply the Alembic migration before starting the application:

```powershell
cd agent-registry\app
python -m alembic upgrade head
```

Alembic reads `DATABASE_URL` from the application environment, so this command
updates the same database used by the API.

Excel support is provided by `openpyxl` in `requirements.txt`.
