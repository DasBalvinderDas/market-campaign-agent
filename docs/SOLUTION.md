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

A central **root agent** governs three **sub-agents** (Google ADK multi-agent hierarchy).

```
                       campaign_provisioner  (root / orchestrator)
        tools: register_campaign_request, get_campaign_overview, get_audit_trail
        ┌────────────────────────┼─────────────────────────────┐
  inventory_agent          procurement_agent              budget_agent
  find_sku                 get_vendor_quotes              check_budget
  check_inventory          create_purchase_order  ──┐     get_approval_policy
  reserve_inventory        (Application Integration)│     notify_approver (Application Integration)
  release_inventory        guard: before / after ◄──┘     approve_budget  (HITL confirmation)
        │                         │                               │
        └──────────── Repository (BigQuery) ◄─────────────────────┘
```

| Agent | Responsibility | Never does |
|---|---|---|
| Root `campaign_provisioner` | Understands the request, registers it, delegates in order, enforces rules, aggregates results | Specialist work itself |
| `inventory_agent` | Maps descriptions to SKUs, checks stock, reserves, reports shortfall, releases on decline | Buy or discuss budget |
| `procurement_agent` | Quotes vendors, recommends one, creates POs once approved | Approve budget |
| `budget_agent` | Checks funds and the approval tier, alerts the approver, approves spend | Place orders |

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
  workflow/guard.py           before/after tool callbacks: PO guard, PO recording, audit
  sub_agents/                 inventory_agent, procurement_agent, budget_agent
scripts/                      setup_all.py, setup_bigquery.py, setup_application_integration.py, verify_setup.py,
                              deploy_agent_engine.py, query_agent_engine.py
.env                          single config file in the repo root (written by setup_all.py)
bigquery/schema.sql           generated DDL
integration/README.md         Application Integration contract and build steps
tests/                        tools, guard, policy, BigQuery repo (stub client)
docs/                         this guide, DEMO_RUN.md, management deck
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
| `v_request_headroom` | Approved amount minus PO total per request (used by the guard) |
| `audit_log` | Append-only trail of every governed action |

Money and stock movements are **ledgers**: the agent only inserts rows and the views compute balances, so there are no
read-modify-write updates and every change is traceable. Writes are parameterised DML inserts (values are never
concatenated into SQL). Set it up with `scripts/setup_bigquery.py`; the DDL is in `bigquery/schema.sql`.

## 6. Code flow, step by step

Example: *"NEXT27-MAIN needs 1 booth LED video wall."*

1. **Intake (root).** Confirms campaign and items, calls `register_campaign_request`, which validates the campaign in BigQuery and inserts a `campaign_requests` row and an audit event.
2. **Inventory.** `find_sku` maps "LED video wall" to `BOOTH-LEDWALL`; `check_inventory` reads `v_inventory_available` (0 free); nothing to reserve; shortfall 1.
3. **Quotes.** `get_vendor_quotes` reads `vendor_catalog`: ExpoVision $18,000 (21 days) vs KioskWorks $20,500 (14 days). The agent recommends one.
4. **Budget.** `check_budget` reads `v_campaign_budget`; `get_approval_policy` reads `approval_policy`: $18,000 is tier MANAGER (Marketing Director).
   - The agent calls the **notify_approver** Application Integration trigger so the approver is alerted.
   - `approve_budget` is wrapped in ADK `FunctionTool(require_confirmation=requires_human)`. ADK **pauses** and asks a human to Confirm or Reject. On confirm the function inserts a COMMIT entry (`approved_by = human:Marketing Director`).
   - AUTO tier amounts skip the pause. Amounts above the remaining budget skip it too and are rejected directly.
5. **Order.** `create_purchase_order` is the Application Integration trigger. A `before_tool_callback` recomputes the amount from the vendor price list and checks `v_request_headroom`; with no covering approval it returns `BLOCKED`. After a successful call the `after_tool_callback` stores the PO (with the integration execution id) in `purchase_orders` and writes an audit event.
6. **Decline path.** If the human rejects, nothing is committed, and the root asks `inventory_agent` to `release_inventory` for the request.
7. **Summary.** The root aggregates stock, POs, remaining budget and approver; `get_audit_trail` reads `audit_log`.

### Governance in four layers

| Layer | Mechanism |
|---|---|
| Prompt | The root instruction fixes the order; sub-agents hand back to the root |
| Policy | Approval tiers live in BigQuery (`approval_policy`) and decide who must approve |
| Platform | ADK tool confirmation pauses tiers that need a human |
| Code | The PO guard blocks orders without a covering ledger approval; `approve_budget` rejects overspend |

## 7. Application Integration

Two API triggers in one integration (`campaign-provisioner-workflows`): `create_purchase_order` and `notify_approver`
(which sends the approval email through its Send Email task). The recipients come from the BigQuery `approvers` table: the guard
reads them, sets the subject and body, and calls the trigger once per address, so the model never supplies an address.
`python scripts/setup_all.py` sets up BigQuery, the integration and `.env` in one go, and reports missing APIs and permissions up front.
ADK connects with `ApplicationIntegrationToolset`. Variable names are a contract; see `integration/README.md`.


**Who directs the flow.** Today the root agent directs the order of the steps, the agents read and write BigQuery
directly, and Application Integration runs two actions (purchase order, approver alert). Directing the whole flow from
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
- The approver is whoever confirms in the ADK prompt. Identity and authority are **not verified**; add IAM or role checks for real use. The notification tells the approver role, but the platform does not enforce who clicks.
- The approved amount is committed up front; there is no automatic release if a PO is later cancelled (the ledger supports RELEASE entries, but no tool writes them yet).
- The guard compares cumulative PO totals with the approved amount per request; it does not detect duplicate POs for the same item.
- Rejected or declined requests release stock reservations only when the root agent asks the inventory agent to; this depends on the model following the instruction.
- A single flat tier table applies to every campaign and approver.
- Step order is enforced by prompts, so a live model can deviate. The hard guarantees are in code: no PO without a covering approval, no approval beyond remaining budget.
- Two users working in parallel against the same BigQuery data can both see the same free stock before either reserves; there is no locking.
- The Application Integration workflows are defined by you; the PO guard requires the documented variable names.

**Verified** on a real Google Cloud project: the BigQuery setup (dataset, tables, views, seed data, approver rows), creating and
publishing the Application Integration workflow, executing both triggers (`setup_application_integration.py --test`: the PO trigger
returned a PO number, the notify trigger completed), reading the data back (`verify_setup.py`), and ADK building the tools
`create_purchase_order` and `notify_approver` from the integration.

**Not yet confirmed:** that the approval email reaches an inbox (check the test email), a full agent run with Gemini on your
project, and the in-chat Confirm / Reject pause. Unit tests cover the tools, tiered policy, purchase-order guard (including
one email call per approver address), audit trail, the setup scripts and the BigQuery repository (stub client, SQL syntax).
See DEMO_RUN.md section 13.

## 9. Production notes

- **Deployment target: Vertex AI Agent Engine.** `scripts/deploy_agent_engine.py` deploys the agent; Agent Engine provides the managed sessions, so a pending human approval survives restarts. The deployed agent runs as its own identity, which needs BigQuery, Application Integration and Vertex AI roles (DEMO_RUN.md section 14). With no `adk web` UI there, the approval request is returned to the client; `scripts/query_agent_engine.py` shows it and sends the Confirm / Reject back, and Gemini Enterprise can provide the chat UI.
- Run the agent under a service account with only the roles it needs (BigQuery Data Editor + Job User, Application Integration Invoker, Vertex AI User).
- Send the audit table to Cloud Logging or a Looker dashboard; add alerting on `po_blocked` events.
- Add Model Armor for prompt safety and IAM-based approver checks, as shown in the architecture slide.
- Set `CAMPAIGN_MODEL` to your standard Gemini model (default `gemini-2.5-flash`).
