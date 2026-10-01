"""Workflow actions through Google Application Integration.

Two integration API triggers are used:
  * create_purchase_order  - creates the PO (ERP / vendor email / approvals chat) and returns po_number
  * notify_approver        - tells the human approver a decision is waiting (Chat / email)

WORKFLOW_BACKEND=app_integration  -> ADK ApplicationIntegrationToolset (real integration)
WORKFLOW_BACKEND=mock             -> local functions with the same argument names (offline demo/tests)

The integration contract (inputs/outputs) is documented in integration/README.md.
"""
import uuid

from .. import config

_PO_HINT = ("Create the purchase order for an APPROVED request. Pass request_id, sku, quantity and vendor_id. "
            "The platform recomputes the amount and blocks the call if no approved budget covers it.")
_NOTIFY_HINT = "Notify the human approver that a high-value request is waiting for a decision."


def create_purchase_order(request_id: str, sku: str, quantity: int, vendor_id: str,
                          campaign_id: str = "", total_amount: float = 0.0) -> dict:
    """Create a purchase order for an approved request (offline stand-in for the Application
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


def notify_approver(request_id: str, campaign_id: str, amount: float, approver_role: str, summary: str) -> dict:
    """Notify the human approver that a request is waiting (offline stand-in for the Application
    Integration trigger of the same name).

    Args:
        request_id: Campaign request id.
        campaign_id: Campaign being charged.
        amount: USD amount awaiting approval.
        approver_role: Role that must decide, from get_approval_policy.
        summary: What is being bought and why.
    """
    return {"status": "SUCCEEDED", "channel": "mock", "approver_role": approver_role}


def _toolset(trigger: str, hint: str):
    from google.adk.tools.application_integration_tool import ApplicationIntegrationToolset

    if not config.PROJECT:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set when WORKFLOW_BACKEND=app_integration")
    return ApplicationIntegrationToolset(
        project=config.PROJECT, location=config.APP_INTEGRATION_LOCATION,
        integration=config.APP_INTEGRATION_NAME, triggers=[trigger], tool_instructions=hint)


def build_po_tool():
    return _toolset(config.PO_TRIGGER, _PO_HINT) if config.WORKFLOW_BACKEND == "app_integration" \
        else create_purchase_order


def build_notify_tool():
    return _toolset(config.NOTIFY_TRIGGER, _NOTIFY_HINT) if config.WORKFLOW_BACKEND == "app_integration" \
        else notify_approver
