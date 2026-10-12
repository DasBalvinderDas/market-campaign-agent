#!/usr/bin/env python3
"""Check that the BigQuery data is in place (and optionally the ADK connection to Application Integration).

  python scripts/verify_setup.py                  # BigQuery only
  python scripts/verify_setup.py --integration    # also checks that the four Application Integration workflows are published

Assumes the APIs are enabled; if one is not, the script tells you which to enable.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402


@guarded
def run(args, project=""):
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    from launchkit_provisioner import config
    from launchkit_provisioner.data.schema import TABLES
    from launchkit_provisioner.repositories import get_repo

    repo = get_repo()
    print(f"Project: {project}\nBigQuery dataset: {repo.ds}")
    have = {t.table_id for t in repo.client.list_tables(repo.ds)}
    missing = [t for t in TABLES if t not in have]
    if missing:
        sys.exit(f"BigQuery tables missing: {', '.join(missing)}. Run:  python scripts/setup_bigquery.py")
    launches = repo.list_launches()
    if not launches:
        sys.exit("No launches found. Run:  python scripts/setup_bigquery.py")
    print("\nLaunches")
    for x in launches:
        print(f"  {x['launch_id']:<16} {x['launch_name']}: in hand by {x['in_hand_by']}, embargo {x['embargo_date']}")
    print("\nSurplus stock in regional depots (free units)")
    for d in repo.list_depot_free():
        print(f"  {d['depot_name']:<28} {d['sku']:<20} {d['free']:>4}")
    items, offers, vendors = repo.list_assets(), repo.list_vendor_offers_all(), repo.list_vendors()
    print(f"\nOffer catalog: {len(items)} items, {len(vendors)} vendors, {len(offers)} price offers "
          f"(if these are lower than expected run: python scripts/setup_bigquery.py --refresh-reference)")
    print("\nGuests on the seeding list:", sum(m["n"] for m in repo.guest_mix(launches[0]["launch_id"])))
    print("Planning rules:", ", ".join(f"{k}={v:g}" for k, v in sorted(repo.get_planning_rules().items())))
    print("\nSign-off tiers")
    for p in repo.list_policies():
        top = "and above" if p["max_amount"] > 1e11 else f"to ${p['max_amount']:,.0f}"
        print(f"  {p['tier']:<12} from ${p['min_amount']:>8,.0f} {top:<14} -> {p['approver_role']}")
    print("\nApprover emails (sign-off and tracking updates)")
    for role in sorted({p["approver_role"] for p in repo.list_policies() if p["requires_human"]} | {"Launch Team"}):
        emails = repo.get_approver_emails(role)
        print(f"  {role:<24} {', '.join(emails) if emails else '(none: run setup_bigquery.py --approver-email)'}")
    print("\nBigQuery OK")

    if args.integration:
        import setup_application_integration as ai
        ai.run_with(_Http(), argparse.Namespace(test=False, check_only=True, provision_region=False, no_email=False,
                                                test_email=None, approver_email=[], republish=False), project)
        print("\nApplication Integration OK (all four workflows are published)")


class _Http:
    """Authorised session for the integration check."""

    def __init__(self):
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self._s = AuthorizedSession(creds)

    def get(self, url, **kw):
        return self._s.get(url, **kw)

    def post(self, url, **kw):
        return self._s.post(url, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--integration", action="store_true")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
