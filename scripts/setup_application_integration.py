#!/usr/bin/env python3
"""Check (and optionally test) the Application Integration workflow the agent uses.

  python scripts/setup_application_integration.py          # is the integration there and published?
  python scripts/setup_application_integration.py --test   # also run both triggers once with sample data

Assumes the Application Integration API is already enabled and that you have created the integration
once in the console (3 minutes, see integration/README.md). If an API is not enabled this script tells
you which one to enable; if the integration or a trigger is missing it prints the exact checklist.

Project id: --project, else GOOGLE_CLOUD_PROJECT, else your active gcloud project.
"""
import argparse
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

CHECKLIST = f"""
Create it once in the console (Application Integration > Create integration):
  1. Name: {NAME}    Region: {LOCATION}
  2. Add an API Trigger with Trigger ID  create_purchase_order
       inputs : request_id, campaign_id, sku, vendor_id (String), quantity (Integer), total_amount (Double)
       outputs: po_number (String), execution_id (String)
       add a Data Mapping task that sets po_number (for example PO-<request_id>-<sku>)
  3. Add a second API Trigger with Trigger ID  notify_approver
       inputs : request_id, campaign_id, approver_role, summary (String), amount (Double)
       outputs: status (String)
       add a Send Email or Google Chat task (or leave it empty for the demo)
  4. Click Publish.
Then re-run this script.  Details: integration/README.md
"""

SAMPLE = {
    PO_TRIGGER: {"request_id": {"stringValue": "SETUP-TEST"}, "campaign_id": {"stringValue": "NEXT27-MAIN"},
                 "sku": {"stringValue": "BOOTH-LEDWALL"}, "quantity": {"intValue": "1"},
                 "vendor_id": {"stringValue": "V-EXPOVISION"}, "total_amount": {"doubleValue": 18000}},
    NOTIFY_TRIGGER: {"request_id": {"stringValue": "SETUP-TEST"}, "campaign_id": {"stringValue": "NEXT27-MAIN"},
                     "approver_role": {"stringValue": "Marketing Director"},
                     "summary": {"stringValue": "Setup test, please ignore"}, "amount": {"doubleValue": 18000}},
}


def _fail_http(resp, project):
    hint = explain(resp.text, project)
    sys.exit(f"\n{hint}" if hint else f"\nApplication Integration returned HTTP {resp.status_code}:\n{resp.text[:600]}")


@guarded
def run(args, project=""):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    http = AuthorizedSession(creds)
    base = f"https://integrations.googleapis.com/v1/projects/{project}/locations/{LOCATION}/integrations/{NAME}"
    print(f"Project: {project}   Integration: {NAME}   Region: {LOCATION}")

    resp = http.get(f"{base}/versions")
    if resp.status_code == 404:
        sys.exit(f"\nIntegration '{NAME}' was not found in {LOCATION}.\n{CHECKLIST}")
    if resp.status_code != 200:
        _fail_http(resp, project)

    versions = resp.json().get("integrationVersions", [])
    active = [v for v in versions if v.get("state") == "ACTIVE"]
    if not active:
        sys.exit(f"\nIntegration '{NAME}' exists but has no published (ACTIVE) version. Open it in the console and click Publish.")
    found = {t.get("triggerId") for v in active for t in v.get("triggerConfigs", [])}
    missing = [t for t in (PO_TRIGGER, NOTIFY_TRIGGER) if t not in found]
    if missing:
        sys.exit(f"\nThe published version is missing trigger(s): {', '.join(missing)}\n{CHECKLIST}")
    print(f"  OK  both triggers are published: {PO_TRIGGER}, {NOTIFY_TRIGGER}")

    if args.test:
        print("\nRunning each trigger once with sample data (this runs your real workflow, e.g. it may send an email)...")
        for trigger, params in SAMPLE.items():
            r = http.post(f"{base}:execute", json={"triggerId": trigger, "inputParameters": params})
            if r.status_code != 200:
                _fail_http(r, project)
            print(f"  {trigger}: {r.json().get('outputParameters', r.json())}")
    print("\nApplication Integration OK. Set WORKFLOW_BACKEND=app_integration in .env.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--test", action="store_true", help="execute both triggers once with sample data")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
