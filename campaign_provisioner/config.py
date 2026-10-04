"""Central configuration. Everything is overridable with environment variables."""
import os

MODEL = os.getenv("CAMPAIGN_MODEL", "gemini-2.5-flash")

# Real-environment defaults: business data in BigQuery, workflow actions through Application Integration.
# (The unit tests override these two settings through the environment, see tests/conftest.py.)
DATA_BACKEND = os.getenv("DATA_BACKEND", "bigquery").lower()
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
BQ_DATASET = os.getenv("BQ_DATASET", "campaign_provisioner")
BQ_LOCATION = os.getenv("BQ_LOCATION", "US")

# Workflow actions (create PO, notify approver) run in Google Application Integration through ADK's
# ApplicationIntegrationToolset.
WORKFLOW_BACKEND = os.getenv("WORKFLOW_BACKEND", "app_integration").lower()
APP_INTEGRATION_NAME = os.getenv("APP_INTEGRATION_NAME", "campaign-provisioner-workflows")
APP_INTEGRATION_LOCATION = os.getenv("APP_INTEGRATION_LOCATION", "us-central1")
PO_TRIGGER = os.getenv("APP_INTEGRATION_PO_TRIGGER", "api_trigger/create_purchase_order")
NOTIFY_TRIGGER = os.getenv("APP_INTEGRATION_NOTIFY_TRIGGER", "api_trigger/notify_approver")

EVENT_NAME = "Google Next 2027"

# Approver notification emails: "Role=a@x.com,b@x.com;Other Role=c@x.com" (or just "a@x.com" for every role).
APPROVER_EMAILS = os.getenv("APPROVER_EMAILS", "")
