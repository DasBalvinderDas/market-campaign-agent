#!/usr/bin/env python3
"""Clean ALL data in the launchkit dataset and load the "Aether Athletics" demo data: vendors and the items they hold.

  python scripts/setup_demo_aether.py --preview     # show what the demo will produce (nothing is changed)
  python scripts/setup_demo_aether.py               # wipe everything and load the Aether data (asks first)
  python scripts/setup_demo_aether.py --yes         # same, without asking

What it does
  1. Empties EVERY table (campaigns, requests, plans, decisions, orders, audit, guests, items, vendors, prices, stock, lanes,
     rules and approval levels). The approver emails are kept: they decide who gets the approval and update emails.
  2. Loads the Aether data: the vendors, the items they hold with price and lead time, our own warehouses and stock
     (50 boxes in Boston, 100 cork folios in Portland, none left in Amsterdam), the delivery places, the packs
     (athlete seeding kit, display podium, buyer folio) and a standing list of 120 athletes with their sizes.
  3. NO campaign is created. Start the demo in the chat: create "Aether Strider Pro Global Marathon Launch" there (see docs/DEMO_AETHER.md).

To go back to the original Spring demo data later:  python scripts/setup_bigquery.py --refresh-reference
"""
import argparse
import copy
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, preflight, resolve_project  # noqa: E402

from launchkit_provisioner.data import aether_data  # noqa: E402
from launchkit_provisioner.data.schema import TABLES  # noqa: E402

KEEP = {"approvers"}                         # never wiped
SAMPLE_DAYS = 9                              # the sample campaign of the preview is in hand this many days from today (like 15 to 24 Oct)


def preview(data: dict) -> list[dict]:
    """Plan a sample brief in memory (no BigQuery, nothing is stored) and print the three options."""
    from launchkit_provisioner import planner, presentation
    from launchkit_provisioner.repositories.memory_repo import MemoryRepository

    repo = MemoryRepository()
    repo.t.update(copy.deepcopy(data))          # a copy: the sample campaign below must never reach what is loaded
    for name in ("launch_requests", "requirement_lines", "scenarios", "scenario_lines", "decisions", "depot_holds",
                 "purchase_orders", "depot_transfers", "audit_log", "vendor_disruptions"):
        repo.t[name] = []
    repo.create_launch({"launch_id": "SAMPLE", "launch_name": aether_data.CAMPAIGN_NAME, "product_name": "Aether Strider Pro",
                        "cost_center": aether_data.COST_CENTER, "owner": "Global Brand & Athletic Marketing",
                        "in_hand_by": date.today() + timedelta(days=SAMPLE_DAYS),
                        "embargo_date": date.today() + timedelta(days=SAMPLE_DAYS + 8)})
    rid = repo.create_request("SAMPLE", "preview")
    lines = planner.expand_bundles(repo, "SAMPLE", [
        {"bundle_type": "GUEST_KIT", "quantity": 120, "region": "US"},
        {"bundle_type": "VENUE_DISPLAY", "quantity": 12, "region": "US"},
        {"bundle_type": "SALES_PACK", "quantity": 250, "region": "US"}])
    repo.replace_requirement_lines(rid, lines)
    scenarios, scenario_lines = planner.plan_scenarios(repo, rid)
    print(f"Sample campaign (not stored): {aether_data.CAMPAIGN_NAME}, in hand {SAMPLE_DAYS} days from today")
    print(f"Brief: 120 athlete kits, 12 podiums, 250 cork folios ({sum(x['quantity'] for x in lines):,} items in total)\n")
    for s in scenarios:
        saving = (f"saves {presentation.money(s['savings_usd'])}" if s["savings_usd"] > 0 else
                  f"{presentation.money(-s['savings_usd'])} more" if s["savings_usd"] < 0 else "baseline")
        print(f"  {s['option_name']:<42} {presentation.money(s['total_cost']):>11}  {saving:<16}"
              f"  arrives {s['delivery_date']}  buffer {s['buffer_hours']:>3}h  {'<- recommended' if s['recommended'] else ''}")
    best = next(s for s in scenarios if s["recommended"])
    own = sum(x["quantity"] for x in scenario_lines if x["scenario_id"] == best["scenario_id"] and x["source_type"] == "DEPOT")
    print(f"\n  The recommended option uses {own} items from our own warehouses.")
    return scenarios


@guarded
def run(args, project=""):
    from google.cloud import bigquery

    import setup_bigquery as sb

    data = aether_data.build()
    print(f"Project: {project}   Dataset: {args.dataset}\n")
    preview(data)
    if args.preview:
        return
    if not args.skip_preflight:
        preflight(project, ["bigquery.googleapis.com"])
    if not args.yes:
        print(f"\nThis EMPTIES every table in {project}.{args.dataset} (except the approver emails) and loads the Aether demo data.")
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

    print("Loading the Aether demo data:")
    for name, rows in data.items():
        if not rows:
            print(f"  {0:>4} rows into {name} (left empty)")
            continue
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
    print("\nDone. No campaign exists yet. Open a NEW chat and paste the brief from docs/DEMO_AETHER.md\n"
          "(120 VIP athlete kits, 12 display podiums, 250 buyer kits, cost center CC-GLOBAL-BRAND-4410, in hand 24 Oct).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--dataset", default=os.getenv("BQ_DATASET", "launchkit"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--preview", action="store_true", help="only show what the demo will produce; change nothing")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--skip-preflight", action="store_true")
    a = ap.parse_args()
    if a.preview:
        run(a, project=a.project or "(preview)")
    else:
        run(a, project=resolve_project(a.project))
