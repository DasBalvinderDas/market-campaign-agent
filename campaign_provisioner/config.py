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

# Who runs the deployed agent and the approval-link service (a service account with BigQuery + Application
# Integration access). Empty: Agent Engine's default service agent is used.
AGENT_SERVICE_ACCOUNT = os.getenv("AGENT_SERVICE_ACCOUNT", "")

# Human approval by email link. APPROVAL_BASE_URL is the public URL of the approval-link service
# (scripts/deploy_approval_service.py writes it to .env). With it set, approvers get Approve / Reject links by
# email and need no login; without it the approval is asked in the chat.
APPROVAL_BASE_URL = os.getenv("APPROVAL_BASE_URL", "").rstrip("/")
APPROVAL_LINK_SECRET = os.getenv("APPROVAL_LINK_SECRET", "")
APPROVAL_LINK_TTL_HOURS = float(os.getenv("APPROVAL_LINK_TTL_HOURS", "72"))
# APPROVAL_CHANNEL: "integration" = native Application Integration approval (the approver gets an Application
# Integration email with Approve / Reject; default with the real workflow backend), "email" = signed links served by
# the Cloud Run approval service, "chat" = confirmation inside the chat.
APPROVAL_TRIGGER = os.getenv("APP_INTEGRATION_APPROVAL_TRIGGER", "api_trigger/request_approval")
APPROVAL_CHANNEL = (os.getenv("APPROVAL_CHANNEL") or (
    "email" if APPROVAL_BASE_URL else "integration" if WORKFLOW_BACKEND == "app_integration" else "chat")).lower()


def async_approval() -> bool:
    """True when the human decides outside the chat (Application Integration approval or emailed links)."""
    return APPROVAL_CHANNEL in ("email", "integration")

# Approver notification emails: "Role=a@x.com,b@x.com;Other Role=c@x.com" (or just "a@x.com" for every role).
APPROVER_EMAILS = os.getenv("APPROVER_EMAILS", "")
