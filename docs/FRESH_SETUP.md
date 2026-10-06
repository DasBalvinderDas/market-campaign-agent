# Fresh setup and reset cheat sheet

Run everything in Cloud Shell, from the repo folder. Replace the project, service account and approver emails with yours.
Values used so far: project `gebu-demo-sandbox`, service account `app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com`,
approvers `dasbalvinder.das@hcltech.com` and `shilpa.raina@hcltech.com`.

| I want to... | Go to |
|---|---|
| Set everything up from scratch (new project or new Cloud Shell) | [A. Fresh setup](#a-fresh-setup) |
| Get the agent ready for a demo (the usual routine) | [B. Before every demo](#b-before-every-demo) |
| Wipe BigQuery completely and rebuild it | [C. Full BigQuery rebuild](#c-full-bigquery-rebuild) |
| Pick up new code (after a `git pull`) | [D. Update after new code](#d-update-after-new-code) |
| Change who gets the approval email (one or several people) | [E. Change approver emails](#e-change-approver-emails) |
| Check the approval flow works, or find out why a status is wrong | [F. Test and debug the approval](#f-test-and-debug-the-approval) |
| Something went wrong | [G. Problems we have seen](#g-problems-we-have-seen) |

Prerequisites (an admin does these once): the BigQuery, Application Integration, Vertex AI and Cloud Build APIs are enabled; your
login can create BigQuery data and Application Integration versions; the service account has BigQuery, Application Integration
and Vertex AI roles. The scripts check this and print which API or permission is missing.

## A. Fresh setup

```bash
# 1. Get the code
git clone https://github.com/dasbalvinderdas/market-campaign-agent.git
cd market-campaign-agent
git checkout claude/next-2027-enhanced

# 2. Configure .env (project and the service account the agent runs as; the agent reads the account from .env)
cat > .env <<'EOF'
GOOGLE_CLOUD_PROJECT=gebu-demo-sandbox
AGENT_SERVICE_ACCOUNT=app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com
EOF

# 3. Environment + data: venv, packages, login and API checks, BigQuery, Application Integration (use `source`, not `bash`)
source scripts/env_setup.sh --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"
```

Step 3 also creates the BigQuery dataset, tables, views and demo data, and the Application Integration workflows
(`create_purchase_order`, `request_approval`, `notify_approver`). Several approvers go in one comma-separated list; they all get the
approval email. If it reports a problem, fix what it names and run it again; every step can be repeated safely.

If you prefer the steps one by one instead of the single command in step 3:

```bash
source scripts/env_setup.sh                       # environment checks only
python scripts/setup_all.py --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"   # BigQuery + Application Integration + .env
python scripts/verify_setup.py                    # prints the data, tables and approver emails it can see
```

```bash
# 4. Check Application Integration: all three triggers must be listed as published
python scripts/setup_application_integration.py --check-only

# 5. Deploy the agent to Agent Engine (runs as the service account from .env; the "Runs as:" line must show it)
python scripts/deploy_agent_engine.py

# 6. Reset the demo numbers, then try it
python scripts/setup_bigquery.py --reset-demo
python scripts/query_agent_engine.py "NEXT27-MAIN needs 1 booth LED video wall and 8 event banners for the main event booth."
#    -> the reply opens with HUMAN APPROVAL REQUIRED; click Approve in the email, then ask:
python scripts/query_agent_engine.py "What is the approval status of that request?"
```

To use the agent from **Gemini Enterprise**, register the deployed Agent Engine agent in your Gemini Enterprise app. There is nothing
else to set: the root agent calls inventory, procurement and budget as tools and writes every reply, on every platform. To test locally
in the browser instead: `adk web` (`docs/DEMO_RUN.md`, section 8). The test prompts are in `docs/DEMO_RUN.md`, section 9.

## B. Before every demo

```bash
cd ~/market-campaign-agent
source scripts/env_setup.sh        # only needed in a new Cloud Shell tab
python scripts/setup_bigquery.py --reset-demo
```

`--reset-demo` clears requests, reservations, purchase orders, approvals, the audit log and every budget commit, so budgets are back
to their opening balances (NEXT27-MAIN $250,000 remaining, NEXT27-PARTNER $32,000, NEXT27-DEVLOUNGE $9,000). It keeps items, vendors,
tiers and approver emails, and it creates any table that is missing. It does not touch Application Integration or the deployed agent,
so no redeploy is needed.

Then:
1. Open a **new chat** (Gemini Enterprise, the Agent Engine playground, `adk web`). An old chat still remembers old request ids and numbers.
2. Run the prompts in order (`docs/DEMO_RUN.md`, section 9). Each human-approval prompt has two steps: send it, click Approve or Reject in
   the email, then ask "What is the approval status of REQ-...?" (the reply gives the exact sentence).
3. A request takes about a minute to a minute and a half in Gemini Enterprise. The "Working on the request" panel lists each step.

## C. Full BigQuery rebuild

Drops every table and view in the dataset and rebuilds them with the seed data. Use it after a schema change, or if the data
is in a bad state. Approver emails are written again from the option, so pass them.

```bash
python scripts/setup_bigquery.py --reset --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"
```

## D. Update after new code

```bash
cd ~/market-campaign-agent
git pull origin claude/next-2027-enhanced
source scripts/env_setup.sh
python scripts/setup_application_integration.py --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"   # adds any new workflow
python scripts/setup_bigquery.py --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"                  # adds new tables, keeps data
python scripts/deploy_agent_engine.py                # updates the existing engine (use --new for a separate one)
python scripts/setup_bigquery.py --reset-demo        # demo numbers back to the start (after the deploy)
```

The agent's logic runs inside the deployment, so a `git pull` alone changes nothing in Agent Engine or Gemini Enterprise: **redeploy**
whenever the code changes. Data, approver emails and tiers are in BigQuery and need no redeploy.

## E. Change approver emails

The approval email recipients are kept in two places, so change both. Put several people in one comma-separated list:

```bash
# 1. BigQuery table `approvers` (the addresses the agent names in its HUMAN APPROVAL REQUIRED message)
python scripts/setup_bigquery.py --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com"
# 2. The Application Integration approval step (who really receives the Approve / Reject email)
python scripts/setup_application_integration.py --approver-email "dasbalvinder.das@hcltech.com,shilpa.raina@hcltech.com" --republish
```

A bare list applies to every approver role. Different people per role (`"Marketing Director=md@x.com;VP Marketing + Finance Controller=vp@x.com"`)
is possible in BigQuery, but the approval step in the integration has one list of recipients, so everyone named in command 2 receives
every approval email. Roles must match `approval_policy.approver_role` exactly. No redeploy is needed. After the change, run a request
and check that every person got the email (how a second approver sees a request the first has already decided is not yet confirmed).

## F. Test and debug the approval

1. Send the LED wall request (prompt 3). The reply must start with **HUMAN APPROVAL REQUIRED**, name the approver address(es) and a total
   of $18,510. Nothing is committed and no PO exists yet.
2. Click **Approve** in the Application Integration email (it may ask you to sign in with the Google account that received it).
3. In the same chat ask `What is the approval status of REQ-xxxx?`. Expect APPROVED, two POs (LED wall and banners) and about
   $231,490 left for NEXT27-MAIN. Clicking **Reject** instead should release the stock and create no PO.

If the status does not change after a click:

```bash
python scripts/check_approval.py            # latest approval; or:  python scripts/check_approval.py REQ-xxxx
```

It prints the approval row from BigQuery, the workflow execution and its approval records. A click on Approve shows as an approval
record with state `LIFTED`, Reject as `REJECTED`; still `PENDING` means the click did not register (open the email again).

## Quick checks

| Check | Command |
|---|---|
| Data, tables and approvers present | `python scripts/verify_setup.py` |
| Application Integration published (3 triggers) | `python scripts/setup_application_integration.py --check-only` |
| What Application Integration says about an approval | `python scripts/check_approval.py [REQ-xxxx]` |
| What the deployed agent is doing / errors | `python scripts/agent_engine_logs.py --errors-only` |
| Budget status in BigQuery | `bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.v_campaign_budget\`"` |
| Approver addresses in BigQuery | `bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.approvers\`"` |

## G. Problems we have seen

| Symptom | Cause and fix |
|---|---|
| The run stops silently after `reserve_inventory`, or "table not found: request_lines" in the logs | The dataset predates a newer table. `python scripts/setup_bigquery.py --approver-email "..."` creates missing tables (`bq ls campaign_provisioner` shows them). |
| `env_setup.sh` stops at "data or workflow not ready" on a new project | The integration and data do not exist yet: run it as `source scripts/env_setup.sh --approver-email "..."`. |
| The approval status stays pending after you clicked Approve | Redeploy (`python scripts/deploy_agent_engine.py`): older versions did not read the approval record. Then run `python scripts/check_approval.py`. |
| The message names an address that is not an approver (for example example.com) | The BigQuery `approvers` table is empty or wrong: `python scripts/setup_bigquery.py --approver-email "..."`, then redeploy once. |
| "No active vendors" for hoodies or bottles | An old deployment passed item names instead of SKUs. Redeploy; the quote tools now resolve names. |
| Gemini Enterprise shows no final answer | Check the session's Traces tab (run time, errors) and `python scripts/agent_engine_logs.py --errors-only`. The agent deliberately writes no text between steps; do not add it back. |
| Old numbers or old request ids appear | Open a new chat after every reset. |
| The agent runs as the wrong identity / 403 on Application Integration | `AGENT_SERVICE_ACCOUNT` is missing in `.env` or the account lacks the integration roles; the deploy script prints which. |

More: `docs/DEMO_RUN.md`, section 12.
