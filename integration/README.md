# Application Integration: the LaunchKit workflows

Integration name: `launchkit-workflows` (region `us-central1`, both configurable in `.env`). It is created and published by
`python scripts/setup_application_integration.py`, so nothing has to be built by hand. This page documents what the script builds, so
you can check it in the console or rebuild it manually.

The agent starts the triggers over the Application Integration API (`integrations.execute`) from `launchkit_provisioner/decision_flow.py`
and `execution.py`. The variable names below are a contract with that code.

## Triggers

### `create_purchase_order`
| Direction | Variable | Type |
|---|---|---|
| in | `request_id`, `plan_line_id`, `vendor_id`, `sku`, `destination_region` | String |
| in | `quantity` | Integer |
| in | `total_amount` | Double |
| out | `po_number` = `"PO-"` + `plan_line_id` (the agent sends `<request>-<vendor>`: one purchase order per vendor; `sku` carries the item list) , `execution_id` | String |

Task: **Data Mapping** (builds `po_number` and `execution_id`). One call per vendor line of the approved option.

### `create_depot_transfer`
| Direction | Variable | Type |
|---|---|---|
| in | `request_id`, `plan_line_id`, `depot_id`, `sku`, `destination_region` | String |
| in | `quantity` | Integer |
| out | `transfer_number` = `"TR-"` + `plan_line_id` (the agent sends `<request>-<warehouse>`: one transfer per warehouse), `execution_id` | String |

Task: **Data Mapping**. One call per depot (surplus stock) line.

### `request_approval` (the executive sign-off)
| Direction | Variable | Type |
|---|---|---|
| in | `request_id`, `launch_id`, `approver_role`, `approval_message` | String |
| in | `amount` | Double |
| out | `decision` (`APPROVED` / `REJECTED`) | String |

Tasks: an **Approval** task (`SuspensionTask`; message `$approval_message$`, notifications = the approver emails given to the setup
script, reminder after 1 day, expiry after 3 days) with two branches: `isApproved = true` leads to a Data Mapping task that sets
`decision = APPROVED`, `isApproved = false` to one that sets `decision = REJECTED`. The run is suspended until an approver clicks
Approve / Reject in the Google-hosted approval page (it may ask for a sign-in with the Google account that received the email). The click is
recorded as an approval record on the execution (`LIFTED` = approved, `REJECTED` = rejected), which `get_launch_status` reads.

### `send_launch_update`
| Direction | Variable | Type |
|---|---|---|
| in | `request_id`, `launch_id`, `recipient_email`, `email_subject`, `email_body` | String |
| out | `status` (`SENT`) | String |

Tasks: **Send Email** to `$recipient_email$` with `$email_subject$` and `$email_body$`, then a Data Mapping task sets `status`. One address per
call; `execute_plan` calls it once per address of the BigQuery role `Launch Team` when every line is placed. The email references only the
trigger's input variables, the pattern used in Google's published email sample.

## Setup, change and debug

```bash
python scripts/setup_application_integration.py --approver-email "vp@example.com,cmo@example.com"   # create + publish (idempotent)
python scripts/setup_application_integration.py --check-only                                         # are all four triggers published?
python scripts/setup_application_integration.py --republish                                          # publish a new version (needed once to switch off Google's own approval email)
python scripts/setup_application_integration.py --test --test-email you@example.com                  # run PO, transfer and update once
python scripts/setup_application_integration.py --print-definition                                   # the JSON that is sent
python scripts/check_approval.py [REQ-xxxx]                                                          # what the workflow says about a sign-off
```

The **agent** sends the approval email: an HTML email with Approve and Reject buttons, the shopping list and the vendors, to every address of the approver role in the
BigQuery table `approvers` (change them with `setup_bigquery.py --approver-email`; no republish needed). The approval task itself sends no email. Add
`--platform-approval-email` to also let Google email the approvers (its plain email with one long link). `--test` does not start `request_approval`.

Not yet confirmed on a real project for this integration: that the definition is accepted unchanged and that the update email arrives. If
the API rejects the definition the script prints its message and changes nothing; send that message for a fix, or build the four
triggers in the console from the tables above.


## Email format

`send_launch_update` sends a formatted **HTML** email (the agent builds the HTML table). If a project rejects the HTML body format, republish with
`python scripts/setup_application_integration.py --email-format text --republish`.

The approval email is the agent's own HTML email. Both buttons open the Application Integration approval page of that run
(`https://console.cloud.google.com/integrations/integration/<integration>/locations/<region>/approval?project=...&execution_id=...&task_number=10`), where the
approver confirms Approve or Reject. The approval task still shows the short summary (`customMessage`) on that page.
