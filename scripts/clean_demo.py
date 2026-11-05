#!/usr/bin/env python3
"""Empty the demo's working data in BigQuery so you can test from a fresh start. Reference data stays.

  python scripts/clean_demo.py              # shows the row counts, asks you to type YES
  python scripts/clean_demo.py --yes        # no question
  python scripts/clean_demo.py --keep-campaigns   # keep the campaigns table (the Spring demo's standing campaigns)

Emptied: campaigns, requests, shopping lists, plans, sign-offs, held stock, orders, warehouse moves, delays and the audit log.
Kept: vendors, items, prices, stock, lanes, rules, approval levels, athletes and the approvers (notice emails and sign-ins).
Free stock comes back by itself: held stock lives in the emptied holds table.
The Gemini Enterprise Inbox is not touched: cancel old items there yourself.
To reload the Aether data from scratch instead, use scripts/setup_demo_aether.py.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402

from launchkit_provisioner.data.schema import TABLES, TRANSACTION_TABLES  # noqa: E402

KEEP = ("approvers", "guests")          # never emptied here


def tables_to_empty(keep_campaigns: bool = False) -> list[str]:
    names = list(TRANSACTION_TABLES) + ([] if keep_campaigns else ["launches"])
    return [n for n in names if n in TABLES and n not in KEEP]


@guarded
def run(args, project=""):
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    client = bigquery.Client(project=project, location=args.location)
    ds = f"{project}.{args.dataset}"
    names = tables_to_empty(args.keep_campaigns)
    print(f"Project {project}, dataset {args.dataset}\n")
    counts = {}
    for n in names:
        try:
            counts[n] = next(iter(client.query(f"SELECT COUNT(*) n FROM `{ds}.{n}`").result()))["n"]
        except NotFound:
            counts[n] = None
        print(f"  {n:<20} {'(missing, skipped)' if counts[n] is None else str(counts[n]) + ' rows'}")
    if not args.yes:
        if input(f"\nThis empties {sum(1 for c in counts.values() if c is not None)} tables above. Reference data and approvers stay. "
                 "Type YES to continue: ").strip() != "YES":
            sys.exit("Nothing was changed.")
    for n, c in counts.items():
        if c is not None:
            client.query(f"TRUNCATE TABLE `{ds}.{n}`").result()
    print("\nEmptied. Kept:")
    for n in ("approvers", "vendors", "assets", "depot_stock", "guests"):
        try:
            print(f"  {n:<20} {next(iter(client.query(f'SELECT COUNT(*) n FROM `{ds}.{n}`').result()))['n']} rows")
        except NotFound:
            print(f"  {n:<20} (missing)")
    print("\nOpen a new chat. Old items in the Gemini Enterprise Inbox are not removed: cancel them there.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--dataset", default=os.getenv("BQ_DATASET", "launchkit"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--keep-campaigns", action="store_true")
    a = ap.parse_args()
    run(a, project=resolve_project(a.project))
