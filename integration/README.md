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
| in | `amount` | Double |
| out | `status` | String |

Typical tasks: a **Send Email** task or a **Google Chat** connector message to the approver role
("Marketing Director", or "VP Marketing + Finance Controller" for the top tier) with the request summary.
The actual approve / reject click still happens in the ADK confirmation prompt; the notification tells the
approver a decision is waiting.

## Build steps (Cloud Console)

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
- Set `WORKFLOW_BACKEND=mock` to rehearse without any integration; the mock functions use the same argument names.

## Status of this guide

The ADK side is covered by tests, but the integration itself must be built in your project. This guide was
written from the product documentation and was **not** run against a live Application Integration instance.
The console screens and the `execute` call may differ slightly; use `verify_setup.py --integration` to confirm.

## Optional: BigQuery through an Integration Connector

The agent reads BigQuery with the BigQuery client library. If your organisation requires all data access to go
through Integration Connectors, create a BigQuery connection and use
`ApplicationIntegrationToolset(connection=..., entity_operations={"campaigns": ["LIST", "GET"]})` instead; only the
tool bodies in `tools/` and the repository would change.
