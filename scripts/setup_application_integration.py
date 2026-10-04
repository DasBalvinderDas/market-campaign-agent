#!/usr/bin/env python3
"""Create, publish and test the Application Integration workflow used by the agent.

  python scripts/setup_application_integration.py            # create + publish if missing (idempotent)
  python scripts/setup_application_integration.py --test     # ...then run both triggers once with sample data
  python scripts/setup_application_integration.py --check-only   # only check, change nothing

It builds integration "campaign-provisioner-workflows" with two API triggers through the Application
Integration REST API:
  create_purchase_order  in: request_id, campaign_id, sku, vendor_id, quantity, total_amount
                         out: po_number (PO-<request_id>-<sku>), execution_id
  notify_approver        in: request_id, campaign_id, approver_role, approver_emails, summary, amount
                         out: status
create_purchase_order runs a Data Mapping task. notify_approver builds the message, SENDS AN EMAIL to
approver_emails (a comma-separated list the agent reads from the BigQuery table `approvers`, so the addresses
are configured in data, not in the integration), then sets status. Use --no-email to skip the email task.

Assumes the Application Integration API is already enabled. Project id: --project, else
GOOGLE_CLOUD_PROJECT, else your active gcloud project. If an API is not enabled the script tells you which one.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import default_account_email, explain, guarded, preflight, resolve_project  # noqa: E402

NAME = os.getenv("APP_INTEGRATION_NAME", "campaign-provisioner-workflows")
LOCATION = os.getenv("APP_INTEGRATION_LOCATION", "us-central1")
PO_TRIGGER = os.getenv("APP_INTEGRATION_PO_TRIGGER", "api_trigger/create_purchase_order")
NOTIFY_TRIGGER = os.getenv("APP_INTEGRATION_NOTIFY_TRIGGER", "api_trigger/notify_approver")
API = "https://integrations.googleapis.com/v1"

S, I, D = "STRING_VALUE", "INT_VALUE", "DOUBLE_VALUE"

# Variable names are a contract with the agent (campaign_provisioner/workflow/guard.py).
PO_IN = {"request_id": S, "campaign_id": S, "sku": S, "vendor_id": S, "quantity": I, "total_amount": D}
PO_OUT = {"po_number": S, "execution_id": S}
NOTIFY_IN = {"request_id": S, "campaign_id": S, "approver_role": S, "approver_emails": S, "summary": S, "amount": D}
NOTIFY_OUT = {"status": S}

SAMPLE = {
    PO_TRIGGER: {"request_id": {"stringValue": "SETUP-TEST"}, "campaign_id": {"stringValue": "NEXT27-MAIN"},
                 "sku": {"stringValue": "BOOTH-LEDWALL"}, "quantity": {"intValue": "1"},
                 "vendor_id": {"stringValue": "V-EXPOVISION"}, "total_amount": {"doubleValue": 18000}},
}


def notify_sample(email):
    return {"request_id": {"stringValue": "SETUP-TEST"}, "campaign_id": {"stringValue": "NEXT27-MAIN"},
            "approver_role": {"stringValue": "Marketing Director"}, "approver_emails": {"stringValue": email},
            "summary": {"stringValue": "Setup test, please ignore: 1 booth LED video wall, USD 18,000"},
            "amount": {"doubleValue": 18000}}


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


def _lits(*parts):
    return [_concat(_lit(p)) if not p.startswith("$") else _concat(_ref(p.strip("$"))) for p in parts]


def _email_task(task_id, next_id):
    """Send Email task. Parameter keys follow Google's published foreach-loop-send-email sample."""
    empty = {"stringArray": {}}
    return {"task": "EmailTask", "taskId": task_id, "displayName": "Email the approver",
            "nextTasks": [{"taskId": next_id}], "taskExecutionStrategy": "WHEN_ALL_SUCCEED",
            "parameters": {
                "To": {"key": "To", "value": {"stringArray": {"stringValues": ["$recipient_list$"]}}},
                "Cc": {"key": "Cc", "value": empty}, "Bcc": {"key": "Bcc", "value": empty},
                "AttachmentPath": {"key": "AttachmentPath", "value": empty},
                "Subject": {"key": "Subject", "value": {"stringValue": "$email_subject$"}},
                "TextBody": {"key": "TextBody", "value": {"stringValue": "$email_body$"}},
                "BodyFormat": {"key": "BodyFormat", "value": {"stringValue": "text"}},
                "EmailConfigInput": {"key": "EmailConfigInput", "value": {
                    "jsonValue": json.dumps({"@type": "type.googleapis.com/enterprise.crm.eventbus.proto.EmailConfig"})}}}}


def build_version(email: bool = True) -> dict:
    """The IntegrationVersion body: two API triggers (purchase order, notify approver)."""
    po_number = {"inputField": {"fieldType": S, "transformExpression": {
        "initialValue": {"literalValue": {"stringValue": "PO-"}},
        "transformationFunctions": [_concat(_ref("request_id")), _concat(_lit("-")), _concat(_ref("sku"))]}},
        "outputField": _out_field("po_number")}
    execution_id = {"inputField": {"fieldType": S, "transformExpression": {"initialValue": {"baseFunction": {
        "functionType": {"baseFunction": {"functionName": "GET_EXECUTION_ID"}}}}}},
        "outputField": _out_field("execution_id")}
    status = {"inputField": {"fieldType": S, "transformExpression": _lit("NOTIFIED")},
              "outputField": _out_field("status")}

    params = {}
    for group, kind in ((PO_IN, "IN"), (NOTIFY_IN, "IN"), (PO_OUT, "OUT"), (NOTIFY_OUT, "OUT")):
        for key, typ in group.items():
            params.setdefault(key, {"key": key, "displayName": key, "dataType": typ, "inputOutputType": kind})
    tasks = [_mapping_task("1", "Build PO number", [po_number, execution_id])]
    if email:
        # 2: build recipient list + subject + body   3: send email   4: set status
        recipients = {"inputField": {"fieldType": S, "transformExpression": {
            "initialValue": _ref("approver_emails")["initialValue"],
            "transformationFunctions": [{"functionType": {"stringFunction": {"functionName": "SPLIT"}},
                                         "parameters": [_lit(",")]}]}},
            "outputField": {"referenceKey": "$recipient_list$", "fieldType": "STRING_ARRAY", "cardinality": "OPTIONAL"}}
        subject = {"inputField": {"fieldType": S, "transformExpression": {
            "initialValue": {"literalValue": {"stringValue": "Approval needed: "}},
            "transformationFunctions": _lits("$request_id$", " - ", "$campaign_id$", " (", "$approver_role$", ")")}},
            "outputField": _out_field("email_subject")}
        body = {"inputField": {"fieldType": S, "transformExpression": {
            "initialValue": _ref("summary")["initialValue"],
            "transformationFunctions": _lits("\n\nRequest ", "$request_id$", " needs approval from ", "$approver_role$",
                                             ". Open the Campaign Provisioner chat and choose Confirm or Reject.")}},
            "outputField": _out_field("email_body")}
        for key, typ in (("recipient_list", "STRING_ARRAY"), ("email_subject", S), ("email_body", S)):
            params[key] = {"key": key, "displayName": key, "dataType": typ}
        t2 = _mapping_task("2", "Build email", [recipients, subject, body])
        t2["nextTasks"] = [{"taskId": "3"}]
        t4 = _mapping_task("4", "Mark approver notified", [status])
        tasks += [t2, _email_task("3", "4"), t4]
    else:
        tasks.append(_mapping_task("2", "Mark approver notified", [status]))
    return {
        "description": "Campaign Provisioner workflows: create purchase order, notify approver by email.",
        "integrationParameters": list(params.values()),
        "triggerConfigs": [_trigger(1, PO_TRIGGER, "1", PO_IN, PO_OUT),
                           _trigger(2, NOTIFY_TRIGGER, "2", NOTIFY_IN, NOTIFY_OUT)],
        "taskConfigs": tasks,
    }


# ---------------------------------------------------------------- API calls
def _fail(resp, project):
    hint = explain(resp.text, project)
    sys.exit(f"\n{hint}" if hint else
             f"\nApplication Integration returned HTTP {resp.status_code}:\n{resp.text[:800]}\n\n"
             "If this is the first time Application Integration is used in this region, run this script once with "
             "--provision-region. Otherwise create the integration in the console (integration/README.md).")


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
    wanted = {PO_TRIGGER, NOTIFY_TRIGGER}
    print(f"Project: {project}   Integration: {NAME}   Region: {LOCATION}")

    if args.provision_region:
        r = http.post(f"{parent}/clients:provision", json={})
        if r.status_code not in (200, 409):
            _fail(r, project)
        print("  region provisioned (or already was)")

    exists, found = _published_triggers(http, base)
    if exists is None:
        _fail(found, project)

    if wanted <= found:
        print(f"  OK  already published: {', '.join(sorted(wanted))}")
    elif args.check_only:
        sys.exit(f"\nNot set up yet (missing: {', '.join(sorted(wanted - found))}). Run without --check-only to create it.")
    else:
        print("  creating the integration and publishing it ..." if not exists else "  adding a new version and publishing it ...")
        r = http.post(f"{base}/versions", params={"newIntegration": "false" if exists else "true"},
                      json=build_version(email=not args.no_email))
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
            samples[NOTIFY_TRIGGER] = notify_sample(test_email)
            print(f"\nRunning each trigger once; the approver email goes to {test_email} ...")
        elif not args.no_email:
            print("\nSkipping the notify_approver test: no email known. Pass --test-email you@example.com.")
        else:
            samples[NOTIFY_TRIGGER] = notify_sample("none@example.com")
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
    ap.add_argument("--test", action="store_true", help="execute both triggers once with sample data")
    ap.add_argument("--test-email", default=None, help="recipient for the --test approval email (default: your gcloud account)")
    ap.add_argument("--no-email", action="store_true", help="do not add the Send Email task to notify_approver")
    ap.add_argument("--check-only", action="store_true", help="check only; do not create anything")
    ap.add_argument("--provision-region", action="store_true",
                    help="one-time: enable Application Integration in this region (first use only)")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
