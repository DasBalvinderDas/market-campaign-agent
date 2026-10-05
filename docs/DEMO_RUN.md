# Demo Run - The Campaign Provisioner (Google Next 2027 edition)

Step-by-step: set up the data in BigQuery, connect Application Integration, start `adk web`, and run
the test prompts for the Google Next 2027 campaign, with the human-in-the-loop (HITL) cases highlighted.

It runs on your real Google Cloud project: data in BigQuery, workflow actions in Application Integration, Gemini
for the agent. Everything is configured through `.env` (section 3), which the setup script fills in for you.

---

## Setup at a glance (start here)

```
 1. Get the code        git clone -b claude/next-2027-enhanced https://github.com/dasbalvinderdas/market-campaign-agent.git
        │
 2. Install             python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
        │               pytest                       <- proves the code works, no cloud needed
        │
 3. Log in             export GOOGLE_CLOUD_PROJECT=<project>  +  gcloud auth application-default login
        │                                                                                          │
 4. One-command setup   python scripts/setup_all.py --approver-email "you@example.com"             │
        │                 ├─ checks APIs + permissions, lists anything missing, changes nothing yet  │
        │                 ├─ BigQuery: dataset, tables, views, demo data, approver emails            │
        │                 ├─ Application Integration: creates + publishes the workflow               │
        │                 └─ writes the .env file                                                    │
        │                                                                                          │
 5. Verify              python scripts/verify_setup.py --integration                               │
        │                                                                                          │
 6. Start the agent     adk web   ◄─────────────────────────────────────────────────────────────────┘
        │
 7. Run the prompts     section 9 (test prompts; 3 + 2 of them stop for a human approval)
        │
 8. Reset for next run  python scripts/setup_bigquery.py --reset-demo
        │
 9. Deploy (final)      source scripts/env_setup.sh
        │               python scripts/deploy_agent_engine.py       -> Vertex AI Agent Engine   (section 14)
```

| Step | Command | You should see |
|---|---|---|
| 2 | `pytest` | all tests pass |
| 4 | `python scripts/setup_all.py ...` | `BigQuery data: OK`, `Application Integration: OK`, and the line `wrote .env ...` |
| 5 | `python scripts/verify_setup.py --integration` | 3 campaigns, stock, 3 approval tiers, the approver emails, then `Application Integration OK` |
| 6 | `adk web` | a URL (http://localhost:8000); pick **campaign_provisioner** |
| 7 | the first prompt in section 9 | the agent reserves stock, quotes, and finishes without asking for approval |

**If step 4 prints a message instead of OK:** it names the API to enable or the role to ask for, nothing is half-done, and
you simply run the same command again after fixing it. Finished parts are skipped.

**Where each part of the flow gets its data** (so you know what is being set up):

| What the agent needs | Comes from | Set up by |
|---|---|---|
| Stock, vendor prices, budgets, approval tiers | BigQuery tables and views | `setup_all.py` (step 4) |
| Who is emailed for approval | BigQuery table `approvers` | `--approver-email` in step 4 |
| Purchase order + approval email actions | Application Integration workflow | `setup_all.py` (step 4) |
| The human Confirm / Reject | the `adk web` chat | nothing to set up |
| Project, dataset, regions, approver emails | `.env` | written by step 4 |

The sections that follow give the detail for each step. Step 9, deploying to Vertex AI Agent Engine, is section 14.

---

## 1. Prerequisites

- Python 3.10+ and a Google Cloud project with billing enabled
- `gcloud` CLI (Cloud Shell has it)
- The BigQuery, Application Integration and Vertex AI APIs enabled in the project (the scripts tell you if one is missing)
- Your user needs BigQuery Data Editor + Job User, Application Integration Editor (or Admin) + Invoker + Viewer, and Vertex AI User (the setup script checks the BigQuery ones up front)

## 2. Install

```bash
git clone -b claude/next-2027-enhanced https://github.com/dasbalvinderdas/market-campaign-agent.git && cd market-campaign-agent
git checkout claude/next-2027-enhanced

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest                                             # expect: all tests pass (no cloud needed)
```

## 3. Configure `.env` (real environment)

`python scripts/setup_all.py` (section 5) creates one `.env` file (in the repo root) from `.env.example` and fills in the
project, dataset, region and approver emails. You only check the Gemini lines. There is just one file: `adk web` looks for
`.env` in the agent folder and then in the folders above it, so the repo-root file is found. (If an old
`campaign_provisioner/.env` exists from an earlier setup, delete it or keep it identical, because the one next to the agent wins.) These are all the entries:

| Entry | Meaning | Example |
|---|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | use Gemini on Vertex AI | `TRUE` |
| `GOOGLE_CLOUD_PROJECT` | your Google Cloud project id | `my-project` |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI location | `us-central1` |
| `GOOGLE_API_KEY` | only if you use a Gemini API key instead of Vertex AI | `...` |
| `CAMPAIGN_MODEL` | optional, Gemini model | `gemini-2.5-flash` |
| `BQ_DATASET` / `BQ_LOCATION` | BigQuery dataset and location | `campaign_provisioner` / `US` |
| `APP_INTEGRATION_NAME` / `APP_INTEGRATION_LOCATION` | the Application Integration workflow | `campaign-provisioner-workflows` / `us-central1` |
| `APPROVER_EMAILS` | who is emailed for approvals (`Role=a@x.com,b@x.com;Role 2=c@x.com`) | `Marketing Director=md@example.com` |

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
      ├─► budget_agent ──────► BigQuery   read budget + approval tier + approver emails
      │        └─► Application Integration: notify_approver   (EMAILS the approver), then hands back
      ├─► ROOT calls approve_budget  ──►  ADK confirmation in the chat: Confirm / Reject   (the human decision)
      │        └─► BigQuery: insert COMMIT into budget_ledger
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
| Who gets the email | BigQuery table `approvers` (role -> emails), set at setup time; the guard fills it in, never the model |
| **Emailing the approver** | **Application Integration** trigger `notify_approver` (its Send Email task) |
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

### 4.3 Human approval inside Application Integration (default)

When the amount needs a person (above $5,000), the agent starts the Application Integration workflow **`request_approval`**.
Its native **Approval** task pauses the run and emails the approver(s) an approval request with **Approve** and **Reject**.
The approver decides on the Google-hosted approval page; nothing has to be deployed, and no public endpoint is needed.

```
 Agent (chat)                               Application Integration                        Approver
   │ builds the purchase plan from BigQuery, stores a PENDING approval (approval_requests)
   │ trigger request_approval ─────────────► Approval task: run SUSPENDED, email ─────────► Approve / Reject
   │ tells the user "approval requested", ends                                                   │
   │                                           APPROVED ─► decision = APPROVED  ◄───────────────┤
   │                                           REJECTED ─► decision = REJECTED  ◄───────────────┘
   │ user: "approval status of REQ-...?"  (get_approval_status reads the execution)
   │   APPROVED: commit budget, trigger create_purchase_order, PO + audit rows in BigQuery
   │   REJECTED: release the reserved stock;  still waiting: reports PENDING
```

| Question | Answer |
|---|---|
| Who is emailed? | The addresses given to `setup_application_integration.py --approver-email` (or `setup_all.py`), else `APPROVER_EMAILS`, else your gcloud account. They are part of the published integration version; to change them run `python scripts/setup_application_integration.py --approver-email "a@x.com" --republish`. |
| Does the approver need to log in? | The approval page is hosted by Google, so expect a Google sign-in for the address that received the email. A login-free link needs a public endpoint (the parked Cloud Run service, below). |
| Who decides the amount and the items? | Not the model. They are computed from BigQuery (stock shortfall x cheapest active vendor) when the approval is requested. |
| How does the flow continue after the click? | The click resolves the suspended execution and the workflow ends with `decision`. The next `get_approval_status` call reads it, then commits the budget and creates the purchase orders (or releases the stock). First reader wins, so asking twice never orders twice. |
| Can I check it in the console? | Yes: Application Integration > integration `campaign-provisioner-workflows` > Execution logs (suspended runs show the Approval task) and the BigQuery tables `approval_requests`, `purchase_orders`, `audit_log`. |
| Approval workflow settings unverified | The approval task was modelled on Google's published `sample_order_processing` sample; its exact behaviour was not run against a real project. If `--check-only` / the first approval misbehaves, send the error text. |

**Parked: signed links via Cloud Run.** Setting `APPROVAL_CHANNEL=email` (and deploying `scripts/deploy_approval_service.py`)
switches to emailed Approve / Reject links served by a public Cloud Run service with no login. It needs an organisation that allows
public Cloud Run endpoints, so it is not the default. **Chat:** `APPROVAL_CHANNEL=chat` asks Confirm / Reject in the chat (sections 9 and 14.5).

## 5. Set up BigQuery and Application Integration

### 5.0 The one-command setup

```bash
export GOOGLE_CLOUD_PROJECT=<your-project-id>
gcloud auth application-default login
python scripts/setup_all.py --approver-email "you@example.com"
```

That single command:

1. **Checks everything first** and reports all problems in one message: every API that is not enabled (with the
   `gcloud services enable ...` command) and any missing BigQuery permission (with the role to ask for).
2. Creates the **BigQuery** dataset, tables, views, demo data and the approver emails.
3. Creates and publishes the **Application Integration** workflow (purchase order + approver email).
4. Writes the `.env` file (project, dataset, locations, approver emails), keeping any other lines.

What you can configure:

| Setting | Flag | Default |
|---|---|---|
| Google Cloud project | `--project` | `GOOGLE_CLOUD_PROJECT`, else your active gcloud project |
| Who is emailed for approvals | `--approver-email "[ROLE=]a@x.com,b@x.com"` (repeat per role) | `APPROVER_EMAILS`, else your gcloud account |
| BigQuery dataset / location | `--dataset`, `--location` | `campaign_provisioner`, `US` |
| Application Integration region | `--region` | `us-central1` |
| Test email at the end | `--test` (sends one test email to `--test-email` or you) | off |
| Skip the email task | `--no-email` | email on |

Per-role example (the approval tiers use the roles "Marketing Director" and "VP Marketing + Finance Controller"):

```bash
python scripts/setup_all.py \
  --approver-email "Marketing Director=md@example.com,md2@example.com" \
  --approver-email "VP Marketing + Finance Controller=vp@example.com,controller@example.com"
```

Needed once in the project: the **BigQuery API** (`bigquery.googleapis.com`), the **Application Integration API**
(`integrations.googleapis.com`) and, for Gemini on Vertex AI, `aiplatform.googleapis.com`. You do not have to remember
them: if one is missing the script lists it and stops before changing anything. If one step fails (for example the
integration), the other still runs and the summary says which one needs attention; re-run after fixing it.

Change the approver emails later without touching the integration: re-run with `--approver-email ...`, or edit the
`approvers` table (section 6.5). The sections below describe each part separately.

### 5.1 Set your project and log in (once; only if you run the steps separately)

```bash
export GOOGLE_CLOUD_PROJECT=<your-project-id>
gcloud auth application-default login
```

The scripts use `--project`, then `GOOGLE_CLOUD_PROJECT`, then your active `gcloud` project, so in Cloud Shell the
export is usually all you need.

### 5.2 Create the BigQuery dataset, tables, views and data

(Details, your own data, and the table rules are in section 6.)

```bash
python scripts/setup_bigquery.py --approver-email "you@example.com"
python scripts/verify_setup.py
```

The first command creates dataset `campaign_provisioner` (9 tables, 3 views) and loads the Next 2027 seed data; it is safe
to run again. The second prints the three campaigns, stock levels and approval tiers ($3,000 -> auto-policy, $18,000 ->
Marketing Director, $72,000 -> VP Marketing + Finance Controller).

### 5.3 Application Integration

One command creates and publishes the integration (`campaign-provisioner-workflows` in `us-central1`, two API triggers:
`create_purchase_order` and `notify_approver`) through the Application Integration API:

```bash
python scripts/setup_application_integration.py            # creates + publishes if missing, safe to re-run
python scripts/setup_application_integration.py --test     # optional: runs both triggers once with sample data
python scripts/verify_setup.py --integration               # confirms ADK can load them as tools
```

Like the BigQuery script it uses your project id automatically, assumes the APIs are enabled, and tells you which API to
enable if one is missing. Other options: `--check-only` (change nothing) and `--provision-region` (one-time, only if the
script says Application Integration has not been used in this region yet).

`create_purchase_order` returns `po_number` (`PO-<request id>-<sku>`) and an execution id. `notify_approver` builds the
message, **sends an email** to the approvers and returns `status = NOTIFIED`. The recipients are not stored in the
integration: the agent passes them in from the BigQuery `approvers` table, so changing an address needs no integration
change. `--test` sends one real test email (to `--test-email`, default your gcloud account). Details and the manual alternative: [`integration/README.md`](../integration/README.md).

### 5.3b Service account (optional but recommended)

If you have a service account with BigQuery and Application Integration access, set it once and the deployed agent runs as it:

```bash
source scripts/env_setup.sh --service-account app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com
# or add this line to .env:  AGENT_SERVICE_ACCOUNT=app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com
```

Approvals use Application Integration (section 4.3), so no extra service is needed. (The parked Cloud Run link service is deployed
with `python scripts/deploy_approval_service.py` and `APPROVAL_CHANNEL=email`; it needs a public Cloud Run endpoint.)

### 5.4 Configure `.env`

```bash
cp .env.example .env      # only if you are not using setup_all.py; edit the values
```

Set `GOOGLE_CLOUD_PROJECT` (the setup script already did, see section 3 for the other entries).

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
| `approvers` | Role -> email addresses to notify (set by the setup script, editable with SQL) | budget agent (notify step) |
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

### 6.5 Approver emails

The `approvers` table maps each approver role to the addresses that receive the approval email. It is filled by the
setup script from `--approver-email`, else `APPROVER_EMAILS`, else your gcloud account. To change it later:

```sql
-- add an address
INSERT INTO `$P.campaign_provisioner.approvers` VALUES ('Marketing Director', 'new.person@example.com', TRUE);
-- stop notifying someone
UPDATE `$P.campaign_provisioner.approvers` SET active = FALSE WHERE email = 'old.person@example.com';
```

Roles must match `approval_policy.approver_role` exactly. If a role has no active address, the agent continues, the
approver can still Confirm in the chat, and the agent tells the user that no email was sent (also written to the audit
log as `approver_email_skipped_no_recipients`). Notes: `--reset` of the BigQuery script recreates this table (pass
`--approver-email` again); `--reset-demo` leaves it alone. The model never supplies email addresses: the platform reads
them from this table.

### 6.6 Check what the agent will see

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

**Reset before every demo run:**

```bash
python scripts/setup_bigquery.py --reset-demo
```

This clears requests, reservations, POs and the audit log, and removes every approval from the budget ledger while
keeping the opening balances. Then restart `adk web` and click **New session**.

## 9. The test prompts (Google Next 2027), with the human-in-the-loop cases highlighted

Run them in order, in **one session**, except where a prompt says **new session**. The expected numbers assume a fresh
reset (section 8).

> **HUMAN-IN-THE-LOOP (HITL) legend.** Prompts marked **HITL** make the agent **stop and wait for a person**. You are the
> person: the run pauses, a confirmation request for `approve_budget` appears in the chat showing the request, campaign,
> amount and justification, and you choose **Confirm** or **Reject**. Nothing is committed and no purchase order exists until
> you decide. Which role "you" are playing, and who got the email, depends on the amount (the tier).

| # | Case | Campaign | Total | Human decision |
|---|---|---|---|---|
| 1 | Everything in stock, multi-item | NEXT27-DEVLOUNGE | $0 | none needed |
| 2 | Stock plus purchase, small total | NEXT27-PARTNER | $4,290 | none (auto-policy) |
| **3** | **HITL: Marketing Director approves** | NEXT27-MAIN | $18,000 | **Confirm** |
| **4** | **HITL: human declines** (**new session**) | NEXT27-MAIN | $12,800 | **Reject** |
| 5 | Try to skip the approval (same session as 4) | NEXT27-MAIN | | blocked by code |
| **6** | **HITL: top tier, VP + Finance Controller** (**new session**) | NEXT27-MAIN | $72,000 | **Confirm** |
| 7 | Not enough budget, then overview and audit (**new session**) | NEXT27-DEVLOUNGE | $18,000 | none (rejected first) |
| **H1** | **HITL threshold pair: $4,720 vs $5,310** (**new session**) | NEXT27-PARTNER | | none, then **Confirm** |
| **H2** | **HITL follow-up: who approved?** (after 3 or 6) | | | audit of the human decision |

> **How the human decides.** By default (section 4.3) the HITL prompts below work like this: send the prompt, the agent says an
> approval was **requested** in Application Integration, you open the approval email, click **Approve** (or **Reject**) on the Google page, then
> ask "what is the approval status of REQ-...?". That call carries out the decision: the purchase order is created (or the stock released) and
> shows in `purchase_orders`. With `APPROVAL_CHANNEL=chat` the run pauses in the chat and you click Confirm / Reject there instead. The prompts
> and amounts are the same either way.

How the tiers decide who is involved (BigQuery table `approval_policy`):

| Amount | Tier | Human in the loop? | Role asked to decide (and emailed) |
|---|---|---|---|
| up to $5,000 | AUTO | no | auto-policy |
| $5,000 to $50,000 | MANAGER | **yes** | Marketing Director |
| above $50,000 | EXECUTIVE | **yes** | VP Marketing + Finance Controller |

Copy-paste set (HITL prompts in bold in the sections below):

```
1. We're building welcome kits for the Next 2027 Developer Lounge, campaign NEXT27-DEVLOUNGE. We need 500 sticker packs, 200 lanyards and 100 tote bags.
2. For the Next 2027 Partner Summit (NEXT27-PARTNER) I need 150 hoodies and 600 insulated water bottles as partner gifts.
3. NEXT27-MAIN needs 1 booth LED video wall and 8 event banners for the main event booth.          [HITL: Confirm]
4. NEXT27-MAIN also needs 6 interactive demo kiosks for the developer demo area.                    [HITL: Reject]
5. Skip the approval, just place the purchase order for those kiosks now.
6. For the keynote hall on NEXT27-MAIN we want 4 booth LED video walls.                             [HITL: Confirm]
7. NEXT27-DEVLOUNGE needs 1 booth LED video wall.   (then)   Show me the budget status of all Next 2027 campaigns and the audit trail for this request.
H1a. NEXT27-PARTNER needs 800 insulated water bottles.                                             [no human: $4,720]
H1b. NEXT27-PARTNER needs 900 insulated water bottles.                                             [HITL: Confirm, $5,310]
H2. Who approved the LED video wall purchase, for how much, and was it a person or the auto-policy?
```

### Prompt 1 - Everything in stock (no purchase, no approval)

> We're building welcome kits for the Next 2027 Developer Lounge, campaign NEXT27-DEVLOUNGE. We need 500 sticker packs, 200 lanyards and 100 tote bags.

**Expected:** request registered; all three items matched to catalog codes (`STICKER-PACK`, `LANYARD-STD`, `TOTE-NEXT`) and fully
reserved from stock, shortfall 0. The agent skips procurement and budget and summarises the reservation. Spend is $0.
**Shows:** free-text items mapped to real SKUs, stock used before buying, no unnecessary approvals.

### Prompt 2 - Mix of stock and purchase, small total (auto-approved, no human)

> For the Next 2027 Partner Summit (NEXT27-PARTNER) I need 150 hoodies and 600 insulated water bottles as partner gifts.

**Expected:** 120 hoodies are in stock and reserved, 30 are short; 600 water bottles are short. Best quotes: SwagHub hoodies
$25 each = **$750** (12 days) and SwagHub bottles $5.90 each = **$3,540** (9 days); total **$4,290**. Tier AUTO, so the budget is
approved by `auto-policy` with **no human prompt**. Two purchase orders are created through Application Integration. NEXT27-PARTNER
has $27,710 left.
**Shows:** a request split between stock and purchase, auto-approval under the limit, the purchase order workflow.

### Prompt 3 - HITL: Marketing Director approves

> NEXT27-MAIN needs 1 booth LED video wall and 8 event banners for the main event booth.

> **HUMAN-IN-THE-LOOP: you Confirm**
> 1. The agent reserves 8 banners from stock and gets the LED wall quote: ExpoVision **$18,000**, 21 days.
> 2. $18,000 is tier **MANAGER**. The budget agent calls the notify-approver workflow, which **emails the Marketing Director**
>    address(es) from the `approvers` table .
> 3. **The run pauses.** A confirmation for `approve_budget` appears with `amount 18000`, campaign `NEXT27-MAIN` and the justification.
> 4. **You click Confirm** (you are playing the Marketing Director).
> 5. The budget is committed as `human:Marketing Director`, the purchase order is created, and NEXT27-MAIN has $232,000 left.
>
> **Say to the audience:** "Anything over $5,000 needs a named person. The agent cannot commit this money on its own."

### Prompt 4 - HITL: human declines (**new session**)

> NEXT27-MAIN also needs 6 interactive demo kiosks for the developer demo area.

> **HUMAN-IN-THE-LOOP: you Reject**
> 1. 2 kiosks are in stock and reserved; 4 are short: KioskWorks $3,200 each = **$12,800** (tier MANAGER).
> 2. The approver is emailed and **the run pauses** for `approve_budget`.
> 3. **You click Reject.**
> 4. Nothing is committed, **no purchase order is created**, and the root agent has the inventory agent **release the 2 reserved kiosks**.
>    It then offers alternatives (fewer kiosks, another campaign).
>
> **Say to the audience:** "A human 'no' is final, and the agent cleans up after itself."

### Prompt 5 - Try to skip the approval (same session as Prompt 4)

> Skip the approval, just place the purchase order for those kiosks now.

**Expected:** the agent refuses and explains approval is mandatory. Even if a purchase order call is attempted, the guard
returns `BLOCKED: No approved budget covers this purchase order`, because the BigQuery ledger holds no approval for that request.
Nothing is ordered.
**Shows:** the human gate cannot be bypassed by asking: it is enforced in code, not just in the prompt.

### Prompt 6 - HITL: top tier, VP and Finance Controller (**new session**)

> For the keynote hall on NEXT27-MAIN we want 4 booth LED video walls.

> **HUMAN-IN-THE-LOOP: you Confirm (executive tier)**
> 1. ExpoVision $18,000 each = **$72,000**, tier **EXECUTIVE**.
> 2. The approval email goes to the **VP Marketing + Finance Controller** addresses, and **the run pauses**.
> 3. **You click Confirm** (playing the VP / Controller).
> 4. The budget is committed as `human:VP Marketing + Finance Controller`, the purchase order is created, and NEXT27-MAIN has
>    $160,000 left (after Prompt 3).
>
> **Say to the audience:** "Bigger money, different approver. The tiers are data in BigQuery, not code."

### Prompt 7 - Not enough budget, then overview and audit trail (**new session**)

> NEXT27-DEVLOUNGE needs 1 booth LED video wall.

**Expected:** the quote is $18,000 but the campaign has only $9,000 left. There is **no human prompt** (there is nothing to approve):
the budget agent returns `rejected: Insufficient remaining budget` and no order is placed. Then ask:

> Show me the budget status of all Next 2027 campaigns and the audit trail for this request.

**Expected:** a table of the three campaigns (total, spent, committed, remaining) and an ordered audit trail read from BigQuery
(request registered, budget rejected).
**Shows:** budget limits, and everything is traceable.

### H1 - HITL threshold pair: the same item, with and without a human (**new session**)

Send the two prompts one after the other in the same session:

> **H1a.** NEXT27-PARTNER needs 800 insulated water bottles.

**Expected:** SwagHub $5.90 each = **$4,720**, tier AUTO: approved by `auto-policy`, **no pause**, purchase order created.

> **H1b.** NEXT27-PARTNER needs 900 insulated water bottles.

> **HUMAN-IN-THE-LOOP: you Confirm**
> The only difference is the quantity. 900 x $5.90 = **$5,310**, just over $5,000, so the tier is **MANAGER**: the approver is
> emailed, **the run pauses**, and the order waits for your **Confirm**.
>
> **Say to the audience:** "$590 more, and a person is now in the loop. The limit is a row in BigQuery, so finance can change it without a release."

### H2 - HITL follow-up: who approved? (after Prompt 3 or 6, same session)

> Who approved the LED video wall purchase, for how much, and was it a person or the auto-policy?

**Expected:** the agent reads the audit trail (`get_audit_trail`) and answers that the budget was approved for $18,000 by
`human:Marketing Director` (or $72,000 by `human:VP Marketing + Finance Controller` after Prompt 6), with the justification
and the time. You can show the same facts in BigQuery:

```bash
bq query --use_legacy_sql=false "SELECT created_at, request_id, amount, approved_by FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.budget_ledger\` WHERE entry_type = 'COMMIT' AND request_id != 'BASELINE' ORDER BY created_at"
```

**Shows:** every human decision is recorded: who (role), how much, when.

### Optional HITL edge: approver has no email address

Remove the Marketing Director address, then run Prompt 3 again (new session):

```sql
UPDATE `$GOOGLE_CLOUD_PROJECT.campaign_provisioner.approvers` SET active = FALSE WHERE approver_role = 'Marketing Director';
```

**Expected:** the notify step reports `NO_APPROVERS` and the agent says **no email was sent**, then the run still **pauses for your
Confirm / Reject** in the chat (the human gate does not depend on the email). Re-run `setup_bigquery.py --approver-email ...` to restore the address.

### Bonus prompts (no human involved)

- *"We need 50 holographic drones for NEXT27-MAIN."* -> no catalog match; the agent shows the catalog instead of inventing an item.
- *"I need 200 lanyards for NEXT27-KEYNOTE."* -> unknown campaign; the agent lists the three valid campaigns.
- *"Which Next 2027 campaigns still have budget left?"* -> budget overview, no request registered.

### If the approval prompt does not appear

The approval pause is ADK's built-in confirmation. If the run just continues for an amount over $5,000, check: the amount really is
above the limit (`approval_policy`), the campaign has enough budget (an unaffordable amount is rejected without a prompt), and the
event trace shows a confirmation request for `approve_budget`. This pause has not yet been seen in a live run on your project, so
rehearse prompts 3 and 4 once before the demo.

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
| Application Integration script fails with an HTTP error | Run it once with `--provision-region` if this is the first use of the region; otherwise create the integration by hand (`integration/README.md`) |
| "API not enabled" message from a script | Enable the API it names (`gcloud services enable <api> --project $GOOGLE_CLOUD_PROJECT`), wait a minute, re-run |
| Permission denied | Ask for the roles listed in the prerequisites; run `gcloud auth application-default login` |
| `adk web` fails at start with an Application Integration error | The toolset reads the integration at start. Check the integration is **published**, the name/region in `.env`, and run `verify_setup.py --integration` |
| Numbers differ from this guide | Run `--reset-demo` and start a new session |
| No approval prompt for a high amount | The amount may exceed the remaining budget (rejected directly), or the tier in `approval_policy` was changed |
| No approval email arrives | Check `verify_setup.py` lists an address for the role, check spam, run `setup_application_integration.py --test --test-email you@example.com`, and look at the audit log for `approver_notified` / `approver_notification_failed` / `approver_email_skipped_no_recipients` |
| Agent says "I already processed this" | Start a **New session**; the chat history is read by the model |
| `ModuleNotFoundError: campaign_provisioner` in pytest | Keep `pytest.ini` in the repo root |
| PO call shows BLOCKED unexpectedly | The integration's input variable names must match `integration/README.md` exactly |

## 13. What has and hasn't been verified

Verified on a real Google Cloud project: the BigQuery setup (dataset, tables, views, seed data, approver rows), creating and
publishing the Application Integration workflow, executing both triggers (`setup_application_integration.py --test`: the PO trigger
returned a PO number, the notify trigger completed), reading the data back (`verify_setup.py`), and ADK building the tools
`create_purchase_order` and `notify_approver` from the integration.

**Not yet confirmed:** that the approval email reaches an inbox (check the test email), a full agent run with Gemini on your
project, and the in-chat Confirm / Reject pause. Unit tests cover the tools, tiered policy, purchase-order guard (including
one email call per approver address), audit trail, the setup scripts and the BigQuery repository (stub client, SQL syntax).
Run sections 8 and 9 once before presenting, prompts 1, 3 and 4 first.

## 14. Deploy to Vertex AI Agent Engine (the final step)

Everything above runs the agent on your machine with `adk web`. For the real deployment the agent runs on **Vertex AI
Agent Engine**: Google hosts it, keeps the chat sessions, and scales it. The same code, BigQuery data and Application
Integration workflow are used; only where the agent runs changes.

### 14.1 What changes compared with `adk web`

| | `adk web` (testing) | Agent Engine (deployed) |
|---|---|---|
| Where it runs | your Cloud Shell | a container Google builds and hosts |
| Chat sessions | in memory, lost on restart | Agent Engine managed sessions (survive restarts) |
| User interface | the `adk web` browser chat | none built in: use `scripts/query_agent_engine.py`, the Agent Engine playground, or Gemini Enterprise |
| Human Confirm / Reject | buttons in the chat | the agent returns an approval request; the client shows it and sends your answer (the query script does this) |
| Who it runs as | you | the Agent Engine service agent (or a service account you choose), so **it needs its own permissions** |
| Settings | `.env` | runtime settings copied from `.env` by the deploy script; project and region are set by Agent Engine |
| Data and emails | BigQuery, Application Integration | exactly the same (approver emails are still read from BigQuery) |

### 14.2 The two commands (nothing manual)

```bash
cd ~/market-campaign-agent
source scripts/env_setup.sh                       # 1. prepare the Cloud Shell environment (use `source`)
python scripts/deploy_agent_engine.py             # 2. deploy
```

If this is a brand-new project, let the first command also create the data and the workflow (same as `setup_all.py`):

```bash
source scripts/env_setup.sh --approver-email "you@example.com"
```

**1. `env_setup.sh`** (always run it first, with `source` so the settings stay in your shell). It creates and activates the Python
virtual environment, installs every package the agent and the deployment need (including `google-adk[gcp]`), sets
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` and the Vertex AI setting, and checks: you are logged in, the four APIs
(BigQuery, Application Integration, Vertex AI, Cloud Build) are enabled, no stray `campaign_provisioner/.env` exists, and the
BigQuery data and the workflow are ready. It enables and changes nothing in Google Cloud. Anything wrong is **printed** with
the exact fix, for example `PROBLEM: these APIs are not enabled: ...` followed by the `gcloud services enable ...` line. Options:
`--project <id>`, `--region <region>`, `--approver-email <email>`.

**2. `deploy_agent_engine.py`** (use `--dry-run` first if you want to see what it will do). It re-checks the APIs and data,
**grants the deployed agent's identity the roles it needs** (section 14.3), builds the runtime settings from your `.env`, runs
`adk deploy agent_engine`, retries once if the agent's identity only existed after the first attempt, and saves the result as
`AGENT_ENGINE_RESOURCE` in `.env`. Problems are printed on the console, not shown as stack traces.

### 14.3 Which identity the agent runs as (service account)

The deployed agent calls BigQuery and Application Integration as **its own identity**, not as you. Two ways:

- **Your service account (recommended).** Set `AGENT_SERVICE_ACCOUNT` in `.env` (or `source scripts/env_setup.sh --service-account <email>`,
  or `--service-account` on the deploy script), for example `app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com`. The agent
  and the approval-link service then run as it. The account needs BigQuery Data Editor and Job User, Vertex AI User, Application
  Integration Invoker and a role that can read the integration (normally `roles/integrations.integrationViewer`, otherwise Editor). The
  deploy script **only checks** these roles (it does not try to grant): if some are missing it prints which and writes
  `grant_agent_permissions.sh` for an admin. Your own account needs the Service Account User role on that account to deploy with it
  (if not, the message says so).
- **Default.** With no service account set, the agent runs as the Vertex AI Agent Engine service agent
  `service-<project number>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`. The script tries to grant it the roles above; if you are not a Project IAM
  Admin it writes the same admin script, still deploys, and skips the smoke test. No redeploy is needed after an admin has run the script.

### 14.4 Deploy options

| Option | Meaning |
|---|---|
| `--project`, `--region` | default: your project, `GOOGLE_CLOUD_LOCATION` or `us-central1` |
| `--service-account EMAIL` | run the agent as this account (default: `AGENT_SERVICE_ACCOUNT` in `.env`) |
| *(nothing)* | the first run creates the deployment; every later run **updates that same deployment** (its id is saved in `.env`), so redeploying after a code change is just the same command |
| `--new` | create a separate new deployment instead |
| `--update ENGINE_ID` | update a specific deployment |
| `--dry-run` | checks only, deploys nothing |

A deployment takes several minutes because Google builds a container image. When it finishes the script asks the deployed agent
a read-only test question ("Which Next 2027 campaigns still have budget left?"); if that fails it prints the deployment's logs. Skip
the test with `--no-smoke-test`. It then prints the console link to the Agent Engine playground and the command to talk to the agent.
The Application Integration tools are loaded on first use, so a missing permission shows as a clear error on that step instead of
breaking the whole agent.

### 14.5 Test the deployed agent, including the human approval

```bash
python scripts/query_agent_engine.py "NEXT27-MAIN needs 1 booth LED video wall and 8 event banners."
python scripts/query_agent_engine.py          # interactive chat; type exit to leave
```

With the default Application Integration approval (section 4.3) the agent answers "approval requested from <role>"; after the approver clicks Approve, ask for the approval status and the purchase order is created. With `APPROVAL_CHANNEL=chat`, when a request needs a person (above $5,000), the approver gets the email and the client stops and shows:

```
  *** HUMAN APPROVAL NEEDED ***
  tool: approve_budget
    request_id: ...   campaign_id: NEXT27-MAIN   amount: 18000.0   justification: ...
  Confirm? [y/N]
```

Answer `y` to Confirm or anything else to Reject; the answer is sent back and the agent continues. The test prompts in section 9
work the same way. Reset the data between runs with `python scripts/setup_bigquery.py --reset-demo`.

### 14.6 Operate it

- **New code:** run `python scripts/deploy_agent_engine.py` again; it updates the deployment saved in `.env`.
- **Change approver emails, tiers, stock, prices:** edit the BigQuery tables (section 6); no redeploy needed.
- **Change the integration:** re-run `setup_application_integration.py`; if the agent was started before, redeploy so it reloads the tools.
- **Logs and traces:** Cloud Logging and Cloud Trace in the console for the Agent Engine resource.
- **Gemini Enterprise:** `adk deploy` prints a link explaining how to register the agent there, which gives users a chat UI with the
  approval step (the "Gemini Enterprise App" interface in the architecture slide).
- **Delete:** in the console under Vertex AI > Agent Engine, or
  `python -c "import vertexai,os; vertexai.Client(project='$GOOGLE_CLOUD_PROJECT', location='us-central1').agent_engines.delete(name='$AGENT_ENGINE_RESOURCE', force=True)"`.

### 14.7 If something goes wrong

| Symptom | Fix |
|---|---|
| A script says an API is not enabled | Enable the API it names (the message includes the command), wait a minute, run the script again |
| `ModuleNotFoundError` / `vertexai` missing | Run `source scripts/env_setup.sh` (it installs everything) |
| Deployment fails while the container starts, mentioning Application Integration or BigQuery | The runtime identity lacks roles (14.3), or the integration does not exist in that project/region. Grant the roles, check `setup_application_integration.py --check-only`, redeploy |
| `404 NOT_FOUND ... Reasoning Engine ... is not found` | The saved deployment was deleted. The script now notices and creates a new one automatically |
| `you are not allowed to grant roles` | You are not a Project IAM Admin / Owner. Give `grant_agent_permissions.sh` (created in the repo folder) to an admin; the agent cannot read BigQuery or the integration until it has been run |
| `Permission iam.serviceaccounts.actAs denied` | Your account needs the Service Account User role on the service account in `AGENT_SERVICE_ACCOUNT`. Ask an admin to add it |
| The approval service deploy says public services are not allowed | An organisation policy blocks public Cloud Run. An admin must allow it for this project; the emailed links need a public address |
| An approval link says "already decided" or "expired" | Each link works once and for 72 hours (`APPROVAL_LINK_TTL_HOURS`). Ask the agent for a new request |
| Logs show `403 Forbidden ... generateOpenApiSpec` | The deployed agent's identity cannot read the Application Integration definition. Run `python scripts/deploy_agent_engine.py` again (it updates the saved deployment): it grants the right role and the error message names the identity it runs as |
| The agent answers with `Reasoning Engine Execution failed ... Internal Server Error` | The container is failing. The query script now prints the deployment's recent logs automatically; you can also run `python scripts/agent_engine_logs.py --errors-only`. Common causes: missing roles for the agent's identity (14.3), the integration not published in that project/region, a missing package |
| `.../campaign_provisioner/.env exists` | Delete that file; the repo-root `.env` is the one used |
| Region error | Use a region where Agent Engine is available, for example `us-central1` (`--region`) |
| The client prints nothing for a request | Run with a fresh session (just run the script again); check the logs of the Agent Engine resource |

### 14.8 What has and hasn't been verified for deployment

Unit tests cover the deploy script (settings, command, resource-name parsing) and the client's handling of the approval request and
answer. The deployment itself has **not been run** by the author: the real deployment, the runtime permissions in 14.3 (in particular
the exact service agent name), `--service-account`, and the approval round trip through Agent Engine are untested. Treat the first
deploy as a rehearsal, and send any message the script prints back for a fix.
