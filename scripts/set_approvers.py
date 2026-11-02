#!/usr/bin/env python3
"""Set who approves and who gets notices. Changes ONLY the approvers table; nothing else is touched.

  python scripts/set_approvers.py a@x.com b@x.com        # these addresses for every role (VP Product Marketing, CMO, Launch Team)
  python scripts/set_approvers.py a@x.com --show         # just print the table
The table is replaced, so run it with every address you want. Safe to run twice.
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402

ROLES = ["VP Product Marketing", "CMO", "Launch Team"]
EMAIL = re.compile(r"^[^@\s,;'\"]+@[^@\s,;'\"]+\.[^@\s,;'\"]+$")


def build_rows(emails: list[str]) -> list[dict]:
    clean = []
    for e in emails:
        e = e.strip().lower()
        if not EMAIL.match(e):
            raise ValueError(f"'{e}' is not an email address.")
        if e not in clean:
            clean.append(e)
    if not clean:
        raise ValueError("Give at least one email address.")
    return [{"approver_role": r, "email": e, "active": True} for r in ROLES for e in clean]


@guarded
def run(args, project=""):
    from google.cloud import bigquery

    client = bigquery.Client(project=project, location=args.location)
    table = f"{project}.{args.dataset}.approvers"
    if not args.show:
        rows = build_rows(args.emails)
        cfg = bigquery.LoadJobConfig(
            schema=[bigquery.SchemaField("approver_role", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("email", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("active", "BOOL", mode="REQUIRED")],
            write_disposition="WRITE_TRUNCATE")
        client.load_table_from_json(rows, table, job_config=cfg).result()
        print(f"Wrote {len(rows)} rows ({len(rows) // len(ROLES)} address(es) for each of {len(ROLES)} roles).")
    for r in client.query(f"SELECT approver_role, email, active FROM `{table}` ORDER BY approver_role, email").result():
        print(f"  {r['approver_role']:<22} {r['email']}  {'active' if r['active'] else 'OFF'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("emails", nargs="*")
    ap.add_argument("--project", default=None)
    ap.add_argument("--dataset", default=os.getenv("BQ_DATASET", "launchkit"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--show", action="store_true", help="only print the table")
    a = ap.parse_args()
    if not a.show and not a.emails:
        ap.error("give the email addresses, or --show")
    run(a, project=resolve_project(a.project))
