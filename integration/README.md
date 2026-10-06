# Application Integration: workflow contract

The agent calls **Google Application Integration** through ADK's `ApplicationIntegrationToolset`
for the two actions that touch the outside world. Everything the agent *reads* comes from BigQuery.

| Integration name | Region | Env vars |
|---|---|---|
| `campaign-provisioner-workflows` | `us-central1` | `APP_INTEGRATION_NAME`, `APP_INTEGRATION_LOCATION` |

You build one integration with **two API triggers**. The trigger IDs and the variable names below are a
contract: the code and the purchase-order guard rely on them. If you rename a trigger, set
`APP_INTEGRATION_PO_TRIGGER` / `APP_INTEGRATION_NOTIFY_TRIGGER`.

## Trigger 1: `api_trigger/create_purchase_order`

| Direction | Variable | Type | Notes |
|---|---|---|---|
| in | `request_id` | String | Approved request, e.g. `REQ-001` |
| in | `campaign_id` | String | Filled by the platform guard |
| in | `sku` | String | |
| in | `quantity` | Integer | |
| in | `vendor_id` | String | e.g. `V-EXPOVISION` |
| in | `total_amount` | Double | Recomputed by the guard from the vendor price list, not trusted from the model |
| out | `po_number` | String | Returned to the agent and stored in `purchase_orders` |
| out | `execution_id` | String | Optional; stored as `integration_execution_id` |

Typical tasks behind the trigger: create the PO in your ERP / procurement system (REST or a connector task),
email or post to the vendor, generate and return `po_number`. A minimal version only needs a **Data Mapping** task
that builds `po_number` (for example `PO-<request_id>-<sku>`) and maps it to the output variable.

## Trigger 2: `api_trigger/notify_approver`

| Direction | Variable | Type |
|---|---|---|
| in | `request_id`, `campaign_id`, `approver_role`, `summary` | String |
| in | `approver_email`, `email_subject`, `email_body` | String | One recipient address, subject and body. Filled by the platform (address from the BigQuery `approvers` table), never by the model |
| in | `amount` | Double |
| out | `status` | String |

Tasks (created by the setup script): a **Send Email** task mails `approver_email` using `email_subject` and `email_body`, then a
Data Mapping task sets `status = NOTIFIED`. The email references only the trigger's input variables, the same pattern as Google's
published email sample. The workflow emails **one address per call**; when a role has several addresses in the BigQuery `approvers`
table, the platform calls the trigger once per address. Recipients live in BigQuery, so changing an address needs no integration
change. You can add a Google Chat task in the console if you also want a chat message.

### Trigger `request_approval` (the human approval)

| Direction | Variable | Type |
|---|---|---|
| in | `request_id`, `campaign_id`, `approver_role`, `approval_message` | String |
| in | `amount` | Double |
| out | `decision` | String (`APPROVED` / `REJECTED`) |

Tasks: **Approval** (task `SuspensionTask`; message `$approval_message$`, notifications = the approver emails given to the setup
script, reminder after 1 day, expiry after 3 days) with two branches, `isApproved = true` -> Data Mapping `decision = APPROVED`,
`isApproved = false` -> Data Mapping `decision = REJECTED`. The run is suspended until an approver clicks Approve / Reject in the
Google-hosted approval page. The agent reads the execution afterwards (`get_approval_status`) and carries the decision out
(purchase orders or stock release). To build it by hand: add an **Approval** task, set the approvers, add a condition on each
outgoing edge, and map `decision` as above.

## Automatic setup (recommended)

```bash
export GOOGLE_CLOUD_PROJECT=<your-project-id>
python scripts/setup_application_integration.py            # create + publish (safe to re-run)
python scripts/setup_application_integration.py --test     # run both triggers once with sample data
```

The script calls the Application Integration REST API (`integrations.versions.create` then `:publish`) with the contract
above. Each trigger starts one Data Mapping task: `create_purchase_order` sets `po_number` to `PO-<request_id>-<sku>` and
`execution_id` to the execution id; `notify_approver` emails the approver (`approver_email`) and then sets `status` to `NOTIFIED`. It assumes the Application Integration API is
enabled and tells you which API to enable if not. `--provision-region` is a one-time step for a region that has never used
Application Integration. Use `--no-email` to skip the email task, `--print-definition` to see the JSON that is sent, and `--test --test-email you@example.com` to send one real test email.
The whole setup (BigQuery + this + `.env`) is also available as one command: `python scripts/setup_all.py`.

## Manual alternative (Cloud Console)

Prerequisite: the Application Integration API is enabled in your project. If it is not, the check script below tells you
which API to enable.

1. Console > **Application Integration**; if prompted, choose region `us-central1` and enable the API.
2. **Create integration** named `campaign-provisioner-workflows`.
3. Add an **API Trigger**, set its Trigger ID to `create_purchase_order`, and create the input and output variables above.
4. Add the tasks described above, connect them to the trigger, then **Publish**.
5. Repeat steps 3 and 4 for `notify_approver` (same integration, second trigger).
6. Test each trigger in the console's **Test** panel with sample values.

## Test from the command line

```bash
TOKEN=$(gcloud auth print-access-token)
curl -s -X POST \
  "https://integrations.googleapis.com/v1/projects/$GOOGLE_CLOUD_PROJECT/locations/us-central1/integrations/campaign-provisioner-workflows:execute" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"triggerId":"api_trigger/create_purchase_order","inputParameters":{
        "request_id":{"stringValue":"REQ-TEST"},"campaign_id":{"stringValue":"NEXT27-MAIN"},
        "sku":{"stringValue":"BOOTH-LEDWALL"},"quantity":{"intValue":"1"},
        "vendor_id":{"stringValue":"V-EXPOVISION"},"total_amount":{"doubleValue":18000}}}'
```

Or let the script do both checks for you (project id from `GOOGLE_CLOUD_PROJECT` or your gcloud project):

```bash
python scripts/setup_application_integration.py          # is it there and published?
python scripts/setup_application_integration.py --test   # run both triggers once with sample data
python scripts/verify_setup.py --integration             # prints the tool names ADK generated
```

## How the agent uses it

Today these two triggers are the action layer; the agent directs the order of the steps. To run the whole campaign flow
inside Application Integration instead, see `docs/DEMO_RUN.md` section 4.2.

- `workflow/integration.py` builds one `ApplicationIntegrationToolset` per trigger (one for the procurement agent,
  one for the budget agent).
- `workflow/guard.py` runs **before** the PO tool: no PO unless the BigQuery budget ledger holds an approved COMMIT
  that still covers the amount. It runs **after**: stores the PO and audit events in BigQuery.

**Deployed agent:** when the agent runs on Agent Engine it calls this integration as its own identity, which needs
`roles/integrations.integrationInvoker` and a role that can read the integration (`roles/integrations.integrationViewer`, or Editor if Viewer is not enough; the deploy script picks it) (see `docs/DEMO_RUN.md` section 14.3).

## Status of this guide

The ADK side and the setup script's logic are covered by offline tests, the integration definition was checked field by field
against Google's published API schema (discovery document), and the Send Email task's parameter keys were copied from
Google's published `foreach-loop-send-email` sample. On a real project the script created and published this integration, and
`--test` executed both triggers successfully (an earlier version that used a list variable for the recipients was rejected by the
API and was replaced by the one-address-per-call design). The approval email has been received and answered on a real project (Approve recorded, purchase order created). If something fails
the script prints the API's message and you can use the manual steps above.
The console screens and the `execute` call may differ slightly; use `verify_setup.py --integration` to confirm.

## Optional: BigQuery through an Integration Connector

The agent reads BigQuery with the BigQuery client library. If your organisation requires all data access to go
through Integration Connectors, create a BigQuery connection and use
`ApplicationIntegrationToolset(connection=..., entity_operations={"campaigns": ["LIST", "GET"]})` instead; only the
tool bodies in `tools/` and the repository would change.

## Debugging an approval

`python scripts/check_approval.py [REQ-id]` prints the approval row from BigQuery, the workflow execution and its approval records.
A click on Approve shows as an approval record with state `LIFTED`, Reject as `REJECTED`; the agent reads that record when the
status is asked.
