# The LaunchKit Provisioner

An autonomous Google ADK agent that plans product-launch collateral against a deadline. A Product Marketing Manager gives it a
brief ("150 VIP creator kits, 10 showroom displays, 300 sales folios for Project Aurora"); it works out what is needed in which
region, reuses surplus stock from regional depots, **computes three sourcing options** against the in-hand date and the press
embargo, lets the manager choose, gets a named executive to sign off above the autopilot limit, and has the purchase orders and
depot transfers placed. It is built for **Gemini Enterprise** (the root agent writes every reply) and runs on Vertex AI Agent Engine.

It is a launch-readiness planner, not a spend approval bot: the decision is "which way do we hit the date?" (with cost, buffer, carbon
and risk per option), and approval is only the last gate for the chosen option.

| Part | What it does | Where it lives |
|---|---|---|
| **Root agent** | Takes the brief, calls the three specialists as tools, shows the decision card, holds the sign-off gate, answers status questions | `launchkit_provisioner/agent.py` |
| **Brief Analyst** | Breaks the brief into requirement lines (creator kits personalised by size and plug, showroom displays, sales folios) | `sub_agents/brief_analyst_agent.py` |
| **Sourcing Planner** | Computes the 3 options (full new, smart depot rebalance, eco launch) with cost, delivery date, safety buffer, savings, carbon, risk; re-plans on a vendor delay | `sub_agents/sourcing_planner_agent.py`, `planner.py` |
| **Fulfilment** | Places the orders of the approved option in one batch: POs, depot transfers, tracking update | `sub_agents/fulfilment_agent.py`, `execution.py` |
| **Google BigQuery** | All data: launches, creators, depots and stock, lanes, vendors and offers, rules, policy, the computed plan, decisions, orders, audit log | dataset `launchkit` (`bigquery/schema.sql`) |
| **Google Application Integration** | Four workflows: `create_purchase_order`, `create_depot_transfer`, `request_approval` (native Approve / Reject email) and `send_launch_update` | integration `launchkit-workflows` |
| **Service account** | One account (`AGENT_SERVICE_ACCOUNT`) with BigQuery + Application Integration access runs the deployed agent | `.env` |
| **Vertex AI Agent Engine / Gemini Enterprise** | Where the agent runs and is used | `scripts/deploy_agent_engine.py` |

Sign-off tiers (a BigQuery table, so they change without code): up to $5,000 runs on **autopilot** (the recommended option is
executed by policy), $5,000 to $50,000 needs the **VP Product Marketing**, above $50,000 the **CMO**.

## Set it up (Cloud Shell or any shell with gcloud)

Everything is created and controlled by scripts; nothing is built by hand.

```bash
git clone https://github.com/dasbalvinderdas/market-campaign-agent.git && cd market-campaign-agent
git checkout claude/budget-approval-reshape
# put GOOGLE_CLOUD_PROJECT and AGENT_SERVICE_ACCOUNT in .env (see .env.example), then:
source scripts/env_setup.sh --approver-email "you@example.com,colleague@example.com"
python scripts/deploy_agent_engine.py
python scripts/setup_bigquery.py --reset-demo        # clean demo data before a demo
```

`env_setup.sh` prepares the Python environment, checks login and APIs, and (with `--approver-email`) creates the BigQuery dataset,
tables, views and demo data and the Application Integration workflows. Full steps, reset and troubleshooting:
[`docs/FRESH_SETUP.md`](docs/FRESH_SETUP.md). Test prompts for a demo: [`docs/DEMO_RUN.md`](docs/DEMO_RUN.md).

## How a request flows

1. **Brief** (chat): the manager describes what the launch needs.
2. **Plan**: the Brief Analyst and the Sourcing Planner compute the requirement lines and three options from BigQuery. The reply
   is a decision card (cost, arrival, buffer in hours, carbon, risk per option).
3. **Choose**: the manager replies with an option. Within the autopilot limit the recommended option runs by itself.
4. **Sign off**: above the limit an Application Integration approval emails the executive (Approve / Reject). The reply starts with
   **HUMAN APPROVAL REQUIRED**; surplus depot stock is held; nothing is ordered.
5. **Execute**: when the user asks for the status after the click, the orders are placed (POs, depot transfers) and the launch
   team gets a tracking update. A rejection releases the held stock.

## Documents

| File | Contents |
|---|---|
| [docs/FRESH_SETUP.md](docs/FRESH_SETUP.md) | Cheat sheet: fresh setup, reset demo data, rebuild, update after new code, change approver emails, test and debug the sign-off |
| [docs/DEMO_RUN.md](docs/DEMO_RUN.md) | How to run it and the test prompts (autopilot, choose, executive sign-off, rejection, vendor delay, tier change) |
| [docs/SOLUTION.md](docs/SOLUTION.md) | The problem, design, scenario engine, data model, what makes it different, assumptions and limitations |
| [integration/README.md](integration/README.md) | The four Application Integration workflows: variables, tasks and how they are created |
| [bigquery/schema.sql](bigquery/schema.sql) | BigQuery DDL (generated from `launchkit_provisioner/data/schema.py`) |
| `docs/LaunchKit_Provisioner_Management_Deck.pptx` | Three-slide management deck with an editable architecture diagram (regenerate with `docs/build_deck.js`) |
| `docs/LaunchKit_Provisioner_Agent_Catalog.xlsx` | Root and sub-agent summary, tools, BigQuery tables, workflows, flow, governance (regenerate with `docs/build_agent_catalog.py`) |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/env_setup.sh` | Run first with `source`: Python environment, packages, project variables, login / API / data checks |
| `scripts/setup_all.py` | One command: preflight checks, BigQuery, Application Integration, `.env` |
| `scripts/setup_bigquery.py` | BigQuery only; `--reset-demo` clears the transactions and moves the launch dates to today, `--reset` rebuilds, `--approver-email` sets who signs off and who gets updates |
| `scripts/setup_application_integration.py` | Application Integration only; `--test` runs the order triggers once, `--republish` after changing approver emails, `--print-definition` shows what is sent |
| `scripts/verify_setup.py` | Reads back the BigQuery data and (with `--integration`) checks the four workflows are published |
| `scripts/deploy_agent_engine.py` | Deploys (or updates) the agent on Vertex AI Agent Engine as the service account in `.env` |
| `scripts/query_agent_engine.py` | Talks to the deployed agent from the shell |
| `scripts/check_approval.py` | Shows what Application Integration says about a sign-off when a status looks wrong |
| `scripts/agent_engine_logs.py` | Shows the deployed agent's recent logs |

## Configuration

One `.env` file in the repo root (template in `.env.example`): Gemini settings, project, BigQuery dataset and location,
Application Integration name and region, the service account and the initial approver emails. After setup the emails are read from
the BigQuery `approvers` table. Planning rules (safety buffers) and sign-off tiers are BigQuery tables too.

## Tests

`pip install -r requirements.txt && pytest` runs the unit tests (planner, sign-off flow, execution, BigQuery repository against a
stub client with SQL syntax checks, setup scripts) and an end-to-end run of the real agent tree through ADK's runner with a scripted
model. No cloud access is needed.
