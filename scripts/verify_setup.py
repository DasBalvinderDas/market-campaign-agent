#!/usr/bin/env python3
"""Check that the BigQuery data is in place (and optionally the ADK connection to Application Integration).

  python scripts/verify_setup.py                  # BigQuery only
  python scripts/verify_setup.py --integration    # also lists the tools ADK generates from the integration

Assumes the APIs are enabled; if one is not, the script tells you which to enable.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402


@guarded
def run(args, project=""):
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    from campaign_provisioner import config
    from campaign_provisioner.repositories import get_repo

    repo = get_repo()
    print(f"Project: {project}\nBigQuery dataset: {repo.ds}")
    budgets = repo.list_budgets()
    if not budgets:
        sys.exit("No campaigns found. Run:  python scripts/setup_bigquery.py")
    print("\nCampaign budgets")
    for b in budgets:
        print(f"  {b['campaign_id']:<18} total {b['total_budget']:>10,.0f}  remaining {b['remaining']:>10,.0f}")
    print("\nSample stock")
    for sku in ("DEMO-KIOSK", "BOOTH-LEDWALL", "STICKER-PACK"):
        print(f"  {sku:<14} free {repo.get_availability(sku)['free']}")
    print("\nApproval tiers")
    for amount in (3000, 18000, 72000):
        p = repo.get_policy(amount)
        print(f"  ${amount:>6,}: {p['tier']:<10} -> {p['approver_role']}")
    print("\nApprover emails (who is notified)")
    for role in sorted({repo.get_policy(a)["approver_role"] for a in (18000, 72000)}):
        emails = repo.get_approver_emails(role)
        print(f"  {role:<36} {', '.join(emails) if emails else '(none: no email will be sent; run setup_bigquery.py --approver-email)'}")
    print("\nBigQuery OK")

    if args.integration:
        from google.adk.tools.application_integration_tool import ApplicationIntegrationToolset
        for trig in (config.PO_TRIGGER, config.NOTIFY_TRIGGER):
            ts = ApplicationIntegrationToolset(project=project, location=config.APP_INTEGRATION_LOCATION,
                                               integration=config.APP_INTEGRATION_NAME, triggers=[trig])
            print(f"Integration trigger {trig}: tools = {[t.name for t in asyncio.run(ts.get_tools())]}")
        print("\nApplication Integration OK (the guard matches tool names containing 'purchase_order' / 'notify')")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--integration", action="store_true")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
