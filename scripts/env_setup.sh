#!/usr/bin/env bash
# Environment setup for Cloud Shell. Run it FIRST, with `source` (so the settings stay in your shell):
#
#   source scripts/env_setup.sh                              # prepare the shell
#   source scripts/env_setup.sh --project my-project         # use a specific project
#   source scripts/env_setup.sh --service-account app-svc@my-project.iam.gserviceaccount.com   # save it in .env
#   source scripts/env_setup.sh --approver-email you@x.com   # also create the BigQuery data + Application
#                                                            # Integration workflow if they do not exist yet
#
# It: creates/activates the Python virtual environment, installs everything the agent and the deployment need,
# sets GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION, and checks login, APIs and data. Nothing is enabled or
# changed in Google Cloud except (with --approver-email) the data setup. Any problem is printed with what to do.
# Then run:  python scripts/deploy_agent_engine.py

if ! (return 0 2>/dev/null); then
  echo "Run this with 'source' so the settings stay in your shell:  source scripts/env_setup.sh"
  exit 1
fi

_ES_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ES_PROJECT=""
_ES_EMAIL=""
_ES_REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
_ES_SA=""
_ES_PROBLEMS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --project) _ES_PROJECT="$2"; shift 2 ;;
    --region) _ES_REGION="$2"; shift 2 ;;
    --approver-email) _ES_EMAIL="$2"; shift 2 ;;
    --service-account) _ES_SA="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; shift ;;
  esac
done

_es_problem() { echo "  PROBLEM: $*"; _ES_PROBLEMS=$((_ES_PROBLEMS + 1)); }
_es_ok() { echo "  OK  $*"; }

echo "== Python environment"
cd "$_ES_ROOT" || { _es_problem "cannot open $_ES_ROOT"; return 1; }
if [ ! -d .venv ]; then
  python3 -m venv .venv && _es_ok "created .venv" || _es_problem "could not create .venv (is python3-venv installed?)"
fi
# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && source .venv/bin/activate && _es_ok "activated .venv ($(python --version 2>&1))"
if [ -z "$ENV_SETUP_SKIP_INSTALL" ]; then
  echo "  installing packages (first run takes a few minutes) ..."
  if pip install -q --disable-pip-version-check -r requirements.txt "google-adk[gcp]" 2>/tmp/env_setup_pip.log; then
    _es_ok "packages installed"
  else
    _es_problem "pip install failed:"; tail -5 /tmp/env_setup_pip.log | sed 's/^/      /'
  fi
fi

echo "== Google Cloud project"
if [ -z "$_ES_PROJECT" ]; then _ES_PROJECT="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"; fi
if [ -z "$_ES_PROJECT" ] || [ "$_ES_PROJECT" = "(unset)" ]; then
  _es_problem "no project id. Run:  source scripts/env_setup.sh --project <your-project-id>"
else
  export GOOGLE_CLOUD_PROJECT="$_ES_PROJECT"
  export GOOGLE_CLOUD_LOCATION="$_ES_REGION"
  export GOOGLE_GENAI_USE_VERTEXAI=TRUE
  gcloud config set project "$_ES_PROJECT" >/dev/null 2>&1
  _es_ok "project $GOOGLE_CLOUD_PROJECT, region $GOOGLE_CLOUD_LOCATION"
fi

echo "== Login"
_ES_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1)"
if [ -z "$_ES_ACCOUNT" ]; then
  _es_problem "not logged in to gcloud. Run:  gcloud auth login"
else
  _es_ok "logged in as $_ES_ACCOUNT"
fi

echo "== APIs"
if [ -n "$GOOGLE_CLOUD_PROJECT" ] && [ -n "$_ES_ACCOUNT" ]; then
  _ES_ENABLED="$(gcloud services list --enabled --project "$GOOGLE_CLOUD_PROJECT" --format='value(config.name)' 2>/dev/null)"
  if [ -z "$_ES_ENABLED" ]; then
    echo "  (could not list the enabled APIs; the scripts will report any that are missing)"
  else
    _ES_MISSING=""
    for api in bigquery.googleapis.com integrations.googleapis.com aiplatform.googleapis.com cloudbuild.googleapis.com; do
      echo "$_ES_ENABLED" | grep -qx "$api" || _ES_MISSING="$_ES_MISSING $api"
    done
    if [ -n "$_ES_MISSING" ]; then
      _es_problem "these APIs are not enabled:$_ES_MISSING"
      echo "      enable them:  gcloud services enable$_ES_MISSING --project $GOOGLE_CLOUD_PROJECT"
    else
      _es_ok "BigQuery, Application Integration, Vertex AI and Cloud Build APIs are enabled"
    fi
  fi
fi

if [ -n "$_ES_SA" ] && [ -z "$_ES_EMAIL" ]; then
  python - "$_ES_SA" <<'PY'
import sys
sys.path.insert(0, "scripts")
from setup_all import write_env, ROOT
write_env(ROOT / ".env", {"AGENT_SERVICE_ACCOUNT": sys.argv[1]})
print("  OK  AGENT_SERVICE_ACCOUNT=" + sys.argv[1] + " saved to .env")
PY
elif [ -z "$_ES_SA" ] && [ -f .env ]; then
  _es_sa_env=$(grep -E '^AGENT_SERVICE_ACCOUNT=.+' .env | tail -1 | cut -d= -f2-)
  if [ -n "$_es_sa_env" ]; then _es_ok "service account from .env: $_es_sa_env (used by the deploy script)"; fi
fi

echo "== Config file"
if [ -f campaign_provisioner/.env ]; then
  _es_problem "campaign_provisioner/.env exists and would override the repo-root .env. Delete it:  rm campaign_provisioner/.env"
else
  _es_ok "no stray campaign_provisioner/.env"
fi

if [ -n "$_ES_EMAIL" ] && [ -n "$GOOGLE_CLOUD_PROJECT" ] && [ "$_ES_PROBLEMS" -eq 0 ]; then
  echo "== Data setup (BigQuery + Application Integration)"
  python scripts/setup_all.py --approver-email "$_ES_EMAIL" ${_ES_SA:+--service-account "$_ES_SA"} || _es_problem "data setup did not finish (see the message above)"
fi

if [ -n "$GOOGLE_CLOUD_PROJECT" ] && [ "$_ES_PROBLEMS" -eq 0 ] && [ -z "$ENV_SETUP_SKIP_CHECK" ]; then
  echo "== Data check"
  python scripts/verify_setup.py --integration >/tmp/env_setup_verify.log 2>&1 \
    && _es_ok "BigQuery data and the Application Integration workflow are ready" \
    || { _es_problem "data or workflow not ready:"; tail -8 /tmp/env_setup_verify.log | sed 's/^/      /'
         echo "      set it up with:  source scripts/env_setup.sh --approver-email <your-email>"; }
fi

echo
if [ "$_ES_PROBLEMS" -eq 0 ]; then
  echo "Environment ready. Next:  python scripts/deploy_agent_engine.py"
else
  echo "$_ES_PROBLEMS problem(s) above. Fix them and run this again:  source scripts/env_setup.sh"
fi
unset _ES_SA _ES_ROOT _ES_PROJECT _ES_EMAIL _ES_REGION _ES_PROBLEMS _ES_ACCOUNT _ES_ENABLED _ES_MISSING
unset -f _es_problem _es_ok
