#!/usr/bin/env python3
"""Create the bucket that holds one trigger file per request waiting for approval. Safe by default: it only shows what it would do.

  python scripts/setup_trigger_bucket.py                 # dry run
  python scripts/setup_trigger_bucket.py --yes           # create the bucket and let the agent write to it
  python scripts/setup_trigger_bucket.py --yes --test    # ...and write one test file

The bucket is private (uniform access, public access blocked). The agent's service account (AGENT_SERVICE_ACCOUNT in .env) gets
Storage Object Creator on this bucket only: it can add files, not read or delete them. Files are deleted after --keep-days.
Then add to .env:  APPROVAL_TRIGGER_BUCKET=<the bucket name>   and deploy again.
Needs the Cloud Storage API (storage.googleapis.com) and your account must be allowed to create buckets.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402


def plan(project: str, bucket: str, location: str, service_account: str, keep_days: int) -> list[str]:
    steps = [f"create bucket gs://{bucket} in {location} (private, uniform access, public access blocked)",
             f"delete files after {keep_days} days"]
    steps.append(f"let {service_account} create files in it (roles/storage.objectCreator on this bucket only)"
                 if service_account else "AGENT_SERVICE_ACCOUNT is empty: no permission is granted. Give the agent's account "
                                         "roles/storage.objectCreator on the bucket yourself")
    return steps


@guarded
def run(args, project=""):
    from google.cloud import storage

    env = {}
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    sa = args.service_account or env.get("AGENT_SERVICE_ACCOUNT", "")
    bucket_name = args.bucket or f"{project}-launchkit-approvals"
    print(f"Project {project}")
    for s in plan(project, bucket_name, args.location, sa, args.keep_days):
        print(f"  - {s}")
    if not args.yes:
        print("\nDry run. Add --yes to do it.")
        return
    client = storage.Client(project=project)
    bucket = client.lookup_bucket(bucket_name)
    if bucket is None:
        bucket = client.bucket(bucket_name)
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        bucket.iam_configuration.public_access_prevention = "enforced"
        bucket.add_lifecycle_delete_rule(age=args.keep_days)
        bucket = client.create_bucket(bucket, location=args.location)
        print(f"Created gs://{bucket_name}")
    else:
        print(f"gs://{bucket_name} already exists")
    if sa:
        policy = bucket.get_iam_policy(requested_policy_version=3)
        member = f"serviceAccount:{sa}"
        binding = next((b for b in policy.bindings if b["role"] == "roles/storage.objectCreator"), None)
        if binding is None:
            policy.bindings.append({"role": "roles/storage.objectCreator", "members": {member}})
        else:
            binding["members"].add(member)
        bucket.set_iam_policy(policy)
        print(f"{sa} can now add files")
    if args.test:
        blob = bucket.blob("approvals/TEST-" + os.urandom(3).hex() + ".json")
        blob.upload_from_string(json.dumps({"event": "test", "summary": "Test file from setup_trigger_bucket.py"}),
                                content_type="application/json")
        print(f"Wrote {blob.name}")
    print(f"\nAdd to .env:\n  APPROVAL_TRIGGER_BUCKET={bucket_name}\nthen: python scripts/deploy_agent_engine.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--bucket", default=None, help="default: <project>-launchkit-approvals")
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--service-account", default=None, help="default: AGENT_SERVICE_ACCOUNT from .env")
    ap.add_argument("--keep-days", type=int, default=30)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--test", action="store_true", help="also write one test file")
    a = ap.parse_args()
    run(a, project=resolve_project(a.project))
