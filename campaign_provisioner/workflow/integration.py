"""Workflow actions through Google Application Integration.

Two integration API triggers are used:
  * create_purchase_order  - creates the PO (ERP / vendor email / approvals chat) and returns po_number
  * notify_approver        - emails the human approver that a decision is waiting (recipients come from the
                             BigQuery table `approvers`)

The tools come from ADK's ApplicationIntegrationToolset (your published integration). The local functions below
are test doubles with the same argument names; they are used only by the unit tests.

The integration contract (inputs/outputs) is documented in integration/README.md.
"""
import uuid

from .. import config

_PO_HINT = ("Create the purchase order for an APPROVED request. Pass request_id, sku, quantity and vendor_id. "
            "The platform recomputes the amount and blocks the call if no approved budget covers it.")
_NOTIFY_HINT = ("Email the human approver that a high-value request is waiting for a decision. Pass request_id, "
                "campaign_id, amount, approver_role and summary. Never pass approver_emails; the platform fills it in.")


def create_purchase_order(request_id: str, sku: str, quantity: int, vendor_id: str,
                          campaign_id: str = "", total_amount: float = 0.0) -> dict:
    """Create a purchase order for an approved request (test double for the Application
    Integration trigger of the same name).

    Args:
        request_id: Approved campaign request id.
        sku: Catalog SKU.
        quantity: Units to order.
        vendor_id: Vendor chosen from the quotes.
        campaign_id: Filled in by the platform guard.
        total_amount: Filled in by the platform guard (USD).
    """
    return {"status": "SUCCEEDED", "po_number": f"PO-{uuid.uuid4().hex[:8].upper()}",
            "execution_id": f"mock-{uuid.uuid4().hex[:8]}"}


def notify_approver(request_id: str, campaign_id: str, amount: float, approver_role: str, summary: str,
                    approver_emails: str = "") -> dict:
    """Notify the human approver by email that a request is waiting (test double for the Application
    Integration trigger of the same name). Do not pass approver_emails: the platform fills it in from the
    BigQuery table `approvers`.

    Args:
        request_id: Campaign request id.
        campaign_id: Campaign being charged.
        amount: USD amount awaiting approval.
        approver_role: Role that must decide, from get_approval_policy.
        summary: What is being bought and why (items, vendor, total).
        approver_emails: Filled in by the platform guard.
    """
    return {"status": "SUCCEEDED", "channel": "test double (no email is sent)", "approver_role": approver_role,
            "approver_emails": approver_emails}


def _toolset(trigger: str, hint: str):
    from google.adk.tools.application_integration_tool import ApplicationIntegrationToolset

    if not config.PROJECT:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set (export GOOGLE_CLOUD_PROJECT=<your-project-id>)")
    try:
        return ApplicationIntegrationToolset(
            project=config.PROJECT, location=config.APP_INTEGRATION_LOCATION,
            integration=config.APP_INTEGRATION_NAME, triggers=[trigger], tool_instructions=hint)
    except ValueError as exc:  # ADK raises this when the integration or trigger cannot be found
        raise RuntimeError(
            f"Application Integration '{config.APP_INTEGRATION_NAME}' (trigger {trigger}) was not found in project "
            f"'{config.PROJECT}', region '{config.APP_INTEGRATION_LOCATION}'. Create it first:\n"
            "    python scripts/setup_application_integration.py     (or python scripts/setup_all.py)\n"
            "and check APP_INTEGRATION_NAME / APP_INTEGRATION_LOCATION in .env.") from exc


def build_po_tool():
    return _toolset(config.PO_TRIGGER, _PO_HINT) if config.WORKFLOW_BACKEND != "mock" \
        else create_purchase_order


def build_notify_tool():
    return _toolset(config.NOTIFY_TRIGGER, _NOTIFY_HINT) if config.WORKFLOW_BACKEND != "mock" \
        else notify_approver
