#!/usr/bin/env bash
# One-time Google Cloud setup: enable APIs and grant the roles the agent needs.
# Usage: PROJECT_ID=my-proj PRINCIPAL="user:you@example.com" ./scripts/setup_gcp.sh
#   (PRINCIPAL can also be "serviceAccount:sa@my-proj.iam.gserviceaccount.com")
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID}"
: "${PRINCIPAL:?Set PRINCIPAL, e.g. user:you@example.com}"

gcloud config set project "$PROJECT_ID"
gcloud services enable bigquery.googleapis.com integrations.googleapis.com \
  connectors.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com

for ROLE in roles/bigquery.dataEditor roles/bigquery.jobUser \
            roles/integrations.integrationInvoker roles/integrations.viewer roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$PRINCIPAL" --role="$ROLE" --condition=None >/dev/null
  echo "granted $ROLE"
done

echo
echo "Next:  gcloud auth application-default login"
echo "       python scripts/setup_bigquery.py --project $PROJECT_ID"
