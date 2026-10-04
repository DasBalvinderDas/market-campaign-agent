#!/usr/bin/env python3
"""One command to set up everything: BigQuery data + Application Integration workflow + .env.

  python scripts/setup_all.py --approver-email "you@example.com"
  python scripts/setup_all.py --project my-proj \\
      --approver-email "Marketing Director=md@example.com,md2@example.com" \\
      --approver-email "VP Marketing + Finance Controller=vp@example.com,controller@example.com"

Configurable:
  --project           Google Cloud project (else GOOGLE_CLOUD_PROJECT, else your active gcloud project)
  --approver-email    who is emailed when a human must approve; [ROLE=]EMAIL[,EMAIL], repeatable
                      (else APPROVER_EMAILS, else your gcloud account)
  --dataset/--location/--region   BigQuery dataset, BigQuery location, Application Integration region

It assumes the APIs are already enabled. Before doing anything it checks them and your BigQuery permissions and
lists EVERYTHING that is missing in one message (which API to enable, which role to ask for). Safe to re-run.
"""
import argparse
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import preflight, resolve_project  # noqa: E402


def write_env(path: Path, updates: dict) -> None:
    """Set KEY=value lines in a .env file (create from .env.example if missing); other lines are untouched."""
    if not path.exists():
        src = ROOT / ".env.example"
        path.write_text(src.read_text() if src.exists() else "")
    lines, seen = path.read_text().splitlines(), set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip().lstrip("#").strip()
        if key in updates and "=" in line and (not line.lstrip().startswith("#") or key not in seen):
            lines[i] = f"{key}={updates[key]}"
            seen.add(key)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--approver-email", action="append", default=[], metavar="[ROLE=]EMAIL[,EMAIL]")
    ap.add_argument("--dataset", default=os.getenv("BQ_DATASET", "campaign_provisioner"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"), help="BigQuery location")
    ap.add_argument("--region", default=os.getenv("APP_INTEGRATION_LOCATION", "us-central1"),
                    help="Application Integration region")
    ap.add_argument("--no-email", action="store_true", help="do not add the Send Email task")
    ap.add_argument("--test", action="store_true", help="run both Application Integration triggers once (sends a test email)")
    ap.add_argument("--test-email", default=None)
    ap.add_argument("--no-env", action="store_true", help="do not write the .env files")
    args = ap.parse_args()

    os.environ["APP_INTEGRATION_LOCATION"] = args.region  # read by the integration script at import
    project = resolve_project(args.project)
    print(f"Project: {project}\n")

    preflight(project, ["bigquery.googleapis.com", "integrations.googleapis.com"],
              optional_apis=["aiplatform.googleapis.com"])

    import setup_application_integration as ai
    import setup_bigquery as bq

    results = {}

    def step(name, fn):
        print(f"== {name}")
        try:
            fn()
            results[name] = "OK"
        except SystemExit as exc:
            results[name] = "FAILED"
            if exc.code not in (0, None):
                print(exc.code if isinstance(exc.code, str) else f"(exit {exc.code})")
        print()

    bq_args = types.SimpleNamespace(dataset=args.dataset, location=args.location, reset=False, reset_demo=False,
                                    approver_email=args.approver_email, skip_preflight=True)
    step("BigQuery data", lambda: bq.run(bq_args, project=project))
    ai_args = types.SimpleNamespace(test=args.test, check_only=False, provision_region=False,
                                    no_email=args.no_email, test_email=args.test_email, skip_preflight=True)
    step("Application Integration", lambda: ai.run(ai_args, project=project))

    if not args.no_env and all(v == "OK" for v in results.values()):
        updates = {"GOOGLE_CLOUD_PROJECT": project, "BQ_DATASET": args.dataset, "BQ_LOCATION": args.location,
                   "APP_INTEGRATION_LOCATION": args.region}
        if args.approver_email:
            updates["APPROVER_EMAILS"] = ";".join(args.approver_email)
        for target in (ROOT / ".env", ROOT / "campaign_provisioner" / ".env"):
            write_env(target, updates)
        print("== .env\n  wrote .env and campaign_provisioner/.env (project, dataset, locations, approver emails)\n")

    print("Summary: " + ", ".join(f"{k}: {v}" for k, v in results.items()))
    if any(v != "OK" for v in results.values()):
        sys.exit("Some steps need attention (see messages above). Fix them and run this script again; finished steps are skipped.")
    print("\nNext: python scripts/verify_setup.py --integration   then   adk web")


if __name__ == "__main__":
    main()
