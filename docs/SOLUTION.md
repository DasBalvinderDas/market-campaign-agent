# The Campaign Provisioner (Google Next 2027 edition) - Solution Guide

> Autonomous agent that orchestrates campaign inventory, procurement and budget approval on **BigQuery** data, runs its workflow actions through **Google Application Integration**, and keeps humans in the loop for high-value spend.

This is the enhanced version. The first version used placeholder in-memory data; this one reads and writes BigQuery, calls Application Integration for actions, and applies a tiered approval policy stored in BigQuery.

## 1. The problem

Running a large event campaign such as Google Next 2027 needs many physical and paid items (swag, signage, booth hardware). Today the work is fragmented: stock is checked by hand, vendor quotes arrive by email, budget sign-off happens in a separate process and often after the order is discussed, and nobody has one audit trail. Launches slip, items are re-bought although stock exists, spend exceeds budget, and large purchases are approved informally.

## 2. What the agent does

It takes a plain-language request ("NEXT27-MAIN needs 1 booth LED video wall") and runs the chain in a fixed, governed order.

| Goal | How it is met |
|---|---|
| Remove manual chasing | Specialist sub-agents read live data from BigQuery |
| Avoid duplicate buying | Inventory is always checked and reserved first |
| Control spend | Budget is validated before any order |
| Keep humans in charge of big money | Tiered approval; high tiers pause for a named human |
| Automate the actions | Purchase orders and approver alerts run as Application Integration workflows |
| Be auditable | Every governed action is written to a BigQuery audit table |

## 3. Architecture

A central **root agent** governs three **specialist agents**: inventory, procurement and budget. The root calls each specialist
as a tool (ADK `AgentTool`), and the specialist returns its result to the root, so the root agent writes every reply the user
sees. This is the same on every platform (`adk web`, the Agent Engine playground, Gemini Enterprise), because Gemini Enterprise
shows the root agent's answers only. Each specialist is still its own LLM agent with its own instruction, tools and guards. They
have batch tools (`reserve_items`, `quote_shortfalls`, `assess_budget`) so a request needs a handful of model calls, not one per
item, and every instruction forbids commentary between steps (a front end may treat the first text as the end of the answer).

```
                       campaign_provisioner  (root / orchestrator)
        tools: register_campaign_request, get_campaign_overview, get_audit_trail,
               get_approval_status, approve_budget  (the human approval gate)
        ┌────────────────────────┼─────────────────────────────┐
  inventory_agent          procurement_agent              budget_agent
  reserve_items (batch)    quote_shortfalls (batch)       assess_budget (budget + tier)
  find_sku, check_/        get_vendor_quotes              check_budget, get_approval_policy
  reserve_inventory        create_purchase_order  ──┐     (reports back; never approves)
  release_inventory        (Application Integration)│
                           guard: before / after ◄──┘
        │                         │                               │
        └──────────── Repository (BigQuery) ◄─────────────────────┘
```

| Agent | Responsibility | Never does |
|---|---|---|
| Root `campaign_provisioner` | Understands the request, registers it, delegates in order, **holds the human approval gate (`approve_budget`)**, aggregates results | Specialist work itself |
| `inventory_agent` | Maps descriptions to SKUs, checks stock, reserves, reports shortfall, releases on decline | Buy or discuss budget |
| `procurement_agent` | Quotes vendors, recommends one, creates POs once approved | Approve budget |
| `budget_agent` | Checks funds and the approval tier, emails the approver, reports back | Approve spend, place orders |

## 4. Code layout

```
campaign_provisioner/
  agent.py                    root agent and its instruction
  config.py                   env-driven settings (backends, dataset, integration names)
  data/schema.py              BigQuery tables and views (single source of truth)
  data/seed_data.py           Google Next 2027 demo data
  repositories/               base.py (contract), bigquery_repo.py, memory_repo.py (unit tests only), get_repo()
  tools/                      inventory, procurement, budget, orchestration, audit tools
  workflow/integration.py     Application Integration toolsets (test doubles for unit tests)
  workflow/guard.py           before/after tool callbacks: PO guard, PO recording, audit, tool-error callback
  workflow/integration_client.py  REST client: start a workflow, read an execution and its approval records
  approval_flow.py            builds the purchase plan, starts the approval workflow, reads the decision, finishes it
  sub_agents/                 inventory_agent, procurement_agent, budget_agent
approval_service/             Cloud Run service behind signed Approve / Reject links (parked, main.py)
scripts/                      setup_all.py, setup_bigquery.py, setup_application_integration.py, verify_setup.py,
                              deploy_approval_service.py (parked), deploy_agent_engine.py, query_agent_engine.py,
                              check_approval.py, agent_engine_logs.py, env_setup.sh
.env                          single config file in the repo root (written by setup_all.py)
bigquery/schema.sql           generated DDL
integration/README.md         Application Integration contract and build steps
tests/                        tools, guard, policy, BigQuery repo (stub client)
docs/                         this guide, DEMO_RUN.md, FRESH_SETUP.md (setup / reset cheat sheet), management deck
```

## 5. Data in BigQuery

| Table / view | Purpose |
|---|---|
| `inventory_items`, `inventory_reservations` | Catalog and on-hand stock; reservations are append-only |
| `v_inventory_available` | on_hand minus active reservations = free stock |
| `vendors`, `vendor_catalog` | Suppliers, unit prices, lead times |
| `campaigns`, `budget_ledger` | Total budgets; ledger of SPEND / COMMIT / RELEASE entries |
| `v_campaign_budget` | total, spent, committed, remaining per campaign |
| `approval_policy` | Tiers: amount range, whether a human is needed, approver role |
| `approvers` | Role -> email addresses notified for approval (configured at setup) |
| `campaign_requests`, `purchase_orders` | Registered requests and created POs |
| `request_lines` | What each request asked for, what stock covered and the shortfall (the purchase plan) |
| `approval_requests` | Human approvals: approver, amount, plan, status (PENDING / APPROVED / REJECTED / FAILED), workflow execution id, decision |
| `v_request_headroom` | Approved amount minus PO total per request (used by the guard) |
| `audit_log` | Append-only trail of every governed action |

Money and stock movements are **ledgers**: the agent only inserts rows and the views compute balances, so there are no
read-modify-write updates and every change is traceable. Writes are parameterised DML inserts (values are never
concatenated into SQL). Set it up with `scripts/setup_bigquery.py`; the DDL is in `bigquery/schema.sql`.

## 6. Code flow, step by step

Example: *"NEXT27-MAIN needs 1 booth LED video wall."*

1. **Intake (root).** Confirms campaign and items, calls `register_campaign_request`, which validates the campaign in BigQuery and inserts a `campaign_requests` row and an audit event.
2. **Inventory.** One `reserve_items` call maps every item ("LED video wall" to `BOOTH-LEDWALL`, "event banners" to `BANNER-XL`), reads `v_inventory_available`, reserves the free units and records each line in `request_lines` (LED wall: 0 free, shortfall 1; banners: 2 free, shortfall 6).
3. **Quotes.** One `quote_shortfalls` call reads `vendor_catalog` for every shortfall line and picks the cheapest active vendor: LED wall ExpoVision $18,000 (21 days), 6 banners PrintCo $510. Total $18,510.
4. **Budget.** One `assess_budget` call reads `v_campaign_budget` and `approval_policy`: $18,510 is tier MANAGER (Marketing Director).
   - The budget agent reports the total, remaining budget, tier and approver role back to the root. It never approves.
   - The **root** then calls `approve_budget`. For a tier that needs a person it starts the Application Integration `request_approval`
     workflow (see "Approval by Application Integration" below) and the reply opens with **HUMAN APPROVAL REQUIRED**. Nothing is
     committed and no order exists yet.
   - AUTO tier amounts are approved by policy and the budget is committed at once. Amounts above the remaining budget are rejected directly.
5. **Order.** After approval (auto-approved, or the approver clicked Approve and the user asked for the status) `create_purchase_order` runs as the Application Integration trigger. A `before_tool_callback` recomputes the amount from the vendor price list and checks `v_request_headroom`; with no covering approval it returns `BLOCKED`. After a successful call the `after_tool_callback` stores the PO (with the integration execution id) in `purchase_orders` and writes an audit event.
6. **Decline path.** If the approver rejects, nothing is committed and the reserved stock is released (done by the status check).
7. **Summary.** The root aggregates stock, POs, remaining budget and approver; `get_audit_trail` reads `audit_log`.

### Approval by Application Integration (default)

For tiers that need a person, `approve_budget` (on the orchestrator) does not pause the chat. It builds the purchase plan from
`request_lines` and the vendor price list, stores a PENDING row in `approval_requests`, and starts the Application Integration
trigger `request_approval`. That workflow contains a native **Approval** task (a suspension): the run pauses and the configured
approver(s) receive an Application Integration approval email with **Approve** and **Reject**. Both outcomes are branches of
the flow and end by setting `decision = APPROVED / REJECTED`; the execution id is stored on the PENDING row.
When the user asks `get_approval_status`, the platform reads that execution from the Application Integration API; if it carries a
decision it is recorded atomically (first one wins) and carried out: Approve commits the budget and creates the purchase orders
through `create_purchase_order`; Reject releases the reserved stock. Both write audit rows. The approver addresses are set in
the published integration version (`--approver-email` on `setup_application_integration.py`, `--republish` to change them);
the approval page is Google-hosted, so the approver is likely asked to sign in with the Google account of that address.

Parked alternative (`APPROVAL_CHANNEL=email`, needs a public Cloud Run endpoint): signed HMAC links to the approval-link service
(`approval_service/`) that decides without any login. The code stays in the repo. With `APPROVAL_CHANNEL=chat` the approval is a
Confirm / Reject prompt in the chat.

### Governance in four layers

| Layer | Mechanism |
|---|---|
| Prompt | The root instruction fixes the order; the specialists only return results to the root |
| Policy | Approval tiers live in BigQuery (`approval_policy`) and decide who must approve |
| Platform | The Application Integration approval pauses the flow for tiers that need a human (in-chat Confirm / Reject remains as `APPROVAL_CHANNEL=chat`) |
| Code | The PO guard blocks orders without a covering ledger approval; `approve_budget` rejects overspend; the approval tool lives on the orchestrator so the flow after a human decision does not depend on a sub-agent handing back |

## 7. Application Integration

Three API triggers in one integration (`campaign-provisioner-workflows`): `create_purchase_order`, `request_approval` (the native
Approval task) and `notify_approver` (a plain email through its Send Email task). The recipients come from the BigQuery `approvers` table: the guard
reads them, sets the subject and body, and calls the trigger once per address, so the model never supplies an address.
`python scripts/setup_all.py` sets up BigQuery, the integration and `.env` in one go, and reports missing APIs and permissions up front.
ADK connects with `ApplicationIntegrationToolset`. Variable names are a contract; see `integration/README.md`.


**Who directs the flow.** Today the root agent directs the order of the steps, the agents read and write BigQuery
directly, and Application Integration runs three workflows (purchase order, human approval, plain email). Directing the whole flow from
inside Application Integration (stock, quotes, approval tier, approval, purchase order as one integration, with the agent
as the conversational front door) is a possible next step. Both designs are compared in
[DEMO_RUN.md section 4](DEMO_RUN.md); the second is a design only and is not built yet.

## 8. Data sources, assumptions and limitations

**Where data comes from.** Production-style data lives in BigQuery and is created by `scripts/setup_bigquery.py`.
The figures are **fictional demo data** (budgets, prices, stock, vendors, tier limits) and do not come from any real
Google or customer system. The unit tests use the same seed data in memory, so they need no cloud access.

**Assumptions**

- Single currency (USD); no tax, shipping, discounts or partial deliveries.
- The vendor choice is simple (cheapest unless lead time is a problem); no contracts or delivery-date optimisation.
- The approver is whoever receives the Application Integration approval email (the addresses given to the setup script, fixed in the published integration version). The platform checks the signed-in Google account on the approval page; the application does not map accounts to roles. The addresses shown by the agent come from the BigQuery `approvers` table, so keep both in sync (`docs/FRESH_SETUP.md`, section E).
- The decision is carried out when the status is asked (a second message), not at the click. A fully automatic hand-off needs either a public endpoint (the parked Cloud Run link service) or a BigQuery connector inside the integration.
- The approved amount is committed up front; there is no automatic release if a PO is later cancelled (the ledger supports RELEASE entries, but no tool writes them yet).
- The guard compares cumulative PO totals with the approved amount per request; it does not detect duplicate POs for the same item.
- Rejected or declined requests release stock reservations only when the root agent asks the inventory agent to; this depends on the model following the instruction.
- A single flat tier table applies to every campaign and approver.
- Step order is enforced by prompts, so a live model can deviate. The hard guarantees are in code: no PO without a covering approval, no approval beyond remaining budget.
- Two users working in parallel against the same BigQuery data can both see the same free stock before either reserves; there is no locking.
- The Application Integration workflows are defined by you; the PO guard requires the documented variable names.

**Verified** on a real Google Cloud project: the BigQuery setup, the Application Integration workflows including the approval
flow (created and published by the setup script), the Agent Engine deployment running as the configured service account, the
human-approval round trip (approval email, Approve click recorded as a `LIFTED` approval record, status check creating the
purchase order and committing the budget), and the agent answering in the Gemini Enterprise chat.

The author reports the full prompt set working in the Gemini Enterprise chat (including the human approval). Not separately
recorded in the data: the Reject path (expected: the approval record says `REJECTED`, the stock is released, no PO) and how a second
approver sees a request the first has already decided. Unit tests cover the tools (including the batch tools), tiered policy,
purchase-order guard, approval flow with the real execution shapes seen so far, audit trail, setup scripts and the BigQuery
repository (stub client, SQL syntax).
See DEMO_RUN.md section 13.

## 9. Production notes

- **Deployment target: Vertex AI Agent Engine.** `scripts/deploy_agent_engine.py` deploys the agent; Agent Engine provides the managed sessions, so a pending human approval survives restarts (the approval state lives in BigQuery and Application Integration). The deployed agent runs as its own identity, which needs BigQuery, Application Integration and Vertex AI roles (DEMO_RUN.md section 14). With no `adk web` UI there, the approval request is returned to the client; `scripts/query_agent_engine.py` shows it and sends the Confirm / Reject back, and Gemini Enterprise provides the chat UI (the agent is built for it: the root agent writes every reply).
- Run the agent under a service account with only the roles it needs (BigQuery Data Editor + Job User, Application Integration Invoker, Vertex AI User).
- Send the audit table to Cloud Logging or a Looker dashboard; add alerting on `po_blocked` events.
- Add Model Armor for prompt safety and IAM-based approver checks, as shown in the architecture slide.
- Set `CAMPAIGN_MODEL` to your standard Gemini model (default `gemini-2.5-flash`).
