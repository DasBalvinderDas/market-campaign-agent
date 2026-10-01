#!/usr/bin/env python3
"""Smoke-test the BigQuery data and (optionally) the Application Integration connection.

  python scripts/verify_setup.py                  # BigQuery only
  python scripts/verify_setup.py --integration    # also builds the ADK toolset and lists generated tool names
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DATA_BACKEND", "bigquery")

from campaign_provisioner import config  # noqa: E402
from campaign_provisioner.repositories import get_repo  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--integration", action="store_true")
    args = ap.parse_args()

    if config.DATA_BACKEND != "bigquery":
        sys.exit("DATA_BACKEND must be 'bigquery' for this check")
    repo = get_repo()
    print(f"BigQuery dataset: {repo.ds}")
    budgets = repo.list_budgets()
    assert budgets, "No campaigns found - run scripts/setup_bigquery.py first"
    print("\nCampaign budgets")
    for b in budgets:
        print(f"  {b['campaign_id']:<18} total {b['total_budget']:>10,.0f}  remaining {b['remaining']:>10,.0f}")
    print("\nSample stock")
    for sku in ("DEMO-KIOSK", "BOOTH-LEDWALL", "STICKER-PACK"):
        a = repo.get_availability(sku)
        print(f"  {sku:<14} free {a['free']}")
    print("\nApproval tiers")
    for amount in (3000, 18000, 72000):
        p = repo.get_policy(amount)
        print(f"  ${amount:>6,}: {p['tier']:<10} -> {p['approver_role']}")
    print("\nBigQuery OK")

    if args.integration:
        from google.adk.tools.application_integration_tool import ApplicationIntegrationToolset
        for trig in (config.PO_TRIGGER, config.NOTIFY_TRIGGER):
            ts = ApplicationIntegrationToolset(project=config.PROJECT, location=config.APP_INTEGRATION_LOCATION,
                                               integration=config.APP_INTEGRATION_NAME, triggers=[trig])
            tools = asyncio.run(ts.get_tools())
            print(f"Integration trigger {trig}: tools = {[t.name for t in tools]}")
        print("\nApplication Integration OK (the guard matches tool names containing 'purchase_order' / 'notify')")


if __name__ == "__main__":
    main()
