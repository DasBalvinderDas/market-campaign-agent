#!/usr/bin/env python3
"""Create, publish and test the Application Integration workflows used by the agent.

  python scripts/setup_application_integration.py            # create + publish if missing (idempotent)
  python scripts/setup_application_integration.py --test     # ...then run the order triggers once with sample data
  python scripts/setup_application_integration.py --check-only   # only check, change nothing

It builds integration "launchkit-workflows" with four API triggers through the Application Integration REST API:
  create_purchase_order   in: request_id, plan_line_id, vendor_id, sku, quantity, total_amount, destination_region
                          out: po_number (PO-<plan_line_id>), execution_id
  create_depot_transfer   in: request_id, plan_line_id, depot_id, sku, quantity, destination_region
                          out: transfer_number (TR-<plan_line_id>), execution_id
  request_approval        in: request_id, launch_id, approver_role, amount, approval_message
                          out: decision (APPROVED / REJECTED). A native Approval (suspension) task: the run pauses, the
                          approver(s) get an Application Integration email with Approve / Reject, and the run continues
                          with the answer.
  send_launch_update      in: request_id, launch_id, recipient_email, email_subject, email_body
                          out: status. SENDS AN EMAIL (Send Email task) to ONE address; the agent calls it once per
                          address of the BigQuery role "Launch Team", so recipients are data, not part of the workflow.
The two order triggers run a Data Mapping task. Use --no-email to skip the email task. --print-definition shows the
JSON that is sent.

Assumes the Application Integration API is already enabled. Project id: --project, else
GOOGLE_CLOUD_PROJECT, else your active gcloud project. If an API is not enabled the script tells you which one.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import default_account_email, explain, guarded, preflight, resolve_project  # noqa: E402

NAME = os.getenv("APP_INTEGRATION_NAME", "launchkit-workflows")
LOCATION = os.getenv("APP_INTEGRATION_LOCATION", "us-central1")
PO_TRIGGER = os.getenv("APP_INTEGRATION_PO_TRIGGER", "api_trigger/create_purchase_order")
TRANSFER_TRIGGER = os.getenv("APP_INTEGRATION_TRANSFER_TRIGGER", "api_trigger/create_depot_transfer")
UPDATE_TRIGGER = os.getenv("APP_INTEGRATION_UPDATE_TRIGGER", "api_trigger/send_launch_update")
APPROVAL_TRIGGER = os.getenv("APP_INTEGRATION_APPROVAL_TRIGGER", "api_trigger/request_approval")
API = "https://integrations.googleapis.com/v1"

S, I, D = "STRING_VALUE", "INT_VALUE", "DOUBLE_VALUE"

# Variable names are a contract with the agent (launchkit_provisioner/execution.py, decision_flow.py).
PO_IN = {"request_id": S, "plan_line_id": S, "vendor_id": S, "sku": S, "quantity": I, "total_amount": D,
         "destination_region": S}
PO_OUT = {"po_number": S, "execution_id": S}
TRANSFER_IN = {"request_id": S, "plan_line_id": S, "depot_id": S, "sku": S, "quantity": I, "destination_region": S}
TRANSFER_OUT = {"transfer_number": S, "execution_id": S}
APPROVAL_IN = {"request_id": S, "launch_id": S, "approver_role": S, "amount": D, "approval_message": S}
APPROVAL_OUT = {"decision": S}
UPDATE_IN = {"request_id": S, "launch_id": S, "recipient_email": S, "email_subject": S, "email_body": S}
UPDATE_OUT = {"status": S}

SAMPLE = {
    PO_TRIGGER: {"request_id": {"stringValue": "SETUP-TEST"}, "plan_line_id": {"stringValue": "SETUP-TEST-L01"},
                 "vendor_id": {"stringValue": "V-DISPLAYCO"}, "sku": {"stringValue": "DISPLAY-COUNTER-AURORA"},
                 "quantity": {"intValue": "1"}, "total_amount": {"doubleValue": 1400},
                 "destination_region": {"stringValue": "US"}},
    TRANSFER_TRIGGER: {"request_id": {"stringValue": "SETUP-TEST"}, "plan_line_id": {"stringValue": "SETUP-TEST-L02"},
                       "depot_id": {"stringValue": "DEPOT-LON-01"}, "sku": {"stringValue": "PKG-LUX-BOX-BLACK"},
                       "quantity": {"intValue": "1"}, "destination_region": {"stringValue": "EMEA"}},
}


def update_sample(email):
    return {"request_id": {"stringValue": "SETUP-TEST"}, "launch_id": {"stringValue": "LAUNCH-AURORA"},
            "recipient_email": {"stringValue": email},
            "email_subject": {"stringValue": "LaunchKit Provisioner setup test (please ignore)"},
            "email_body": {"stringValue": "This is a test of the launch tracking update email. No action needed."}}


# ---------------------------------------------------------------- integration definition
def _ref(name):
    return {"initialValue": {"referenceValue": f"${name}$"}}


def _lit(text):
    return {"initialValue": {"literalValue": {"stringValue": text}}}


def _concat(param):
    return {"functionType": {"stringFunction": {"functionName": "CONCAT"}}, "parameters": [param]}


def _mapping_task(task_id, display_name, mapped_fields):
    """A Data Mapping task (task name FieldMappingTask) with the given input -> output fields."""
    config = {"@type": "type.googleapis.com/enterprise.crm.eventbus.proto.FieldMappingConfig",
              "mappedFields": mapped_fields}
    return {"task": "FieldMappingTask", "taskId": task_id, "displayName": display_name, "nextTasks": [],
            "taskExecutionStrategy": "WHEN_ALL_SUCCEED",
            "parameters": {"FieldMappingConfigTaskParameterKey": {
                "key": "FieldMappingConfigTaskParameterKey", "value": {"jsonValue": json.dumps(config)}}}}


def _out_field(name):
    return {"referenceKey": f"${name}$", "fieldType": S, "cardinality": "OPTIONAL"}


def _trigger(number, trigger_id, start_task, inputs, outputs):
    name = trigger_id.split("/", 1)[1]
    return {"label": "API Trigger", "triggerType": "API", "triggerNumber": str(number), "triggerId": trigger_id,
            "startTasks": [{"taskId": start_task}], "properties": {"Trigger name": name},
            "inputVariables": {"names": list(inputs)}, "outputVariables": {"names": list(outputs)}}


def _email_task(task_id, next_id):
    """Send Email task. Parameter keys follow Google's published foreach-loop-send-email sample."""
    empty = {"stringArray": {}}
    return {"task": "EmailTask", "taskId": task_id, "displayName": "Email the launch team",
            "nextTasks": [{"taskId": next_id}], "taskExecutionStrategy": "WHEN_ALL_SUCCEED",
            "parameters": {
                "To": {"key": "To", "value": {"stringArray": {"stringValues": ["$recipient_email$"]}}},
                "Cc": {"key": "Cc", "value": empty}, "Bcc": {"key": "Bcc", "value": empty},
                "AttachmentPath": {"key": "AttachmentPath", "value": empty},
                "Subject": {"key": "Subject", "value": {"stringValue": "$email_subject$"}},
                "TextBody": {"key": "TextBody", "value": {"stringValue": "$email_body$"}},
                "BodyFormat": {"key": "BodyFormat", "value": {"stringValue": "text"}},
                "EmailConfigInput": {"key": "EmailConfigInput", "value": {
                    "jsonValue": json.dumps({"@type": "type.googleapis.com/enterprise.crm.eventbus.proto.EmailConfig"})}}}}


def _approval_task(task_id, approver_emails, approve_id, reject_id):
    """Native Application Integration approval (task name SuspensionTask), modelled on Google's
    sample_order_processing sample. The run suspends here; each approver gets an email with Approve / Reject.
    Edges: isApproved = true -> approve_id, false -> reject_id."""
    notes = {"protoValues": [{"@type": "type.googleapis.com/enterprise.crm.eventbus.proto.Notification",
                              "emailAddress": {"email": e}} for e in approver_emails]}
    expiry = {"@type": "type.googleapis.com/enterprise.crm.eventbus.proto.SuspensionExpiration",
              "remindAfterMs": 86400000, "expireAfterMs": 259200000}
    flag = f"$`Task_{task_id}_isApproved`$"
    return {"task": "SuspensionTask", "taskId": task_id, "displayName": "Approval",
            "nextTasks": [{"taskId": approve_id, "condition": f"{flag} = true", "displayName": "Approved"},
                          {"taskId": reject_id, "condition": f"{flag} = false", "displayName": "Rejected"}],
            "taskExecutionStrategy": "WHEN_ALL_SUCCEED", "successPolicy": {"finalState": "SUSPENDED"},
            "externalTaskType": "NORMAL_TASK",
            "parameters": {
                "customMessage": {"key": "customMessage", "value": {"stringValue": "$approval_message$"}},
                "isApproved": {"key": "isApproved", "value": {"stringArray": {"stringValues": [flag]}}},
                "notifications": {"key": "notifications", "value": {"jsonValue": json.dumps(notes)}},
                "suspensionExpiration": {"key": "suspensionExpiration", "value": {"jsonValue": json.dumps(expiry)}}}}


def _decision_task(task_id, decision):
    field = {"inputField": {"fieldType": S, "transformExpression": _lit(decision)},
             "outputField": _out_field("decision")}
    return _mapping_task(task_id, f"Decision: {decision}", [field])


def _prefixed(prefix, ref_name, out_name):
    """Data Mapping field: <out_name> = "<prefix>" + $ref_name$."""
    return {"inputField": {"fieldType": S, "transformExpression": {
        "initialValue": {"literalValue": {"stringValue": prefix}}, "transformationFunctions": [_concat(_ref(ref_name))]}},
        "outputField": _out_field(out_name)}


def _execution_id():
    return {"inputField": {"fieldType": S, "transformExpression": {"initialValue": {"baseFunction": {
        "functionType": {"baseFunction": {"functionName": "GET_EXECUTION_ID"}}}}}},
        "outputField": _out_field("execution_id")}


def build_version(email: bool = True, approver_emails=None) -> dict:
    """The IntegrationVersion body: four API triggers (purchase order, depot transfer, approval, launch update)."""
    status = {"inputField": {"fieldType": S, "transformExpression": _lit("SENT")}, "outputField": _out_field("status")}
    params = {}
    for group, kind in ((PO_IN, "IN"), (TRANSFER_IN, "IN"), (APPROVAL_IN, "IN"), (UPDATE_IN, "IN"), (PO_OUT, "OUT"),
                        (TRANSFER_OUT, "OUT"), (APPROVAL_OUT, "OUT"), (UPDATE_OUT, "OUT")):
        for key, typ in group.items():
            params.setdefault(key, {"key": key, "displayName": key, "dataType": typ, "inputOutputType": kind})
    tasks = [_mapping_task("1", "Build PO number", [_prefixed("PO-", "plan_line_id", "po_number"), _execution_id()]),
             _mapping_task("4", "Build transfer number",
                           [_prefixed("TR-", "plan_line_id", "transfer_number"), _execution_id()])]
    if email:
        # 2: send email (only trigger inputs are referenced, like Google's foreach-loop-send-email sample)
        # 3: set status
        tasks += [_email_task("2", "3"), _mapping_task("3", "Mark update sent", [status])]
    else:
        tasks.append(_mapping_task("2", "Mark update sent", [status]))
    tasks += [_approval_task("10", approver_emails or ["approver@example.com"], "11", "12"),
              _decision_task("11", "APPROVED"), _decision_task("12", "REJECTED")]
    return {
        "description": "LaunchKit Provisioner workflows: purchase order, depot transfer, executive sign-off, launch update.",
        "integrationParameters": list(params.values()),
        "triggerConfigs": [_trigger(1, PO_TRIGGER, "1", PO_IN, PO_OUT),
                           _trigger(2, TRANSFER_TRIGGER, "4", TRANSFER_IN, TRANSFER_OUT),
                           _trigger(3, APPROVAL_TRIGGER, "10", APPROVAL_IN, APPROVAL_OUT),
                           _trigger(4, UPDATE_TRIGGER, "2", UPDATE_IN, UPDATE_OUT)],
        "taskConfigs": tasks,
    }


def approver_addresses(specs=None):
    """Emails the native approval step notifies: from --approver-email specs ([ROLE=]EMAIL[,EMAIL]), else the
    APPROVER_EMAILS env var, else the active gcloud account. They are fixed in the published integration version;
    re-run with --republish to change them."""
    text = ";".join(specs or []) or os.getenv("APPROVER_EMAILS", "")
    found = list(dict.fromkeys(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)))
    if not found and default_account_email():
        found = [default_account_email()]
    return found


# ---------------------------------------------------------------- API calls
def _fail(resp, project):
    hint = explain(resp.text, project)
    if hint:
        sys.exit(f"\n{hint}")
    msg = f"\nApplication Integration returned HTTP {resp.status_code}:\n{resp.text[:800]}\n"
    if resp.status_code == 400:
        msg += ("\nThe API rejected the integration definition. Send this message to the maintainer; "
                "`--print-definition` shows exactly what was sent. You can also build the integration in the "
                "console (integration/README.md).")
    elif resp.status_code in (403, 404):
        msg += ("\nIf Application Integration has never been used in this region, run this script once with "
                "--provision-region. Otherwise check the permissions (Application Integration Editor) and the region.")
    sys.exit(msg)


def _published_triggers(http, base):
    """Returns (exists, trigger ids found in ACTIVE versions)."""
    resp = http.get(f"{base}/versions")
    if resp.status_code == 404:
        return False, set()
    if resp.status_code != 200:
        return None, resp
    versions = resp.json().get("integrationVersions", [])
    found = {t.get("triggerId") for v in versions if v.get("state") == "ACTIVE" for t in v.get("triggerConfigs", [])}
    return True, found


@guarded
def run(args, project=""):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    if not getattr(args, "skip_preflight", False):
        preflight(project, ["integrations.googleapis.com"], check_bigquery_permissions=False)
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    http = AuthorizedSession(creds)
    run_with(http, args, project)


def run_with(http, args, project):
    parent = f"{API}/projects/{project}/locations/{LOCATION}"
    base = f"{parent}/integrations/{NAME}"
    wanted = {PO_TRIGGER, TRANSFER_TRIGGER, APPROVAL_TRIGGER, UPDATE_TRIGGER}
    print(f"Project: {project}   Integration: {NAME}   Region: {LOCATION}")

    if args.provision_region:
        r = http.post(f"{parent}/clients:provision", json={})
        if r.status_code not in (200, 409):
            _fail(r, project)
        print("  region provisioned (or already was)")

    exists, found = _published_triggers(http, base)
    if exists is None:
        _fail(found, project)
    approvers = approver_addresses(getattr(args, "approver_email", None))

    if wanted <= found and not getattr(args, "republish", False):
        print(f"  OK  already published: {', '.join(sorted(wanted))}")
    elif args.check_only:
        sys.exit(f"\nNot set up yet (missing: {', '.join(sorted(wanted - found))}). Run without --check-only to create it.")
    else:
        print("  creating the integration and publishing it ..." if not exists else "  adding a new version and publishing it ...")
        r = http.post(f"{base}/versions", params={"newIntegration": "false" if exists else "true"},
                      json=build_version(email=not args.no_email, approver_emails=approvers))
        if r.status_code != 200:
            _fail(r, project)
        version = r.json()["name"]
        r = http.post(f"{API}/{version}:publish", json={})
        if r.status_code != 200:
            _fail(r, project)
        exists, found = _published_triggers(http, base)
        if not (wanted <= (found if isinstance(found, set) else set())):
            sys.exit("\nThe version was created but is not showing as published. Open the integration in the console and click Publish.")
        print(f"  OK  created and published: {', '.join(sorted(wanted))}")

    if args.test:
        test_email = args.test_email or default_account_email()
        samples = dict(SAMPLE)
        if test_email and not args.no_email:
            samples[UPDATE_TRIGGER] = update_sample(test_email)
            print(f"\nRunning each order trigger once; the update email goes to {test_email} ...")
        elif not args.no_email:
            print("\nSkipping the send_launch_update test: no email known. Pass --test-email you@example.com.")
        else:
            samples[UPDATE_TRIGGER] = update_sample("none@example.com")
            print("\nRunning each trigger once ...")
        for trigger, params in samples.items():
            r = http.post(f"{base}:execute", json={"triggerId": trigger, "inputParameters": params})
            if r.status_code != 200:
                _fail(r, project)
            body = r.json()
            print(f"  {trigger}: failed={body.get('executionFailed', False)} outputs={body.get('outputParameters')}")
    print("\nApplication Integration OK. Next: python scripts/verify_setup.py --integration")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--test", action="store_true", help="execute the order triggers once with sample data")
    ap.add_argument("--test-email", default=None, help="recipient for the --test update email (default: your gcloud account)")
    ap.add_argument("--approver-email", action="append", default=[], metavar="[ROLE=]EMAIL[,EMAIL]",
                    help="who gets the sign-off email (Approve / Reject); default: APPROVER_EMAILS, else your gcloud account")
    ap.add_argument("--republish", action="store_true", help="publish a new version even if the triggers exist (e.g. new approver emails)")
    ap.add_argument("--no-email", action="store_true", help="do not add the Send Email task to send_launch_update")
    ap.add_argument("--check-only", action="store_true", help="check only; do not create anything")
    ap.add_argument("--provision-region", action="store_true",
                    help="one-time: enable Application Integration in this region (first use only)")
    ap.add_argument("--print-definition", action="store_true", help="print the integration definition JSON and exit")
    args = ap.parse_args()
    if args.print_definition:
        print(json.dumps(build_version(email=not args.no_email, approver_emails=approver_addresses(args.approver_email)), indent=2))
        return
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
