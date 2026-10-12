# Fresh setup and reset cheat sheet (LaunchKit Provisioner)

Run everything in Cloud Shell, from the repo folder. Replace the project, service account and approver emails with yours.
Values used so far: project `gebu-demo-sandbox`, service account `app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com`,
approvers `dasbalvinder.das@hcltech.com` and `shilpa.raina@hcltech.com`. Branch: `claude/budget-approval-reshape`.
BigQuery dataset: `launchkit`. Application Integration: `launchkit-workflows` (4 triggers).

| I want to... | Go to |
|---|---|
| Set everything up from scratch | [A. Fresh setup](#a-fresh-setup) |
| Get ready for a demo (usual routine) | [B. Before every demo](#b-before-every-demo) |
| Wipe BigQuery and rebuild it | [C. Full BigQuery rebuild](#c-full-bigquery-rebuild) |
| Pick up new code after a `git pull` | [D. Update after new code](#d-update-after-new-code) |
| Load the latest items, vendors, prices and stock into BigQuery | [E2. Update the items and vendors data](#e2-update-the-items-and-vendors-data) |
| Change who gets the sign-off email | [E. Change approver emails](#e-change-approver-emails) |
| Test the sign-off or debug a wrong status | [F. Test and debug the sign-off](#f-test-and-debug-the-sign-off) |
| Something went wrong | [G. Problems](#g-problems) |

Prerequisites (an admin does these once): BigQuery, Application Integration, Vertex AI and Cloud Build APIs enabled; your login can
create BigQuery data and Application Integration versions; the service account has BigQuery, Application Integration and Vertex AI
roles. The scripts check this and print what is missing. No other Google Cloud service is used.

## A. Fresh setup

```bash
git clone https://github.com/dasbalvinderdas/market-campaign-agent.git
cd market-campaign-agent
git checkout claude/budget-approval-reshape

cat > .env <<'EOF2'
GOOGLE_CLOUD_PROJECT=gebu-demo-sandbox
AGENT_SERVICE_ACCOUNT=app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com
EOF

# venv, packages, login and API checks, BigQuery, Application Integration (use `source`, not `bash`)
source scripts/env_setup.sh --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"
```

This creates the dataset, tables, views and Spring Launch Event demo data, and the workflows `create_purchase_order`,
`create_depot_transfer`, `request_approval`, `send_launch_update`. Several approvers go in one comma-separated list. Every step can be repeated.

```bash
python scripts/verify_setup.py                                   # data, tables, tiers, approvers
python scripts/setup_application_integration.py --check-only     # all 4 triggers published
python scripts/deploy_agent_engine.py                            # "Runs as:" must show the service account
python scripts/setup_bigquery.py --reset-demo
python scripts/query_agent_engine.py "Show me the launch readiness board and the surplus depot stock."
```

Then register the deployed agent in Gemini Enterprise. Nothing else to set: the root agent calls the three specialists as tools and
writes every reply. Test prompts: `docs/DEMO_RUN.md`.

## B. Before every demo

```bash
cd ~/market-campaign-agent
source scripts/env_setup.sh        # only in a new Cloud Shell tab
python scripts/setup_bigquery.py --reset-demo
```

`--reset-demo` clears requests, plans, decisions, holds, orders, transfers and the audit log, and moves the Spring launch dates
(in-hand day = today + 25) so buffers are right. It keeps reference data and approvers, creates any missing table, and needs no
redeploy. Then open a **new chat** and follow `docs/DEMO_RUN.md`: send the prompt, click Approve/Reject in the email, ask for status.

## C. Full BigQuery rebuild

```bash
python scripts/setup_bigquery.py --reset --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"
```

## D. Update after new code

```bash
cd ~/market-campaign-agent
git pull origin claude/budget-approval-reshape
source scripts/env_setup.sh
python scripts/setup_application_integration.py --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"
python scripts/setup_bigquery.py --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"
python scripts/setup_bigquery.py --refresh-reference   # picks up new items, vendors, prices and stock, and resets the demo
python scripts/deploy_agent_engine.py
```

The agent logic runs inside the deployment, so redeploy whenever code changes. Data, tiers and approvers need no redeploy.

## E2. Update the items and vendors data

The offer the assistant shows (packs, items, our stock, vendor prices and ready-by dates) comes from BigQuery. The demo catalog (items, vendors,
price offers, stock) lives in `launchkit_provisioner/data/seed_data.py` and is loaded when the dataset is first built. If you pulled a newer
catalog, load it into the dataset you already have:

```bash
python scripts/setup_bigquery.py --refresh-reference     # reload items, vendors, offers, stock, lanes, rules, tiers; then reset the demo
python scripts/verify_setup.py                           # prints the counts: 19 items (SKUs), 12 vendors, 51 price offers, and the venues (USA, Canada, London, Singapore) with 11 date-pricing rows
```

It keeps the approver emails, and clears the demo transactions (old plans and orders) and any campaigns made in chat. It also puts the demo campaign and its guest list back if they are missing. **Run it before you deploy** a new version: the agent reads new tables (`venues`, `vendor_date_pricing`) and new columns (`suggested_per_person`), and the refresh adds them. If it ever reports a schema problem, `python scripts/setup_bigquery.py --reset --approver-email "..."` rebuilds everything.

To change a single price or stock number yourself, edit the table in BigQuery; the next answer uses it:

```bash
bq query --use_legacy_sql=false "UPDATE \`$GOOGLE_CLOUD_PROJECT.launchkit.vendor_offers\` SET unit_price = 39 WHERE vendor_id='V-APPAREL' AND sku LIKE 'HOODIE-EVENT-%' AND variant='STANDARD'"
bq query --use_legacy_sql=false "UPDATE \`$GOOGLE_CLOUD_PROJECT.launchkit.depot_stock\` SET on_hand = 300 WHERE depot_id='DEPOT-LON-01' AND sku='TOTE-CANVAS'"
```

Tables: `assets` (items), `vendors`, `vendor_offers` (price, days to make, carbon per vendor, item and variant), `depot_stock` (units per warehouse), `bundle_templates` (what is in a pack), `venues` (where a campaign can be held and the region that serves it), `vendor_date_pricing` (early-bird and rush price factors by days ahead).

## E. Change approver emails

```bash
python scripts/setup_bigquery.py --approver-email "a@x.com,b@x.com"
```

Roles are "VP Product Marketing" and "CMO"; a bare list applies to both. The integration approval step has one recipient list,
so everyone in it receives every sign-off email. Launch-team tracking updates go to the "Launch Team" role.

## F. Test and debug the sign-off

1. Send the launch brief, then "Choose option 2." The reply must start with **HUMAN APPROVAL REQUIRED** and name the approver(s).
2. Click **Approve** in the email.
3. Ask "What is the status?". Expect APPROVED, then the orders and transfers placed.

```bash
python scripts/check_approval.py            # latest sign-off, or: python scripts/check_approval.py REQ-xxxx
```

Approve shows as an approval record `LIFTED`, Reject as `REJECTED`; `PENDING` means the click did not register.

| Check | Command |
|---|---|
| Data, tables, approvers | `python scripts/verify_setup.py` |
| Workflows published | `python scripts/setup_application_integration.py --check-only` |
| Agent errors | `python scripts/agent_engine_logs.py --errors-only` |
| Readiness view | `bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.launchkit.v_launch_readiness\`"` |

## G. Problems

| Symptom | Cause and fix |
|---|---|
| "table not found" in the logs | Dataset predates a table: `python scripts/setup_bigquery.py --approver-email "..."` |
| `env_setup.sh` stops at "data or workflow not ready" | Run it as `source scripts/env_setup.sh --approver-email "..."` |
| Status stays pending after Approve | Redeploy, then `python scripts/check_approval.py` |
| Message names a wrong approver | `approvers` table wrong: re-run the BigQuery command in E, redeploy once |
| Buffers or delivery dates look wrong | Run `--reset-demo` (it re-bases the dates) |
| Gemini Enterprise shows no final answer | Check the Traces tab and `agent_engine_logs.py --errors-only`; the agent writes no text between steps, do not add it |
| Old numbers in the chat | Open a new chat after every reset |
| Publishing the workflows fails on the email body format | The launch-team update is an HTML email. Run `python scripts/setup_application_integration.py --email-format text --republish` to fall back to plain text |
| 403 on Application Integration | `AGENT_SERVICE_ACCOUNT` missing in `.env` or roles missing; the deploy script says which |
