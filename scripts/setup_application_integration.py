#!/usr/bin/env python3
"""Create, publish and test the Application Integration workflow used by the agent.

  python scripts/setup_application_integration.py            # create + publish if missing (idempotent)
  python scripts/setup_application_integration.py --test     # ...then run both triggers once with sample data
  python scripts/setup_application_integration.py --check-only   # only check, change nothing

It builds integration "campaign-provisioner-workflows" with two API triggers through the Application
Integration REST API:
  create_purchase_order  in: request_id, campaign_id, sku, vendor_id, quantity, total_amount
                         out: po_number (PO-<request_id>-<sku>), execution_id
  notify_approver        in: request_id, campaign_id, approver_role, summary, amount
                         out: status
Each trigger runs one Data Mapping task. To send a real email or Chat message, open the integration in the
console and add a Send Email / Google Chat task after the notify_approver mapping (optional).

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

from _common import explain, guarded, resolve_project  # noqa: E402

NAME = os.getenv("APP_INTEGRATION_NAME", "campaign-provisioner-workflows")
LOCATION = os.getenv("APP_INTEGRATION_LOCATION", "us-central1")
PO_TRIGGER = os.getenv("APP_INTEGRATION_PO_TRIGGER", "api_trigger/create_purchase_order")
NOTIFY_TRIGGER = os.getenv("APP_INTEGRATION_NOTIFY_TRIGGER", "api_trigger/notify_approver")
API = "https://integrations.googleapis.com/v1"

S, I, D = "STRING_VALUE", "INT_VALUE", "DOUBLE_VALUE"

# Variable names are a contract with the agent (campaign_provisioner/workflow/guard.py).
PO_IN = {"request_id": S, "campaign_id": S, "sku": S, "vendor_id": S, "quantity": I, "total_amount": D}
PO_OUT = {"po_number": S, "execution_id": S}
NOTIFY_IN = {"request_id": S, "campaign_id": S, "approver_role": S, "summary": S, "amount": D}
NOTIFY_OUT = {"status": S}

SAMPLE = {
    PO_TRIGGER: {"request_id": {"stringValue": "SETUP-TEST"}, "campaign_id": {"stringValue": "NEXT27-MAIN"},
                 "sku": {"stringValue": "BOOTH-LEDWALL"}, "quantity": {"intValue": "1"},
                 "vendor_id": {"stringValue": "V-EXPOVISION"}, "total_amount": {"doubleValue": 18000}},
    NOTIFY_TRIGGER: {"request_id": {"stringValue": "SETUP-TEST"}, "campaign_id": {"stringValue": "NEXT27-MAIN"},
                     "approver_role": {"stringValue": "Marketing Director"},
                     "summary": {"stringValue": "Setup test, please ignore"}, "amount": {"doubleValue": 18000}},
}


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


def build_version() -> dict:
    """The IntegrationVersion body: two API triggers, each starting one Data Mapping task."""
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
    return {
        "description": "Campaign Provisioner workflows: create purchase order, notify approver.",
        "integrationParameters": list(params.values()),
        "triggerConfigs": [_trigger(1, PO_TRIGGER, "1", PO_IN, PO_OUT),
                           _trigger(2, NOTIFY_TRIGGER, "2", NOTIFY_IN, NOTIFY_OUT)],
        "taskConfigs": [_mapping_task("1", "Build PO number", [po_number, execution_id]),
                        _mapping_task("2", "Mark approver notified", [status])],
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
                      json=build_version())
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
        print("\nRunning each trigger once with sample data ...")
        for trigger, params in SAMPLE.items():
            r = http.post(f"{base}:execute", json={"triggerId": trigger, "inputParameters": params})
            if r.status_code != 200:
                _fail(r, project)
            body = r.json()
            print(f"  {trigger}: failed={body.get('executionFailed', False)} outputs={body.get('outputParameters')}")
    print("\nApplication Integration OK. Set WORKFLOW_BACKEND=app_integration in .env.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--test", action="store_true", help="execute both triggers once with sample data")
    ap.add_argument("--check-only", action="store_true", help="check only; do not create anything")
    ap.add_argument("--provision-region", action="store_true",
                    help="one-time: enable Application Integration in this region (first use only)")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
