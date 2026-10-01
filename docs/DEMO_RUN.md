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
- Your user or service account needs: BigQuery Data Editor, BigQuery Job User, Integrations Invoker/Viewer, Vertex AI User (the script below grants them)

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
lines. Then jump to **section 6** (start `adk web`). Restart `adk web` between prompts to reset the state.

## 4. Mode B: BigQuery + Application Integration

### 4.1 Google Cloud setup

```bash
gcloud auth login
gcloud auth application-default login
export PROJECT_ID=<your-project-id>
export PRINCIPAL="user:<your-email>"
./scripts/setup_gcp.sh            # enables APIs and grants roles
```

### 4.2 Create the BigQuery dataset, tables, views and data

```bash
export GOOGLE_CLOUD_PROJECT=$PROJECT_ID
python scripts/setup_bigquery.py --project $PROJECT_ID
```

This creates dataset `campaign_provisioner` with 9 tables, 3 views and the Next 2027 seed data
(see `bigquery/schema.sql` for the DDL). Check it:

```bash
python scripts/verify_setup.py
```

Expected: three campaigns, stock levels and three approval tiers ($3,000 -> auto-policy, $18,000 -> Marketing Director,
$72,000 -> VP Marketing + Finance Controller).

### 4.3 Build the Application Integration workflow

Follow [`integration/README.md`](../integration/README.md): one integration `campaign-provisioner-workflows` with two
API triggers, `create_purchase_order` and `notify_approver`. Then confirm ADK can see them:

```bash
python scripts/verify_setup.py --integration
```

### 4.4 Configure `.env`

```bash
cp .env.example .env
cp .env campaign_provisioner/.env      # adk web reads the agent folder's .env
```

Edit `GOOGLE_CLOUD_PROJECT`, keep `DATA_BACKEND=bigquery` and `WORKFLOW_BACKEND=app_integration`.

## 5. Starting data

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

## 6. Start the agent

```bash
adk web          # run from the repo root (the folder that contains campaign_provisioner/)
```

Open the URL it prints (http://localhost:8000, or use Cloud Shell's **Web Preview** on port 8000). Pick
**campaign_provisioner** in the agent dropdown. The Events panel shows each tool call and each hand-off between
the root agent and the sub-agents.

**Reset before every demo run** (Mode B):

```bash
python scripts/setup_bigquery.py --project $PROJECT_ID --reset-demo
```

This clears requests, reservations, POs and the audit log, and removes every approval from the budget ledger while
keeping the opening balances. Then restart `adk web` and click **New session**.

## 7. The seven prompts

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

## 8. Check the data in BigQuery (nice for the demo)

```bash
bq query --use_legacy_sql=false "SELECT * FROM \`$PROJECT_ID.campaign_provisioner.v_campaign_budget\`"
bq query --use_legacy_sql=false "SELECT created_at, actor, action FROM \`$PROJECT_ID.campaign_provisioner.audit_log\` ORDER BY created_at"
bq query --use_legacy_sql=false "SELECT * FROM \`$PROJECT_ID.campaign_provisioner.purchase_orders\`"
```

## 9. Talking points

1. One root agent decides the order; three sub-agents do the specialist work.
2. All data is in BigQuery: stock, prices, budgets and the approval tiers. Change a tier in the table, not in code.
3. Actions (purchase orders, approver notifications) run as Application Integration workflows through ADK.
4. Routine spend is automatic; higher tiers always have a named human decision.
5. Purchase orders are blocked in code without an approved budget; the amount is recomputed from the price list.
6. Every step lands in the BigQuery audit log.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `403` / permission denied on BigQuery | Re-run `setup_gcp.sh`; run `gcloud auth application-default login` |
| `adk web` fails at start with an Application Integration error | The toolset reads the integration at start. Check the integration is **published**, the name/region in `.env`, and run `verify_setup.py --integration` |
| Want to rehearse without the integration | Set `WORKFLOW_BACKEND=mock` (and `DATA_BACKEND=memory` for no BigQuery) |
| Numbers differ from this guide | Run `--reset-demo` and start a new session |
| No approval prompt for a high amount | The amount may exceed the remaining budget (rejected directly), or the tier in `approval_policy` was changed |
| Agent says "I already processed this" | Start a **New session**; the chat history is read by the model |
| `ModuleNotFoundError: campaign_provisioner` in pytest | Keep `pytest.ini` in the repo root |
| PO call shows BLOCKED unexpectedly | The integration's input variable names must match `integration/README.md` exactly |

## 11. What has and hasn't been verified

Tested without cloud access: the tools, tiered policy, purchase-order guard, audit trail, the BigQuery repository
against a stub client, and the syntax of every SQL statement. **Not yet run against live services:** BigQuery execution,
Application Integration, and a live Gemini model including the approval prompt. Run sections 4 and 7 once before presenting.
