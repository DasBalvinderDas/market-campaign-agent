# The Campaign Provisioner (Google Next 2027 edition)

An autonomous Google ADK agent that handles campaign logistics: it checks stock, gets vendor quotes, approves spend and
creates purchase orders, and it stops for a named human when the amount is high.

A central **root agent** governs three **sub-agents**: inventory, procurement and budget.

| Part | What it does | Where it lives |
|---|---|---|
| **Google BigQuery** | All data: stock, vendor prices, budgets (ledger), approval tiers, approver emails, requests, purchase orders, audit log | dataset `campaign_provisioner` |
| **Google Application Integration** | The two workflow actions: `create_purchase_order` and `notify_approver` (sends the approval email), called through ADK's Application Integration toolset | integration `campaign-provisioner-workflows` |
| **Human in the loop** | Spend above $5,000 needs a person: an **Application Integration approval** (a native approval task) emails the approver Approve / Reject; asking the agent for the status then creates the PO or releases the stock. Parked options: signed links via a Cloud Run service, or Confirm / Reject in the chat | Application Integration trigger `request_approval` |
| **Service account** | One account (`AGENT_SERVICE_ACCOUNT`) with BigQuery + Application Integration access runs the deployed agent and the link service | `.env` |
| **Vertex AI Agent Engine** | Where the finished agent runs (hosted, managed sessions) | `scripts/deploy_agent_engine.py` |
| **Code guard** | A purchase order is blocked unless an approved budget covers it | `campaign_provisioner/workflow/guard.py` |

Approval tiers (a BigQuery table, so they can change without code): up to $5,000 auto-approved, $5,000 to $50,000
Marketing Director, above $50,000 VP Marketing + Finance Controller.

## Set it up (Cloud Shell or any shell with gcloud)

```bash
git clone -b claude/next-2027-enhanced https://github.com/dasbalvinderdas/market-campaign-agent.git
cd market-campaign-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                                   # unit tests, no cloud needed

export GOOGLE_CLOUD_PROJECT=<your-project-id>
python scripts/setup_all.py --approver-email "you@example.com"
python scripts/verify_setup.py --integration
adk web --port 8080                      # then open Web Preview on port 8080

```

## Deploy to Vertex AI Agent Engine (final step, Cloud Shell)

```bash
source scripts/env_setup.sh --service-account <your-service-account>   # 1. venv, packages, project, login/API/data checks
python scripts/deploy_agent_engine.py       # 2. deploys the agent (runs as your service account)
python scripts/query_agent_engine.py "NEXT27-MAIN needs 1 booth LED video wall."   # talk to it; handles Confirm / Reject
```

New project? `source scripts/env_setup.sh --approver-email you@example.com` also creates the BigQuery data and the workflow.
Details: `docs/DEMO_RUN.md` section 14.

`setup_all.py` checks your APIs and permissions first and lists anything missing (which API to enable, which role to ask
for). It then creates the BigQuery dataset, tables, views, demo data and approver emails, creates and publishes the
Application Integration workflow, and writes one `.env` file. It is safe to re-run. The BigQuery API, Application Integration
API and Vertex AI API must be enabled in the project.

## Documentation

| Document | What is in it |
|---|---|
| [docs/FRESH_SETUP.md](docs/FRESH_SETUP.md) | Cheat sheet: fresh setup, reset demo data, full BigQuery rebuild, update after new code, change approver emails |
| [docs/DEMO_RUN.md](docs/DEMO_RUN.md) | Step-by-step setup, how the flow works, how to set up and change the data and approver emails, and the test prompts with the human-in-the-loop cases highlighted |
| [docs/SOLUTION.md](docs/SOLUTION.md) | The problem, design, code flow, BigQuery data model, assumptions and limitations |
| [integration/README.md](integration/README.md) | The Application Integration workflow: variables, tasks and how it is created |
| [bigquery/schema.sql](bigquery/schema.sql) | BigQuery DDL (generated from `campaign_provisioner/data/schema.py`) |
| `docs/Campaign_Provisioner_Management_Deck.pptx` | Three-slide management deck with an editable architecture diagram showing BigQuery and Application Integration (regenerate with `docs/build_deck.js`) |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/setup_all.py` | One command: preflight checks, BigQuery, Application Integration, `.env` |
| `scripts/setup_bigquery.py` | BigQuery only; `--reset-demo` clears demo transactions between runs, `--reset` rebuilds, `--approver-email` sets who is emailed |
| `scripts/setup_application_integration.py` | Application Integration only; `--test` runs both triggers once and sends a test email, `--print-definition` shows what is sent |
| `scripts/verify_setup.py` | Reads back the BigQuery data and (with `--integration`) the tools ADK builds from the integration |
| `scripts/env_setup.sh` | Run first with `source`: Python environment, packages, project variables, login / API / data checks |
| `scripts/deploy_approval_service.py` | (Parked: needs a public Cloud Run endpoint) Deploys the Cloud Run service behind signed Approve / Reject links and saves its URL in `.env` |
| `scripts/deploy_agent_engine.py` | Grants the agent's permissions and deploys the agent to Vertex AI Agent Engine (`--dry-run` to check first; run it again after code changes and it updates the saved deployment, `--new` for a separate one) |
| `scripts/agent_engine_logs.py` | Shows the deployed agent's recent logs (used automatically when a request fails) |
| `scripts/query_agent_engine.py` | Talks to the deployed agent and handles the human Confirm / Reject |

## Configuration

One `.env` file in the repo root (written by `setup_all.py`, template in `.env.example`): Gemini settings, project, BigQuery
dataset and location, Application Integration name and region, and the initial approver emails. After setup the approver
emails are read from the BigQuery `approvers` table, so you change them there.

## Status

Verified on a real Google Cloud project: the BigQuery setup, creating and publishing the Application Integration workflow,
running both triggers, reading the data back, and ADK discovering the two integration tools. Not yet confirmed: approval
email delivery to an inbox, a full agent run with Gemini, the in-chat Confirm / Reject pause, and the Agent Engine deployment (new). See the last section of
`docs/DEMO_RUN.md`. Unit tests (`pytest`) cover the tools, policy, guard, audit trail, setup scripts and the BigQuery
repository (against a stub client).
