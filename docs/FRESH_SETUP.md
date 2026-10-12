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
python scripts/deploy_agent_engine.py
python scripts/setup_bigquery.py --reset-demo
```

The agent logic runs inside the deployment, so redeploy whenever code changes. Data, tiers and approvers need no redeploy.

## E. Change approver emails

```bash
python scripts/setup_bigquery.py --approver-email "a@x.com,b@x.com"
python scripts/setup_application_integration.py --approver-email "a@x.com,b@x.com" --republish
```

Roles are "VP Product Marketing" and "CMO"; a bare list applies to both. The integration approval step has one recipient list,
so everyone in it receives every sign-off email. Launch-team tracking updates go to the "Launch Team" role.

## F. Test and debug the sign-off

1. Send the launch brief, then "Go with option 2." The reply must start with **HUMAN APPROVAL REQUIRED** and name the approver(s).
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
| 403 on Application Integration | `AGENT_SERVICE_ACCOUNT` missing in `.env` or roles missing; the deploy script says which |
