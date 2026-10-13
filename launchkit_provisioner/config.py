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

# Notification emails: "Role=a@x.com,b@x.com;Other Role=c@x.com" (or just "a@x.com" for every role).
APPROVER_EMAILS = os.getenv("APPROVER_EMAILS", "")

# Private Cloud Storage bucket that hands the order pack PDF to the email workflow (created by scripts/setup_order_pack_bucket.py).
# Empty string switches the attachment off.
ORDER_PACK_BUCKET = os.getenv("ORDER_PACK_BUCKET", f"{PROJECT}-launchkit-order-packs" if PROJECT else "")
