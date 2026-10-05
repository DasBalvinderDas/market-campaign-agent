#!/usr/bin/env python3
"""Deploy the approval-link service (Cloud Run): the page behind the Approve / Reject links in the approval email.

  python scripts/deploy_approval_service.py             # deploy (or update) the service
  python scripts/deploy_approval_service.py --dry-run   # checks and shows what it would do

Run it once, BEFORE deploying the agent. It
  1. generates APPROVAL_LINK_SECRET (the key that signs the links) if .env has none, and saves it to .env
  2. deploys the service to Cloud Run as your service account (AGENT_SERVICE_ACCOUNT / --service-account), publicly
     reachable: approvers need no Google login. The links are protected by the signed token, not by a login.
  3. saves its URL as APPROVAL_BASE_URL in .env. From then on the agent sends approvers an email with the links.

Assumes the Cloud Run, Cloud Build and Artifact Registry APIs are enabled; if not, it tells you which to enable.
Project: --project, else GOOGLE_CLOUD_PROJECT, else your active gcloud project.
"""
import argparse
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, preflight, resolve_project  # noqa: E402

SERVICE = "approval-callback"
ENV_KEYS = ["BQ_DATASET", "BQ_LOCATION", "APP_INTEGRATION_NAME", "APP_INTEGRATION_LOCATION",
            "APP_INTEGRATION_PO_TRIGGER", "APP_INTEGRATION_NOTIFY_TRIGGER", "APPROVAL_LINK_TTL_HOURS"]


def read_env(path: Path) -> dict:
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def stage(dest: Path) -> None:
    """The folder Cloud Run builds from: the service, the shared package, requirements and the start command."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".env", "tests")
    shutil.copytree(ROOT / "approval_service", dest / "approval_service", ignore=ignore)
    shutil.copytree(ROOT / "campaign_provisioner", dest / "campaign_provisioner", ignore=ignore)
    shutil.copy(ROOT / "approval_service" / "requirements.txt", dest / "requirements.txt")
    (dest / "Procfile").write_text("web: gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 120 "
                                   "approval_service.main:app\n")


def service_env(project: str, env_file: dict, secret: str) -> dict:
    env = {"GOOGLE_CLOUD_PROJECT": project, "APPROVAL_LINK_SECRET": secret}
    env.update({k: v for k, v in env_file.items() if k in ENV_KEYS})
    return env


def env_yaml(env: dict) -> str:
    return "".join(f"{k}: {json.dumps(v)}\n" for k, v in env.items())


def deploy_command(project, region, stage_dir, env_file_path, service_account):
    cmd = ["gcloud", "run", "deploy", SERVICE, f"--source={stage_dir}", f"--region={region}", f"--project={project}",
           "--allow-unauthenticated", f"--env-vars-file={env_file_path}", "--quiet"]
    if service_account:
        cmd.append(f"--service-account={service_account}")
    return cmd


def advice(output: str, project: str, service_account: str | None) -> str | None:
    low = output.lower()
    if "iam.allowedpolicymemberdomains" in low or "allusers" in low and "policy" in low:
        return ("Your organisation does not allow public Cloud Run services (an organisation policy blocks `allUsers`). "
                "The approval links need a public address, so an admin must allow it for this service/project "
                "(constraint iam.allowedPolicyMemberDomains), or use another way to reach approvers.")
    if "actas" in low or "iam.serviceaccounts.actas" in low:
        return (f"Your account needs the Service Account User role on {service_account or 'the service account'} to deploy "
                "a service that runs as it. Ask an admin: gcloud iam service-accounts add-iam-policy-binding "
                f"{service_account} --member=user:<you> --role=roles/iam.serviceAccountUser")
    if "run.services.setiampolicy" in low or "setiampolicy" in low:
        return ("Making the service public needs the Cloud Run Admin role. Ask an admin to run:\n"
                f"  gcloud run services add-iam-policy-binding {SERVICE} --region=<region> --project={project} "
                "--member=allUsers --role=roles/run.invoker")
    return None


@guarded
def run(args, project=""):
    env_path = ROOT / ".env"
    env_file = read_env(env_path)
    region = args.region or env_file.get("APPROVAL_SERVICE_REGION") or env_file.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    service_account = args.service_account or env_file.get("AGENT_SERVICE_ACCOUNT") or None
    print(f"Project: {project}   Region: {region}   Runs as: {service_account or '(default Cloud Run identity)'}")

    if not args.skip_preflight:
        preflight(project, ["run.googleapis.com", "cloudbuild.googleapis.com", "artifactregistry.googleapis.com"],
                  check_bigquery_permissions=False)

    secret = env_file.get("APPROVAL_LINK_SECRET")
    if not secret:
        secret = secrets.token_urlsafe(32)
        print("  generated APPROVAL_LINK_SECRET (the key that signs approval links)")
    env = service_env(project, env_file, secret)
    tmp = Path(tempfile.mkdtemp(prefix="approval_svc_"))
    try:
        stage_dir = tmp / "src"
        stage(stage_dir)
        env_path_yaml = tmp / "env.yaml"
        env_path_yaml.write_text(env_yaml(env))
        cmd = deploy_command(project, region, stage_dir, env_path_yaml, service_account)
        print("\nCommand:\n  " + " ".join(cmd))
        if args.dry_run:
            print("\n(dry run: nothing deployed)")
            return
        print("\nDeploying (a few minutes: Google builds a container image) ...\n")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = (proc.stdout or "") + (proc.stderr or "")
        print(out)
        if proc.returncode != 0:
            from _common import explain
            hint = advice(out, project, service_account) or explain(out, project)
            sys.exit(f"\n{hint}" if hint else "\nThe approval service was not deployed (see the output above).")
        url = subprocess.run(["gcloud", "run", "services", "describe", SERVICE, f"--region={region}",
                              f"--project={project}", "--format=value(status.url)"],
                             capture_output=True, text=True).stdout.strip()
        if not url:
            sys.exit("\nDeployed, but the service URL could not be read. Run: gcloud run services describe "
                     f"{SERVICE} --region={region} and set APPROVAL_BASE_URL in .env to its URL.")
        from setup_all import write_env
        write_env(env_path, {"APPROVAL_LINK_SECRET": secret, "APPROVAL_BASE_URL": url,
                             "APPROVAL_SERVICE_REGION": region})
        print(f"\nApproval service ready: {url}\nSaved APPROVAL_BASE_URL and APPROVAL_LINK_SECRET to .env.")
        print("Next: python scripts/deploy_agent_engine.py   (the agent now emails Approve / Reject links)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--region", default=None)
    ap.add_argument("--service-account", default=None, help="run the service as this account (default: AGENT_SERVICE_ACCOUNT)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
