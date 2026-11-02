#!/usr/bin/env python3
"""Set who approves and who gets notice emails. Changes ONLY the approvers table; nothing else is touched.

  python scripts/set_approvers.py NOTICE_EMAIL[=SIGNIN_EMAIL] [...]

  NOTICE_EMAIL  where notice emails go (approval waiting, orders placed)
  SIGNIN_EMAIL  the address the person signs in to Gemini Enterprise with. Only this address may approve.
                Leave it out when it is the same as the notice email.

Example (notices to hcltech.com, approvals by the labgtm.com sign-in):
  python scripts/set_approvers.py dasbalvinder.das@hcltech.com=dasbalvinder.das@labgtm.com

Every address is added to the roles VP Product Marketing, CMO and Launch Team. The Launch Team only gets emails.
The table is replaced, so run it with every address you want. Safe to run twice.
  python scripts/set_approvers.py --show     # just print the table
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
APPROVING = ("VP Product Marketing", "CMO")
EMAIL = re.compile(r"^[^@\s,;'\"=]+@[^@\s,;'\"=]+\.[^@\s,;'\"=]+$")


def _clean(address: str) -> str:
    address = address.strip().lower()
    if not EMAIL.match(address):
        raise ValueError(f"'{address}' is not an email address.")
    return address


def build_rows(specs: list[str]) -> list[dict]:
    pairs = []
    for spec in specs:
        notice, _, signin = spec.partition("=")
        pair = (_clean(notice), _clean(signin) if signin.strip() else None)
        if pair not in pairs:
            pairs.append(pair)
    if not pairs:
        raise ValueError("Give at least one email address.")
    return [{"approver_role": r, "email": notice, "active": True, "signin_email": signin if r in APPROVING else None}
            for r in ROLES for notice, signin in pairs]


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
                    bigquery.SchemaField("active", "BOOL", mode="REQUIRED"),
                    bigquery.SchemaField("signin_email", "STRING", mode="NULLABLE")],
            write_disposition="WRITE_TRUNCATE")
        client.load_table_from_json(rows, table, job_config=cfg).result()
        print(f"Wrote {len(rows)} rows.")
    print(f"  {'role':<22} {'notice email':<34} sign-in (approves)")
    for r in client.query(f"SELECT approver_role, email, signin_email, active FROM `{table}` ORDER BY approver_role, email").result():
        print(f"  {r['approver_role']:<22} {r['email']:<34} {r['signin_email'] or '-'}{'' if r['active'] else '  (OFF)'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("emails", nargs="*", metavar="NOTICE_EMAIL[=SIGNIN_EMAIL]")
    ap.add_argument("--project", default=None)
    ap.add_argument("--dataset", default=os.getenv("BQ_DATASET", "launchkit"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--show", action="store_true", help="only print the table")
    a = ap.parse_args()
    if not a.show and not a.emails:
        ap.error("give the email addresses, or --show")
    run(a, project=resolve_project(a.project))
