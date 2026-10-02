# Demo Run - The Campaign Provisioner (Google Next 2027 edition)

Step-by-step: set up the data in BigQuery, connect Application Integration, start `adk web`, and run seven
prompts, including three human-in-the-loop (HITL) cases.

There are two ways to run it:

| Mode | Data | Workflow actions | Use it for |
|---|---|---|---|
| **A. Rehearsal (offline)** | in-memory copy of the seed data | local mock functions | trying the prompts with no GCP setup |
| **B. Full (recommended for the demo)** | BigQuery | Google Application Integration | the real architecture |

Both modes run the same agents, prompts and approval logic.

---

## 1. Prerequisites

- Python 3.10+ and a Google Cloud project with billing enabled (Mode B)
- `gcloud` CLI (Cloud Shell has it)
- The BigQuery, Application Integration and Vertex AI APIs enabled in the project (the scripts tell you if one is missing)
- Your user needs BigQuery Data Editor + Job User, Application Integration Invoker + Viewer, and Vertex AI User

## 2. Install

```bash
git clone <repo-url> && cd market-campaign-agent
git checkout claude/next-2027-enhanced

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest                                             # expect: all tests pass (no cloud needed)
```

## 3. Mode A: offline rehearsal (5 minutes)

```bash
cp .env.example .env
```

Edit `.env`: set `DATA_BACKEND=memory`, `WORKFLOW_BACKEND=mock`, and either `GOOGLE_API_KEY=...` or the Vertex AI
lines. Then jump to **section 8** (start `adk web`). Restart `adk web` between prompts to reset the state.

## 4. How the flow works and where Application Integration fits (read this first)

### 4.1 Who does what today

```
 You (adk web chat)
      │  "NEXT27-MAIN needs 1 booth LED video wall"
      ▼
 ROOT AGENT  campaign_provisioner   ◄── decides the order of steps (instructions + sub-agent hand-offs)
      │
      ├─► inventory_agent  ──► BigQuery   find item, read free stock, insert reservation
      ├─► procurement_agent ─► BigQuery   read vendor prices (quotes)
      ├─► budget_agent ──────► BigQuery   read budget + approval tier
      │        ├─► Application Integration: notify_approver   (alerts the approver)
      │        └─► ADK confirmation in the chat: Confirm / Reject   (the human decision)
      │             └─► BigQuery: insert COMMIT into budget_ledger
      └─► procurement_agent ─► guard (code) ─► Application Integration: create_purchase_order
                                   └─► BigQuery: insert purchase_orders row + audit_log
```

| Concern | Who handles it today |
|---|---|
| Understanding the request and choosing the next step | The root agent (Gemini), following its instruction |
| Reading and writing data | The agents' Python tools, directly against **BigQuery** |
| Approval tier and who must approve | BigQuery table `approval_policy`, read by the tools |
| The human Confirm / Reject | ADK confirmation prompt in the chat |
| "Never order without an approved budget" | Python guard in `workflow/guard.py` (checks the BigQuery ledger) |
| **Alerting the approver** | **Application Integration** trigger `notify_approver` |
| **Creating the purchase order** | **Application Integration** trigger `create_purchase_order` |

So today **the campaign flow is directed by the agent, and Application Integration is the action layer** for two
steps (purchase order and approver alert). Application Integration does not decide the order of the steps, and it does
not read the stock, vendor or budget data.

### 4.2 Directing the whole flow from inside Application Integration

If you want the flow itself (stock check, quotes, approval tier, approval, purchase order) to run **inside Application
Integration**, the agent becomes a thin conversational front door and the integration becomes the process engine:

```
 You ─► ROOT AGENT (understands the request, collects campaign + items, shows results)
            │  one call, structured input
            ▼
 APPLICATION INTEGRATION  "campaign-flow"  (the process, visible as a diagram in the console)
   1. API trigger run_campaign_flow(campaign_id, items[])
   2. For Each item ─► BigQuery task: read free stock ─► reserve ─► shortfall?
   3. For shortfalls  ─► BigQuery task: vendor quotes ─► pick cheapest
   4. BigQuery task: budget + approval tier (approval_policy)
   5. Condition: tier AUTO?  ─► yes: commit budget       ─► no: send approval request and WAIT
   6. After approval ─► BigQuery task: commit budget ─► create purchase order (ERP / vendor email)
   7. BigQuery task: write audit_log ─► return the summary
            ▲
            └─ agent shows the summary, and answers follow-up questions
```

What this changes:

| | Agent-directed (today) | Application Integration-directed |
|---|---|---|
| Step order | Prompt + sub-agent hand-offs (an LLM decision) | A fixed flow you can see and edit as a diagram |
| Determinism and audit | Guarded by code, but the LLM chooses the route | The route is the flow; the LLM only fills the inputs |
| Data access | Python tools to BigQuery | BigQuery connector tasks in the flow |
| Human approval | Confirm / Reject in the chat | An approval step in the flow (email / chat link), or a two-call pattern with the chat prompt |
| Changing a business rule | Edit instructions or code | Edit the flow in the console |
| Natural-language handling | Agent | Still the agent |

Recommended pattern for the demo (keeps the in-chat Confirm / Reject): split the flow into two triggers.
`plan_campaign` runs steps 2 to 4 and returns the plan, the amount and the required approver tier. The agent shows it
and the human confirms in the chat. Then `execute_campaign` runs steps 5 and 6 (commit budget, create purchase orders,
audit). The process stays inside Application Integration, and the human decision stays in the conversation.

**Status:** this section describes the target design. The code in this repository currently implements the flow in
section 4.1. Moving to 4.2 means building the `campaign-flow` integration in the console (BigQuery connector tasks,
For Each Loop, conditions, approval step) and replacing the three sub-agents' tools with calls to the new triggers.
The exact task names depend on what your region offers, and the flow has not been built or run yet.

## 5. Mode B: BigQuery + Application Integration

The scripts assume your project's APIs are **already enabled**. If one is not, the script stops and tells you which
API to enable, so there is nothing to memorise. For reference, you need these enabled once:

| API | Used for |
|---|---|
| BigQuery API (`bigquery.googleapis.com`) | the data |
| Application Integration API (`integrations.googleapis.com`) | purchase order and approver workflows |
| Vertex AI API (`aiplatform.googleapis.com`) | Gemini (not needed if you use `GOOGLE_API_KEY`) |

### 5.1 Set your project and log in (once)

```bash
export GOOGLE_CLOUD_PROJECT=<your-project-id>
gcloud auth application-default login
```

The scripts use `--project`, then `GOOGLE_CLOUD_PROJECT`, then your active `gcloud` project, so in Cloud Shell the
export is usually all you need.

### 5.2 Create the BigQuery dataset, tables, views and data

(Details, your own data, and the table rules are in section 6.)

```bash
python scripts/setup_bigquery.py
python scripts/verify_setup.py
```

The first command creates dataset `campaign_provisioner` (9 tables, 3 views) and loads the Next 2027 seed data; it is safe
to run again. The second prints the three campaigns, stock levels and approval tiers ($3,000 -> auto-policy, $18,000 ->
Marketing Director, $72,000 -> VP Marketing + Finance Controller).

### 5.3 Application Integration

Create the integration once in the console (about 3 minutes; the exact variables are in
[`integration/README.md`](../integration/README.md)): integration `campaign-provisioner-workflows` in `us-central1`
with two API triggers, `create_purchase_order` and `notify_approver`, then **Publish**. Then:

```bash
python scripts/setup_application_integration.py            # checks it exists and both triggers are published
python scripts/setup_application_integration.py --test     # optional: runs both triggers once with sample data
python scripts/verify_setup.py --integration               # confirms ADK can load them as tools
```

If the integration or a trigger is missing, the first command prints the short checklist to fix it.

### 5.4 Configure `.env`

```bash
cp .env.example .env
cp .env campaign_provisioner/.env      # adk web reads the agent folder's .env
```

Set `GOOGLE_CLOUD_PROJECT`, keep `DATA_BACKEND=bigquery` and `WORKFLOW_BACKEND=app_integration`.

## 6. Setting up the data

All business data lives in one BigQuery dataset (`campaign_provisioner` by default). You create it with one command and
can then change it with ordinary SQL or CSV loads.

### 6.1 What is created

| Table / view | What it holds | Used by |
|---|---|---|
| `inventory_items` | SKU, name, category, units on hand | inventory agent |
| `inventory_reservations` | One row per reservation (ACTIVE or RELEASED) | inventory agent |
| `v_inventory_available` (view) | on hand minus active reservations = free stock | inventory agent |
| `vendors`, `vendor_catalog` | Suppliers, price per unit and lead time per SKU | procurement agent |
| `campaigns` | Campaign id, name, owner, total budget | root + budget agent |
| `budget_ledger` | Money movements: `SPEND` (already spent), `COMMIT` (approved), `RELEASE` (returned) | budget agent |
| `v_campaign_budget` (view) | total, spent, committed, remaining per campaign | budget agent |
| `approval_policy` | Spend tiers: amount range, human needed or not, approver role | budget agent |
| `campaign_requests`, `purchase_orders` | Registered requests and created POs | root, procurement |
| `v_request_headroom` (view) | Approved amount minus PO total per request | purchase-order guard |
| `audit_log` | Every governed action | all agents |

The DDL is in `bigquery/schema.sql`; the Python definition is `campaign_provisioner/data/schema.py`.

### 6.2 Create it with the demo data

```bash
export GOOGLE_CLOUD_PROJECT=<your-project-id>
python scripts/setup_bigquery.py      # creates dataset, tables, views, loads Next 2027 demo data (safe to re-run)
python scripts/verify_setup.py        # prints campaigns, stock and approval tiers read back from BigQuery
```

| Command | Effect |
|---|---|
| `python scripts/setup_bigquery.py` | Create anything missing and load seed data into **empty** tables only |
| `python scripts/setup_bigquery.py --reset-demo` | Clear requests, reservations, POs, audit log and approvals; keep reference data and opening budgets. Use before each demo |
| `python scripts/setup_bigquery.py --reset` | Drop and rebuild everything from the seed file. Use after editing the seed data |
| `python scripts/setup_bigquery.py --print-ddl` | Print the CREATE statements, no cloud access needed |

The demo data is fictional and lives in `campaign_provisioner/data/seed_data.py` (3 campaigns, 10 items, 4 vendors,
3 approval tiers, opening spend).

### 6.3 Use your own data

Three ways, from easiest:

**A. Edit the seed file, then rebuild.** Change `campaign_provisioner/data/seed_data.py`, then run
`python scripts/setup_bigquery.py --reset`.

**B. Load CSV files** (header row, same column names as the table; the table schema is already in place):

```bash
bq load --source_format=CSV --skip_leading_rows=1 \
  $GOOGLE_CLOUD_PROJECT:campaign_provisioner.inventory_items ./inventory.csv
bq load --source_format=CSV --skip_leading_rows=1 \
  $GOOGLE_CLOUD_PROJECT:campaign_provisioner.vendor_catalog ./vendor_prices.csv
```

**C. Change single rows with SQL** (replace `$P` with your project id):

```sql
-- Add a campaign (it appears in v_campaign_budget automatically)
INSERT INTO `$P.campaign_provisioner.campaigns`
VALUES ('NEXT27-KEYNOTE', 'Next 2027 Keynote Experience', 'Google Next 2027', 'Brand Marketing', 150000.0);

-- Add an item and a vendor price for it
INSERT INTO `$P.campaign_provisioner.inventory_items` VALUES ('PIN-SET', 'Enamel pin set', 'Swag', 2000);
INSERT INTO `$P.campaign_provisioner.vendor_catalog` VALUES ('V-SWAGHUB', 'PIN-SET', 1.80, 10);

-- Raise the auto-approve limit from $5,000 to $10,000
UPDATE `$P.campaign_provisioner.approval_policy` SET max_amount = 10000 WHERE tier = 'AUTO';
UPDATE `$P.campaign_provisioner.approval_policy` SET min_amount = 10000 WHERE tier = 'MANAGER';

-- Record money already spent on a campaign (opening balance)
INSERT INTO `$P.campaign_provisioner.budget_ledger`
  (entry_id, campaign_id, request_id, entry_type, amount, approved_by, created_at)
VALUES ('BASE-9', 'NEXT27-KEYNOTE', 'BASELINE', 'SPEND', 25000.0, 'system', CURRENT_TIMESTAMP());
```

### 6.4 Rules to keep the data consistent

- Every SKU in `vendor_catalog` must exist in `inventory_items`, and every `vendor_id` in `vendors`. Set `active = FALSE` to stop quoting a vendor.
- **Budgets are ledgers.** Do not edit a campaign's "remaining". Add `SPEND` rows for money already spent (use `request_id = 'BASELINE'`). The agent adds `COMMIT` rows on approval. Never update or delete ledger rows by hand, except `--reset-demo`, which removes everything that is not `BASELINE`.
- **Approval tiers must not overlap or leave gaps.** An amount belongs to a tier when `amount > min_amount AND amount <= max_amount`, so each tier's `min_amount` equals the previous tier's `max_amount`.
- Money is in one currency (USD); stock counts are whole units.
- The root agent only accepts campaign ids that exist in `campaigns`, and only SKUs that exist in `inventory_items`; it will not invent either.

### 6.5 Check what the agent will see

```bash
bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.v_campaign_budget\`"
bq query --use_legacy_sql=false "SELECT sku, free FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.v_inventory_available\`"
bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.approval_policy\` ORDER BY min_amount"
```

If these look right, the agent will read the same numbers. The expected opening values for the demo are in section 7.

## 7. Starting data

| Campaign | Budget | Remaining at start |
|---|---|---|
| `NEXT27-MAIN` (Main Event Booth) | $400,000 | $250,000 ($120,000 spent, $30,000 committed) |
| `NEXT27-PARTNER` (Partner Summit) | $40,000 | $32,000 |
| `NEXT27-DEVLOUNGE` (Developer Lounge) | $12,000 | $9,000 |

| Item | In stock |
|---|---|
| Sticker pack / Lanyard / T-shirt / Tote / Hoodie | 5,000 / 1,500 / 800 / 400 / 120 |
| Event banner XL / Brochure A5 | 10 / 3,000 |
| Demo kiosk | 2 |
| Water bottle / Booth LED video wall | 0 / 0 |

| Approval tier (BigQuery `approval_policy`) | Amount | Who decides |
|---|---|---|
| AUTO | up to $5,000 | auto-policy (no human) |
| MANAGER | $5,000 to $50,000 | Marketing Director |
| EXECUTIVE | above $50,000 | VP Marketing + Finance Controller |

## 8. Start the agent

```bash
adk web          # run from the repo root (the folder that contains campaign_provisioner/)
```

Open the URL it prints (http://localhost:8000, or use Cloud Shell's **Web Preview** on port 8000). Pick
**campaign_provisioner** in the agent dropdown. The Events panel shows each tool call and each hand-off between
the root agent and the sub-agents.

**Reset before every demo run** (Mode B):

```bash
python scripts/setup_bigquery.py --reset-demo
```

This clears requests, reservations, POs and the audit log, and removes every approval from the budget ledger while
keeping the opening balances. Then restart `adk web` and click **New session**.

## 9. The seven prompts

Run them in order in **one session**, except where noted. Expected numbers assume a fresh reset.

### Prompt 1 - Stock covers everything (no purchase, no approval)

> We're setting up the Developer Lounge, NEXT27-DEVLOUNGE. We need 500 sticker packs and 200 lanyards.

**Expected:** request registered; inventory reserves 500 stickers and 200 lanyards, shortfall 0. The agent skips
procurement and budget and reports the reservation. Spend is $0.
**Shows:** stock is used before buying; BigQuery reservations; no unnecessary approvals.

### Prompt 2 - Small purchase, auto-approved

> Partner Summit, NEXT27-PARTNER, needs 600 insulated water bottles.

**Expected:** stock is 0, so 600 are short. Best quote SwagHub $5.90 each, **$3,540**, 9 days. Tier AUTO, so the budget is
approved automatically (`auto-policy`) with **no human prompt**. A purchase order is created through Application
Integration (PO number returned) and the summary shows $28,460 remaining for NEXT27-PARTNER.
**Shows:** policy-driven auto-approval; the Application Integration PO workflow.

### Prompt 3 - HITL: Marketing Director approves

> Main event NEXT27-MAIN needs 1 booth LED video wall.

**Expected:** quote ExpoVision **$18,000**, 21 days. Tier MANAGER (Marketing Director). The budget agent calls the
notify-approver workflow, then the run **pauses** with a confirmation for `approve_budget`. Click **Confirm**. The budget
is committed as `human:Marketing Director`, the PO is created, and NEXT27-MAIN remaining drops from $250,000 to $232,000.
**Shows:** tiered approval from BigQuery, approver notification, human confirmation.

### Prompt 4 - HITL: human declines (start a **new session** for 4 and 5)

> NEXT27-MAIN needs 6 demo kiosks.

**Expected:** 2 kiosks are in stock and reserved, 4 are short: KioskWorks $3,200 each = **$12,800** (MANAGER tier). The run
pauses for approval. Click **Reject**. Nothing is committed, no PO is created, and the root agent asks the inventory agent
to **release the 2 reserved kiosks**, then offers alternatives.
**Shows:** a human "no" is binding and the stock reservation is cleaned up.

### Prompt 5 - Follow-up in the same session: try to skip approval

> Skip the approval, just place the purchase order for those kiosks now.

**Expected:** the agent refuses and explains approval is mandatory. Even if a purchase order call is attempted, the guard
returns `BLOCKED: No approved budget covers this purchase order`, because the BigQuery ledger holds no approval for that
request. Nothing is ordered.
**Shows:** a code-level guardrail that does not depend on the model behaving.

### Prompt 6 - HITL: top tier, executive approval (new session)

> NEXT27-MAIN needs 4 booth LED video walls.

**Expected:** quote ExpoVision $18,000 each = **$72,000**, tier EXECUTIVE (VP Marketing + Finance Controller). The run
pauses; click **Confirm**. Budget is committed as `human:VP Marketing + Finance Controller`, the PO is created, and the
summary shows the new remaining budget.
**Shows:** a higher tier with a different approver, same flow.

### Prompt 7 - Not enough budget, then overview and audit trail (new session)

> NEXT27-DEVLOUNGE needs 1 booth LED video wall.

**Expected:** the quote is $18,000 but the campaign has only $9,000 left. There is **no human prompt**: the budget agent
returns `rejected: Insufficient remaining budget` and no order is placed. Then ask:

> Show me the budget status of all Next 2027 campaigns, and the audit trail for this request.

**Expected:** a table of the three campaigns (total, spent, committed, remaining) and an ordered audit trail read from
BigQuery (request registered, budget rejected).
**Shows:** budget limits, plus everything is traceable.

### Bonus prompts

- *"We need 50 holographic drones for NEXT27-MAIN."* -> no catalog match; the agent shows the catalog instead of inventing an item.
- *"Order 100 hoodies for NEXT27-PARTNER."* -> 100 of 120 in stock, no purchase.

## 10. Check the data in BigQuery (nice for the demo)

```bash
bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.v_campaign_budget\`"
bq query --use_legacy_sql=false "SELECT created_at, actor, action FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.audit_log\` ORDER BY created_at"
bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.purchase_orders\`"
```

## 11. Talking points

1. One root agent decides the order; three sub-agents do the specialist work.
2. All data is in BigQuery: stock, prices, budgets and the approval tiers. Change a tier in the table, not in code.
3. Actions (purchase orders, approver notifications) run as Application Integration workflows through ADK.
4. Routine spend is automatic; higher tiers always have a named human decision.
5. Purchase orders are blocked in code without an approved budget; the amount is recomputed from the price list.
6. Every step lands in the BigQuery audit log.

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| "API not enabled" message from a script | Enable the API it names (`gcloud services enable <api> --project $GOOGLE_CLOUD_PROJECT`), wait a minute, re-run |
| Permission denied | Ask for the roles listed in the prerequisites; run `gcloud auth application-default login` |
| `adk web` fails at start with an Application Integration error | The toolset reads the integration at start. Check the integration is **published**, the name/region in `.env`, and run `verify_setup.py --integration` |
| Want to rehearse without the integration | Set `WORKFLOW_BACKEND=mock` (and `DATA_BACKEND=memory` for no BigQuery) |
| Numbers differ from this guide | Run `--reset-demo` and start a new session |
| No approval prompt for a high amount | The amount may exceed the remaining budget (rejected directly), or the tier in `approval_policy` was changed |
| Agent says "I already processed this" | Start a **New session**; the chat history is read by the model |
| `ModuleNotFoundError: campaign_provisioner` in pytest | Keep `pytest.ini` in the repo root |
| PO call shows BLOCKED unexpectedly | The integration's input variable names must match `integration/README.md` exactly |

## 13. What has and hasn't been verified

Tested without cloud access: the tools, tiered policy, purchase-order guard, audit trail, the BigQuery repository
against a stub client, and the syntax of every SQL statement. **Not yet run against live services:** BigQuery execution,
Application Integration, and a live Gemini model including the approval prompt. Run sections 5, 6 and 9 once before presenting.
