#!/usr/bin/env python3
"""Clean ALL data in the launchkit dataset and load the "Aether Athletics" live-demo data.

  python scripts/setup_demo_aether.py --preview            # show the three options the demo will produce (nothing is changed)
  python scripts/setup_demo_aether.py                       # wipe everything and load the Aether demo (asks first)
  python scripts/setup_demo_aether.py --yes                 # same, without asking
  python scripts/setup_demo_aether.py --yes --no-standing   # ONLY the Aether campaign (no London, US, Singapore campaigns)
  python scripts/setup_demo_aether.py --yes --in-hand-days 25
  python scripts/setup_demo_aether.py --yes --exact-dates   # the pack's own dates: in hand Oct 24 2026, embargo Nov 1 2026

What it does
  1. Empties EVERY table (requests, plans, decisions, orders, audit, campaigns, guests, items, vendors, prices, stock, lanes,
     rules and approval levels). The approver emails are kept: they decide who gets the approval and update emails.
  2. Loads the Aether data: the "Aether Strider Pro Global Marathon Launch" campaign (cost center CC-GLOBAL-BRAND-4410), the
     three standing campaigns (London, US, Singapore), 120 athletes with their sizes and handles, the 6 pack items with
     their vendors, prices and lead times, and the surplus stock (50 boxes in Boston, 100 cork folios in Portland, none left
     in Amsterdam).
  3. Dates are relative to today: in hand = today + --in-hand-days (default 20), embargo 8 days later. With 20 days the
     planned delivery keeps a 48-hour safety buffer. --exact-dates uses the pack's dates instead.

To go back to the original Spring demo data later:  python scripts/setup_bigquery.py --refresh-reference
(that command also restores the Spring campaign; the Aether data stays until you wipe it with this script).
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, preflight, resolve_project  # noqa: E402

from launchkit_provisioner.data import aether_data  # noqa: E402
from launchkit_provisioner.data.schema import TABLES  # noqa: E402

KEEP = {"approvers"}                         # never wiped


def preview(data: dict) -> list[dict]:
    """Plan the demo brief in memory (no BigQuery) and print the three options."""
    from launchkit_provisioner import planner, presentation
    from launchkit_provisioner.repositories.memory_repo import MemoryRepository

    repo = MemoryRepository()
    repo.t.update(data)
    for name in ("launch_requests", "requirement_lines", "scenarios", "scenario_lines", "decisions", "depot_holds",
                 "purchase_orders", "depot_transfers", "audit_log", "vendor_disruptions"):
        repo.t[name] = []
    rid = repo.create_request(aether_data.LAUNCH_ID, "preview")
    lines = planner.expand_bundles(repo, aether_data.LAUNCH_ID, [
        {"bundle_type": "GUEST_KIT", "quantity": 120, "region": "US"},
        {"bundle_type": "VENUE_DISPLAY", "quantity": 12, "region": "US"},
        {"bundle_type": "SALES_PACK", "quantity": 250, "region": "US"}])
    repo.replace_requirement_lines(rid, lines)
    scenarios, scenario_lines = planner.plan_scenarios(repo, rid)
    launch = repo.get_launch(aether_data.LAUNCH_ID)
    print(f"Campaign: {launch['launch_name']}  |  in hand by {launch['in_hand_by']}  |  embargo {launch['embargo_date']}")
    print(f"Brief: 120 athlete kits, 12 podiums, 250 cork folios ({sum(x['quantity'] for x in lines):,} items in total)\n")
    for s in scenarios:
        saving = (f"saves {presentation.money(s['savings_usd'])}" if s["savings_usd"] > 0 else
                  f"{presentation.money(-s['savings_usd'])} more" if s["savings_usd"] < 0 else "baseline")
        print(f"  {s['option_name']:<42} {presentation.money(s['total_cost']):>11}  {saving:<16}"
              f"  arrives {s['delivery_date']}  buffer {s['buffer_hours']:>3}h  {'<- recommended' if s['recommended'] else ''}")
    best = next(s for s in scenarios if s["recommended"])
    own = sum(x["quantity"] for x in scenario_lines if x["scenario_id"] == best["scenario_id"] and x["source_type"] == "DEPOT")
    print(f"\n  Recommended option uses {own} items from our own warehouses.")
    return scenarios


@guarded
def run(args, project=""):
    from google.cloud import bigquery

    import setup_bigquery as sb

    data = aether_data.build(date.today(), args.in_hand_days, args.exact_dates, standing=not args.no_standing)
    print(f"Project: {project}   Dataset: {args.dataset}\n")
    preview(data)
    if args.preview:
        return
    if not args.skip_preflight:
        preflight(project, ["bigquery.googleapis.com"])
    if not args.yes:
        print(f"\nThis EMPTIES every table in {project}.{args.dataset} (except the approver emails) and loads the Aether demo.")
        if input("Type YES to continue: ").strip() != "YES":
            sys.exit("Nothing was changed.")

    client = bigquery.Client(project=project, location=args.location)
    ds = f"{project}.{args.dataset}"
    client.create_dataset(bigquery.Dataset(ds), exists_ok=True)
    client.query(sb.ddl(ds)).result()                      # tables and views that are missing
    print("\nCleaning:")
    for name in TABLES:
        if name in KEEP:
            continue
        client.query(f"TRUNCATE TABLE `{ds}.{name}`").result()
    print(f"  emptied {len([t for t in TABLES if t not in KEEP])} tables (approvers kept)")

    print("Loading the Aether demo:")
    for name, rows in data.items():
        t = TABLES[name]
        cfg = bigquery.LoadJobConfig(
            schema=[bigquery.SchemaField(c, typ, mode=mode) for c, typ, mode, _ in t["columns"]],
            write_disposition="WRITE_TRUNCATE")
        client.load_table_from_json(sb._json_rows(rows), f"{ds}.{name}", job_config=cfg).result()
        print(f"  {len(rows):>4} rows into {name}")

    n = next(iter(client.query(f"SELECT COUNT(*) n FROM `{ds}.approvers`").result()))["n"]
    if not n:
        print("\nWARNING: no approver emails are set, so no approval email will be sent. Run:\n"
              "  python scripts/setup_bigquery.py --approver-email \"you@example.com\"")
    print("\nDone. The agent needs no redeploy. Open a NEW chat and try:\n"
          "  Hi  ->  Add to the Aether Strider Pro campaign  ->  120 people, USA  ->  use the suggested plan\n"
          "Details and the talk-track: docs/DEMO_AETHER.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--dataset", default=os.getenv("BQ_DATASET", "launchkit"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--in-hand-days", type=int, default=aether_data.IN_HAND_DAYS,
                    help="days from today until everything must be in hand (default 20)")
    ap.add_argument("--exact-dates", action="store_true", help="use the pack's dates (in hand 24 Oct 2026, embargo 1 Nov 2026)")
    ap.add_argument("--no-standing", action="store_true",
                    help="do not keep the London, US and Singapore campaigns: the Aether campaign is the only one")
    ap.add_argument("--preview", action="store_true", help="only show what the demo will produce; change nothing")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--skip-preflight", action="store_true")
    a = ap.parse_args()
    if a.preview:
        run(a, project=a.project or "(preview)")
    else:
        run(a, project=resolve_project(a.project))
