# Fresh setup and reset cheat sheet

Run everything in Cloud Shell, from the repo folder. Replace the project, service account and approver email with yours.
Values used so far: project `gebu-demo-sandbox`, service account `app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com`,
approver `dasbalvinder.das@hcltech.com`.

| I want to... | Go to |
|---|---|
| Set everything up from scratch (new project or new Cloud Shell) | [A. Fresh setup](#a-fresh-setup) |
| Put the demo data back to the starting values (before a demo) | [B. Reset demo data](#b-reset-demo-data-fastest) |
| Wipe BigQuery completely and rebuild it | [C. Full BigQuery rebuild](#c-full-bigquery-rebuild) |
| Pick up new code (after a `git pull`) | [D. Update after new code](#d-update-after-new-code) |
| Change the approver email | [E. Change approver emails](#e-change-approver-emails) |

Prerequisites (an admin does these once): the BigQuery, Application Integration, Vertex AI and Cloud Build APIs are enabled; your
login can create BigQuery data and Application Integration versions; the service account has BigQuery, Application Integration
and Vertex AI roles. The scripts check this and print which API or permission is missing.

## A. Fresh setup

```bash
# 1. Get the code
git clone https://github.com/dasbalvinderdas/market-campaign-agent.git
cd market-campaign-agent
git checkout claude/next-2027-enhanced

# 2. Configure .env (project and the service account the agent runs as)
cat > .env <<'EOF'
GOOGLE_CLOUD_PROJECT=gebu-demo-sandbox
AGENT_SERVICE_ACCOUNT=app-svc-custom-sandbox@gebu-demo-sandbox.iam.gserviceaccount.com
EOF

# 3. Environment: venv, packages, login and API checks (use `source`, not `bash`)
source scripts/env_setup.sh --approver-email "dasbalvinder.das@hcltech.com"
```

Step 3 also creates the BigQuery dataset, tables, views and demo data, and the Application Integration workflows
(`create_purchase_order`, `notify_approver`, `request_approval`). If it reports a problem, fix what it names and run it again;
every step can be repeated safely.

If you prefer the steps one by one instead of the single command in step 3:

```bash
source scripts/env_setup.sh                       # environment checks only
python scripts/setup_all.py --approver-email "dasbalvinder.das@hcltech.com"   # BigQuery + Application Integration + .env
python scripts/verify_setup.py                    # prints the data and approver emails it can see
```

```bash
# 4. Check Application Integration: all three triggers must be listed as published
python scripts/setup_application_integration.py --check-only

# 5. Deploy the agent to Agent Engine (runs as the service account from .env)
python scripts/deploy_agent_engine.py             # the "Runs as:" line must show your service account

# 6. Try it
python scripts/query_agent_engine.py "NEXT27-MAIN needs 1 booth LED video wall and 8 event banners for the main event booth."
#    -> bold HUMAN APPROVAL REQUIRED line; click Approve in the email, then:
python scripts/query_agent_engine.py "What is the approval status of that request?"
```

To test locally in the browser instead of Agent Engine: `adk web` (see `docs/DEMO_RUN.md`, section 8). The test prompts and the
approval flow (send prompt, click the email, ask for the status) are in `docs/DEMO_RUN.md`, section 9.

## B. Reset demo data (fastest)

Use this before every demo run. It clears requests, reservations, purchase orders, approvals and the audit log, and puts the
budgets back to their opening balances. Reference data (items, vendors, tiers, approvers) is kept. Application Integration and
the deployed agent are not touched.

```bash
source scripts/env_setup.sh        # only needed in a new Cloud Shell tab
python scripts/setup_bigquery.py --reset-demo
```

Then start a **new session** in `adk web` or the query script.

## C. Full BigQuery rebuild

Drops every table and view in the dataset and rebuilds them with the seed data. Use it after a schema change, or if the data
is in a bad state. Approver emails are written again from the option, so pass them.

```bash
python scripts/setup_bigquery.py --reset --approver-email "dasbalvinder.das@hcltech.com"
```

## D. Update after new code

```bash
git pull origin claude/next-2027-enhanced
source scripts/env_setup.sh
python scripts/setup_application_integration.py --approver-email "dasbalvinder.das@hcltech.com"   # adds any new workflow
python scripts/setup_bigquery.py --reset-demo        # optional: demo values back to the start
python scripts/deploy_agent_engine.py                # updates the existing engine (use --new for a separate one)
```

## E. Change approver emails

The approval email recipients are stored in two places, so change both:

```bash
# 1. BigQuery table `approvers` (shown in the agent's message, used per role)
python scripts/setup_bigquery.py --approver-email "Marketing Director=md@x.com;VP Marketing + Finance Controller=vp@x.com,controller@x.com"
# 2. The Application Integration approval step (who really gets the Approve / Reject email)
python scripts/setup_application_integration.py --approver-email "md@x.com,vp@x.com,controller@x.com" --republish
```

A bare address (as in section A) applies to every role. Roles must match `approval_policy.approver_role` exactly.

## Quick checks

| Check | Command |
|---|---|
| Data and approvers present | `python scripts/verify_setup.py` |
| Application Integration published | `python scripts/setup_application_integration.py --check-only` |
| What the deployed agent is doing / errors | `python scripts/agent_engine_logs.py --errors-only` |
| Budget status in BigQuery | `bq query --use_legacy_sql=false "SELECT * FROM \`$GOOGLE_CLOUD_PROJECT.campaign_provisioner.v_campaign_budget\`"` |

Common problems: `docs/DEMO_RUN.md`, section 12.
