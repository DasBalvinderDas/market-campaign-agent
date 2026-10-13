#!/usr/bin/env python3
"""Create the private Cloud Storage bucket that hands the order pack PDF to the email workflow.

  python scripts/setup_order_pack_bucket.py                    # bucket from ORDER_PACK_BUCKET in .env, else <project>-launchkit-order-packs
  python scripts/setup_order_pack_bucket.py --bucket my-bucket

Nobody gets a link: the bucket is private, files are deleted after 2 days, and the emails carry the PDF as an attachment.
It lets the agent's service account (AGENT_SERVICE_ACCOUNT) write files and the Application Integration service agent read
them. Safe to re-run. Needs the Cloud Storage API (storage.googleapis.com).
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, resolve_project  # noqa: E402


def _run(*cmd):
    return subprocess.run(list(cmd), capture_output=True, text=True)


def _number(project: str) -> str:
    return _run("gcloud", "projects", "describe", project, "--format=value(projectNumber)").stdout.strip()


def configured_bucket(project: str) -> str:
    """--bucket wins, else ORDER_PACK_BUCKET (environment or the .env file), else <project>-launchkit-order-packs."""
    import os
    if os.getenv("ORDER_PACK_BUCKET"):
        return os.environ["ORDER_PACK_BUCKET"]
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ORDER_PACK_BUCKET=") and line.split("=", 1)[1].strip():
                return line.split("=", 1)[1].strip()
    return f"{project}-launchkit-order-packs"


@guarded
def run(args, project=""):
    import os
    bucket = args.bucket or configured_bucket(project)
    sa = args.service_account or os.getenv("AGENT_SERVICE_ACCOUNT", "")
    uri = f"gs://{bucket}"
    print(f"Project: {project}\nBucket:  {uri}")
    if _run("gcloud", "storage", "buckets", "describe", uri, "--project", project).returncode == 0:
        print("  OK  bucket already exists")
    else:
        r = _run("gcloud", "storage", "buckets", "create", uri, "--project", project, "--location", args.location,
                 "--uniform-bucket-level-access", "--public-access-prevention")
        if r.returncode:
            sys.exit(f"Could not create the bucket:\n{r.stderr}\nEnable the API with:  gcloud services enable "
                     f"storage.googleapis.com --project {project}")
        print("  OK  bucket created (private)")
    lifecycle = Path("/tmp/launchkit_pack_lifecycle.json")
    lifecycle.write_text('{"rule":[{"action":{"type":"Delete"},"condition":{"age":2}}]}')
    _run("gcloud", "storage", "buckets", "update", uri, f"--lifecycle-file={lifecycle}")
    print("  OK  files are deleted after 2 days")
    grants = []
    if sa:
        grants.append((f"serviceAccount:{sa}", "roles/storage.objectAdmin", "the agent can write the PDF"))
    num = _number(project)
    if num:
        grants.append((f"serviceAccount:service-{num}@gcp-sa-integrations.iam.gserviceaccount.com",
                       "roles/storage.objectViewer", "the email workflow can read the PDF"))
        grants.append((f"serviceAccount:{num}-compute@developer.gserviceaccount.com", "roles/storage.objectViewer",
                       "the default workflow account can read the PDF"))
    for member, role, why in grants:
        r = _run("gcloud", "storage", "buckets", "add-iam-policy-binding", uri, f"--member={member}", f"--role={role}")
        print(f"  {'OK ' if not r.returncode else 'WARN'} {why}" + ("" if not r.returncode else f" (could not grant: {r.stderr.strip()[:150]})"))
    env = Path(__file__).resolve().parent.parent / ".env"
    text = env.read_text() if env.exists() else ""
    lines = [x for x in text.splitlines() if not x.startswith("ORDER_PACK_BUCKET=")]
    env.write_text("\n".join(lines + [f"ORDER_PACK_BUCKET={bucket}"]) + "\n")
    print(f"\nDone. ORDER_PACK_BUCKET={bucket} saved in .env. Next: republish the workflows and redeploy the agent.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    ap.add_argument("--bucket")
    ap.add_argument("--location", default="US")
    ap.add_argument("--service-account", default=None)
    a = ap.parse_args()
    run(a, project=resolve_project(a.project))
