"""Central configuration. Everything is overridable with environment variables."""
import os

MODEL = os.getenv("LAUNCHKIT_MODEL", "gemini-2.5-flash")

# Business data lives in BigQuery; workflow actions run in Google Application Integration.
# (The unit tests override DATA_BACKEND through the environment, see tests/conftest.py.)
DATA_BACKEND = os.getenv("DATA_BACKEND", "bigquery").lower()
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
BQ_DATASET = os.getenv("BQ_DATASET", "launchkit")
BQ_LOCATION = os.getenv("BQ_LOCATION", "US")

APP_INTEGRATION_NAME = os.getenv("APP_INTEGRATION_NAME", "launchkit-workflows")
APP_INTEGRATION_LOCATION = os.getenv("APP_INTEGRATION_LOCATION", "us-central1")
PO_TRIGGER = os.getenv("APP_INTEGRATION_PO_TRIGGER", "api_trigger/create_purchase_order")
TRANSFER_TRIGGER = os.getenv("APP_INTEGRATION_TRANSFER_TRIGGER", "api_trigger/create_depot_transfer")
UPDATE_TRIGGER = os.getenv("APP_INTEGRATION_UPDATE_TRIGGER", "api_trigger/send_launch_update")
APPROVAL_TRIGGER = os.getenv("APP_INTEGRATION_APPROVAL_TRIGGER", "api_trigger/request_approval")

# How long a pending sign-off stays valid.
APPROVAL_TTL_HOURS = float(os.getenv("APPROVAL_TTL_HOURS", "72"))

# Who runs the deployed agent (a service account with BigQuery + Application Integration access).
# Empty: Agent Engine's default service agent is used.
AGENT_SERVICE_ACCOUNT = os.getenv("AGENT_SERVICE_ACCOUNT", "")

# Where approvals and order confirmations go: "email" (approval email with buttons, launch-team email), "gemini" (inside the
# Gemini Enterprise app: the approver says Approve or Reject in the agent; no emails) or "both".
# "workflow": the approval is a human step of a Gemini Enterprise workflow, so it shows in the app's Inbox ("Needs input"); the
# workflow's last agent step records the answer (see docs/GEMINI_INBOX_WORKFLOW.md).
_CHANNEL = os.getenv("APPROVAL_CHANNEL", "email").strip().lower()
APPROVAL_CHANNEL = _CHANNEL if _CHANNEL in ("email", "gemini", "both", "workflow") else "email"
# "gemini" and "workflow" send no email. Set this to true to also send a plain notice (no buttons) to the approvers and the
# launch team: "an approval is waiting in your Inbox" and "orders placed".
APPROVAL_NOTIFY_EMAIL = os.getenv("APPROVAL_NOTIFY_EMAIL", "false").strip().lower() in ("true", "1", "yes")
# In "gemini" or "both" mode, only a signed-in user whose address is on the approver list for the role may decide.
# Set it to false to let anyone in the chat decide (demo only).
APPROVAL_CHECK_USER = os.getenv("APPROVAL_CHECK_USER", "true").strip().lower() not in ("false", "0", "no")

# Notification emails: "Role=a@x.com,b@x.com;Other Role=c@x.com" (or just "a@x.com" for every role).
APPROVER_EMAILS = os.getenv("APPROVER_EMAILS", "")

