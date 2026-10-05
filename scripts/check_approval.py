#!/usr/bin/env python3
"""Show what Application Integration says about an approval, to debug "approved but the agent still says pending".

  python scripts/check_approval.py              # the latest approval
  python scripts/check_approval.py REQ-1234ABCD # a given request
Prints the approval row from BigQuery, the execution (state and parameters) and its approval records.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402


@guarded
def run(args, project=""):
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    from campaign_provisioner.repositories import get_repo
    from campaign_provisioner.workflow.integration_client import IntegrationExecutor

    repo = get_repo()
    if args:
        row = repo.get_approval_for_request(args[0])
    else:
        rows = repo._run("SELECT request_id FROM `{ds}.approval_requests` ORDER BY created_at DESC LIMIT 1")
        row = repo.get_approval_for_request(rows[0]["request_id"]) if rows else None
    if not row:
        sys.exit("No approval found in BigQuery (table approval_requests).")
    print("Approval row:", json.dumps({k: str(v) for k, v in row.items() if k != "plan"}, indent=2))
    note = str(row.get("decision_note") or "")
    if not note.startswith("execution:"):
        sys.exit("\nNo workflow execution id stored on this approval (the status is final or the workflow never started).")
    ex_id, ex = note.split(":", 1)[1], IntegrationExecutor()
    print("\nExecution", ex_id)
    print(json.dumps(ex.get_execution(ex_id), indent=2, default=str)[:6000])
    print("\nApproval records (suspensions)")
    print(json.dumps(ex.list_suspensions(ex_id), indent=2, default=str)[:3000])


if __name__ == "__main__":
    run(sys.argv[1:], project=resolve_project(None))
