#!/usr/bin/env python3
"""Deploy The Campaign Provisioner to Vertex AI Agent Engine (the final step).

  python scripts/deploy_agent_engine.py                 # create a new Agent Engine deployment
  python scripts/deploy_agent_engine.py --update ID     # redeploy new code to an existing one
  python scripts/deploy_agent_engine.py --dry-run       # run all checks and show the command, deploy nothing

What it does
  1. checks the APIs (Vertex AI, Cloud Build) and that BigQuery and the Application Integration workflow are
     already set up (run scripts/setup_all.py first)
  2. builds the runtime settings (BigQuery dataset, Application Integration name and region, model) from your .env
  3. runs `adk deploy agent_engine` on the campaign_provisioner folder
  4. saves the deployed resource name as AGENT_ENGINE_RESOURCE in .env and prints the permissions the deployed
     agent needs plus the command to talk to it (scripts/query_agent_engine.py)

Project id: --project, else GOOGLE_CLOUD_PROJECT, else your active gcloud project. Region: --region, else
GOOGLE_CLOUD_LOCATION from .env, else us-central1.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import guarded, preflight, resolve_project  # noqa: E402

RUNTIME_KEYS = ["BQ_DATASET", "BQ_LOCATION", "APP_INTEGRATION_NAME", "APP_INTEGRATION_LOCATION",
                "APP_INTEGRATION_PO_TRIGGER", "APP_INTEGRATION_NOTIFY_TRIGGER", "CAMPAIGN_MODEL"]
RESOURCE_RE = re.compile(r"projects/[^/\s]+/locations/[^/\s]+/reasoningEngines/\d+")


def read_env(path: Path) -> dict:
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def runtime_env(env_file_values: dict) -> dict:
    """Settings the deployed agent needs. The project and region are set by Agent Engine itself."""
    merged = {k: os.environ[k] for k in RUNTIME_KEYS if k in os.environ}
    merged.update({k: v for k, v in env_file_values.items() if k in RUNTIME_KEYS})
    return merged


def build_config(env: dict, service_account: str | None) -> dict:
    config = {"display_name": "campaign-provisioner",
              "description": "Google Next 2027 campaign logistics agent: BigQuery data, Application Integration "
                             "workflows, human approval for high-value spend.",
              "env_vars": env}
    if service_account:
        config["service_account"] = service_account
    return config


def deploy_command(project, region, config_path, agent_dir, update_id):
    cmd = ["adk", "deploy", "agent_engine", f"--project={project}", f"--region={region}",
           f"--agent_engine_config_file={config_path}"]
    if update_id:
        cmd.append(f"--agent_engine_id={update_id}")
    return cmd + [str(agent_dir)]


def iam_help(project: str) -> str:
    return f"""
Give the deployed agent permission to use your data and workflow. It runs as the Vertex AI Agent Engine service
agent (or your custom service account). Replace the member if you used --service-account:

  PROJECT_NUMBER=$(gcloud projects describe {project} --format='value(projectNumber)')
  MEMBER="serviceAccount:service-${{PROJECT_NUMBER}}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
  for ROLE in roles/bigquery.dataEditor roles/bigquery.jobUser \\
              roles/integrations.integrationInvoker roles/integrations.viewer roles/aiplatform.user; do
    gcloud projects add-iam-policy-binding {project} --member="$MEMBER" --role="$ROLE" --condition=None
  done

(To confirm the exact identity, open IAM in the console and tick "Include Google-provided role grants".)"""


@guarded
def run(args, project=""):
    region = args.region or read_env(ROOT / ".env").get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    print(f"Project: {project}   Region: {region}")

    if not args.skip_preflight:
        preflight(project, ["aiplatform.googleapis.com", "cloudbuild.googleapis.com"],
                  check_bigquery_permissions=False)

    stale = ROOT / "campaign_provisioner" / ".env"
    if stale.exists():
        sys.exit(f"\n{stale} exists. adk deploy reads a .env next to the agent and it would override the settings "
                 "below. Delete it (the repo-root .env is the one to use) and run this again.")

    if not args.skip_checks:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project
        from campaign_provisioner.repositories import get_repo
        budgets = get_repo().list_budgets()
        if not budgets:
            sys.exit("\nNo campaigns found in BigQuery. Run: python scripts/setup_all.py")
        print(f"  OK  BigQuery has {len(budgets)} campaigns")
        import setup_application_integration as ai
        ai.run_with(_Http(), argparse.Namespace(test=False, check_only=True, provision_region=False,
                                                no_email=False, test_email=None), project)

    env = runtime_env(read_env(ROOT / ".env"))
    config = build_config(env, args.service_account)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(config, f, indent=2)
        config_path = f.name
    cmd = deploy_command(project, region, config_path, ROOT / "campaign_provisioner", args.update)
    print("\nRuntime settings for the deployed agent:")
    for k, v in env.items():
        print(f"  {k}={v}")
    print("\nCommand:\n  " + " ".join(cmd))
    if args.dry_run:
        print("\n(dry run: nothing deployed)")
        return
    print("\nDeploying (this takes several minutes: it builds a container image) ...\n")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))
    output = []
    for line in proc.stdout:
        print(line, end="")
        output.append(line)
    proc.wait()
    text = "".join(output)
    explained = None
    if proc.returncode != 0:
        from _common import explain
        explained = explain(text, project)
        sys.exit(f"\n{explained}" if explained else
                 "\nDeployment failed (see the output above). If it mentions a missing module, run: "
                 'pip install "google-adk[gcp]"')
    found = RESOURCE_RE.findall(text)
    resource = found[-1] if found else None
    if resource:
        from setup_all import write_env
        write_env(ROOT / ".env", {"AGENT_ENGINE_RESOURCE": resource})
        print(f"\nSaved AGENT_ENGINE_RESOURCE={resource} to .env")
    print(iam_help(project))
    print("\nTalk to it (handles the human Confirm / Reject):\n"
          '  python scripts/query_agent_engine.py "NEXT27-MAIN needs 1 booth LED video wall."')


class _Http:
    """Authorised HTTP session created lazily so --skip-checks needs no credentials."""
    def __init__(self):
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self._s = AuthorizedSession(creds)

    def get(self, *a, **k):
        return self._s.get(*a, **k)

    def post(self, *a, **k):
        return self._s.post(*a, **k)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--region", default=None, help="Agent Engine region (default: GOOGLE_CLOUD_LOCATION or us-central1)")
    ap.add_argument("--update", default=None, metavar="ENGINE_ID", help="redeploy to an existing Agent Engine id")
    ap.add_argument("--service-account", default=None, help="run the agent as this service account instead of the default")
    ap.add_argument("--dry-run", action="store_true", help="run the checks and print the command, deploy nothing")
    ap.add_argument("--skip-checks", action="store_true", help="skip the BigQuery / Application Integration check")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
