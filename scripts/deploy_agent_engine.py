#!/usr/bin/env python3
"""Deploy The Campaign Provisioner to Vertex AI Agent Engine (the final step).

  python scripts/deploy_agent_engine.py                 # create a new Agent Engine deployment
  python scripts/deploy_agent_engine.py                 # first time: creates; afterwards: updates the saved one
  python scripts/deploy_agent_engine.py --new           # create a separate new deployment
  python scripts/deploy_agent_engine.py --dry-run       # run all checks and show the command, deploy nothing

What it does
  1. checks the APIs (Vertex AI, Cloud Build) and that BigQuery and the Application Integration workflow are
     already set up (run `source scripts/env_setup.sh` first; add --approver-email to create them)
  2. builds the runtime settings (BigQuery dataset, Application Integration name and region, model) from your .env
  3. gives the deployed agent's identity the roles it needs (BigQuery, Application Integration, Vertex AI); if
     you are not allowed to, it prints who must grant what
  4. runs `adk deploy agent_engine` on the campaign_provisioner folder (retries once if the identity only
     existed after the first attempt)
  5. saves the deployed resource name as AGENT_ENGINE_RESOURCE in .env, asks the deployed agent a read-only
     test question (if it fails, the deployment's logs are printed), and prints the command to talk to it
     (scripts/query_agent_engine.py)

Nothing manual: problems are printed on the console with what to do, they are not raised as stack traces.

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


def pick_update_id(args, env_values: dict) -> str | None:
    """Which existing Agent Engine to update: --update ID, else the one saved in .env, unless --new."""
    if args.new:
        return None
    if args.update and args.update != "auto":
        return args.update.rstrip("/").split("/")[-1]
    saved = env_values.get("AGENT_ENGINE_RESOURCE")
    if saved and RESOURCE_RE.fullmatch(saved):
        return saved.split("/")[-1]
    if args.update == "auto":
        print("  NOTE: --update given but no AGENT_ENGINE_RESOURCE is saved in .env, so a new deployment is created.")
    return None


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


BASE_ROLES = ["roles/bigquery.dataEditor", "roles/bigquery.jobUser", "roles/aiplatform.user",
              "roles/integrations.integrationInvoker"]
# The agent reads the integration definition when it first needs its tools (ADK calls generateOpenApiSpec).
# Which predefined role contains that permission is looked up at run time; these are tried least-privileged first.
READ_ROLE_CANDIDATES = ["roles/integrations.integrationViewer", "roles/integrations.integrationEditor",
                        "roles/integrations.integrationAdmin"]
SPEC_PERMISSION_HINT = "generateopenapispec"
RUNTIME_ROLES = BASE_ROLES + [READ_ROLE_CANDIDATES[0]]  # default when the lookup is not possible


def role_permissions(role: str) -> set[str] | None:
    r = subprocess.run(["gcloud", "iam", "roles", "describe", role, "--format=value(includedPermissions)"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {p.strip() for p in r.stdout.replace(";", "\n").splitlines() if p.strip()}


def choose_runtime_roles() -> list[str]:
    """BASE_ROLES plus the least-privileged Application Integration role that can read the integration."""
    for role in READ_ROLE_CANDIDATES:
        perms = role_permissions(role)
        if perms and any(SPEC_PERMISSION_HINT in p.lower() for p in perms):
            return BASE_ROLES + [role]
    print("  NOTE: could not look up which role lets the agent read the integration; granting "
          f"{READ_ROLE_CANDIDATES[1]} to be safe.")
    return BASE_ROLES + [READ_ROLE_CANDIDATES[1]]


def runtime_member(project: str, service_account: str | None) -> str | None:
    """The identity the deployed agent runs as."""
    if service_account:
        return f"serviceAccount:{service_account}"
    r = subprocess.run(["gcloud", "projects", "describe", project, "--format=value(projectNumber)"],
                       capture_output=True, text=True)
    number = r.stdout.strip()
    if r.returncode != 0 or not number:
        return None
    return f"serviceAccount:service-{number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"


def granted_roles(project: str, member: str) -> set[str] | None:
    """Roles the member already has on the project (None if the policy cannot be read)."""
    r = subprocess.run(["gcloud", "projects", "get-iam-policy", project, "--format=json"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        bindings = json.loads(r.stdout).get("bindings", [])
    except ValueError:
        return None
    return {b["role"] for b in bindings if member in b.get("members", [])}


def write_admin_script(project: str, member: str, roles: list[str]) -> Path:
    """A ready-to-run script for someone who is allowed to change IAM (Project IAM Admin / Owner)."""
    path = ROOT / "grant_agent_permissions.sh"
    lines = ["#!/usr/bin/env bash", f"# Run by a Project IAM Admin or Owner of {project}.",
             "# Gives the deployed Campaign Provisioner agent access to BigQuery, Application Integration and Vertex AI.",
             "set -e"]
    lines += [f"gcloud projects add-iam-policy-binding {project} --member={member} --role={role} --condition=None"
              for role in roles]
    path.write_text("\n".join(lines) + "\n")
    return path


def grant_runtime_roles(project: str, member: str | None, roles: list[str] | None = None) -> str:
    """Give the deployed agent's identity the roles it needs. Returns ok | missing_identity | denied | error.
    Problems are printed, never raised."""
    if not member:
        print("  PROBLEM: could not work out the identity the agent runs as (gcloud projects describe failed).")
        return "error"
    status = "ok"
    roles = roles or choose_runtime_roles()
    have = granted_roles(project, member)
    if have is not None:
        missing = [r for r in roles if r not in have]
        if not missing:
            print(f"  OK  {member} already has all the roles it needs")
            return "ok"
        roles = missing
    for role in roles:
        r = subprocess.run(["gcloud", "projects", "add-iam-policy-binding", project, f"--member={member}",
                            f"--role={role}", "--condition=None", "--quiet"], capture_output=True, text=True)
        if r.returncode == 0:
            continue
        err = (r.stderr or "").lower()
        if "does not exist" in err or "invalid" in err and "serviceaccount" in err:
            print(f"  NOTE: {member} does not exist yet (it is created the first time Agent Engine is used).")
            return "missing_identity"
        if "permission" in err or "403" in err or "denied" in err:
            script = write_admin_script(project, member, roles)
            print(f"  PROBLEM: you are not allowed to grant roles in {project} (that needs Project IAM Admin or Owner).\n"
                  f"           The agent cannot reach BigQuery or Application Integration until these roles are granted\n"
                  f"           to {member}:\n"
                  f"             {', '.join(roles)}\n"
                  f"           Send this file to an admin to run (it is ready to use):  {script}\n"
                  "           No redeploy is needed afterwards; run `python scripts/query_agent_engine.py ...` again.")
            return "denied"
        print(f"  PROBLEM granting {role}: {(r.stderr or '').strip()[:300]}")
        status = "error"
    if status == "ok":
        print(f"  OK  {member} has: {', '.join(r.split('/')[1] for r in roles)}")
    return status


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

    update_id = pick_update_id(args, read_env(ROOT / ".env"))
    args.update = update_id
    print(f"  {'Updating the existing deployment ' + update_id + ' (use --new for a separate one)' if update_id else 'Creating a new deployment'}")
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
    print("\nPermissions for the deployed agent:")
    member = runtime_member(project, args.service_account)
    grant_status = grant_runtime_roles(project, member)

    print("\nDeploying (this takes several minutes: it builds a container image) ...\n")
    returncode, text = run_deploy(cmd)
    if returncode != 0 and args.update and is_not_found(text):
        print(f"\nThe saved deployment {args.update} no longer exists (deleted?). Creating a new one instead ...\n")
        args.update = None
        cmd = deploy_command(project, region, config_path, ROOT / "campaign_provisioner", None)
        returncode, text = run_deploy(cmd)
    if returncode != 0 and grant_status == "missing_identity":
        print("\nThe agent's identity did not exist before the first deployment. Granting its roles now and "
              "trying once more ...")
        if grant_runtime_roles(project, member) == "ok":
            returncode, text = run_deploy(cmd)
    elif returncode == 0 and grant_status == "missing_identity":
        grant_runtime_roles(project, member)
        print("  (If the first question fails with a permission error, wait a minute for the roles to take effect.)")
    if returncode != 0:
        from _common import explain
        explained = explain(text, project)
        sys.exit(f"\n{explained}" if explained else
                 "\nDeployment failed (see the output above). If it mentions a missing module run "
                 "`source scripts/env_setup.sh` first. If it mentions Application Integration or BigQuery "
                 "permissions, the roles above are missing for the agent's identity.")
    found = RESOURCE_RE.findall(text)
    resource = found[-1] if found else None
    if resource:
        from setup_all import write_env
        write_env(ROOT / ".env", {"AGENT_ENGINE_RESOURCE": resource})
        print(f"\nSaved AGENT_ENGINE_RESOURCE={resource} to .env")
    if grant_status == "denied":
        print("\nSmoke test skipped: the agent's permissions are not granted yet (see above). After an admin ran "
              "grant_agent_permissions.sh, test with:\n  python scripts/query_agent_engine.py \"Which Next 2027 campaigns "
              "still have budget left?\"")
    elif resource and not args.no_smoke_test:
        print("\nSmoke test: asking the deployed agent a read-only question ...\n")
        smoke = subprocess.run([sys.executable, str(ROOT / "scripts" / "query_agent_engine.py"),
                                "Which Next 2027 campaigns still have budget left?", "--resource", resource,
                                "--project", project])
        if smoke.returncode != 0:
            sys.exit("\nThe agent was deployed but did not answer (details and logs above).")
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


def is_not_found(text: str) -> bool:
    return "NOT_FOUND" in text or "is not found" in text


def run_deploy(cmd) -> tuple[int, str]:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))
    output = []
    for line in proc.stdout:
        print(line, end="")
        output.append(line)
    proc.wait()
    return proc.returncode, "".join(output)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--region", default=None, help="Agent Engine region (default: GOOGLE_CLOUD_LOCATION or us-central1)")
    ap.add_argument("--update", nargs="?", const="auto", default=None, metavar="ENGINE_ID",
                    help="redeploy to an existing Agent Engine (no value: the one saved in .env). This is already the "
                         "default when .env has AGENT_ENGINE_RESOURCE")
    ap.add_argument("--new", action="store_true", help="create a separate new deployment even if one is saved in .env")
    ap.add_argument("--service-account", default=None, help="run the agent as this service account instead of the default")
    ap.add_argument("--dry-run", action="store_true", help="run the checks and print the command, deploy nothing")
    ap.add_argument("--no-smoke-test", action="store_true", help="do not ask the deployed agent a test question")
    ap.add_argument("--skip-checks", action="store_true", help="skip the BigQuery / Application Integration check")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()
    run(args, project=resolve_project(args.project))


if __name__ == "__main__":
    main()
