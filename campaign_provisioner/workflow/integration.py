"""Workflow actions through Google Application Integration.

Two integration API triggers are used:
  * create_purchase_order  - creates the PO (ERP / vendor email / approvals chat) and returns po_number
  * notify_approver        - emails the human approver that a decision is waiting (recipients come from the
                             BigQuery table `approvers`)

The tools come from ADK's ApplicationIntegrationToolset (your published integration). The local functions below
are test doubles with the same argument names; they are used only by the unit tests.

The integration contract (inputs/outputs) is documented in integration/README.md.
"""
import asyncio
import logging
import uuid

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from .. import config

logger = logging.getLogger(__name__)

_PO_HINT = ("Create the purchase order for an APPROVED request. Pass request_id, sku, quantity and vendor_id. "
            "The platform recomputes the amount and blocks the call if no approved budget covers it.")
_NOTIFY_HINT = ("Email the human approver that a high-value request is waiting for a decision. Pass request_id, "
                "campaign_id, amount, approver_role and summary. Never pass approver_email, email_subject or email_body; the platform fills them in.")


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
                    approver_email: str = "", email_subject: str = "", email_body: str = "") -> dict:
    """Email the human approver that a request is waiting (test double for the Application Integration trigger
    of the same name). Do not pass approver_email, email_subject or email_body: the platform fills them in.

    Args:
        request_id: Campaign request id.
        campaign_id: Campaign being charged.
        amount: USD amount awaiting approval.
        approver_role: Role that must decide, from get_approval_policy.
        summary: What is being bought and why (items, vendor, total).
        approver_email: Filled in by the platform guard.
        email_subject: Filled in by the platform guard.
        email_body: Filled in by the platform guard.
    """
    return {"status": "SUCCEEDED", "channel": "test double (no email is sent)", "approver_role": approver_role,
            "approver_email": approver_email}


def create_purchase_order_unavailable(request_id: str, sku: str, quantity: int, vendor_id: str,
                                      campaign_id: str = "", total_amount: float = 0.0) -> dict:
    """Create a purchase order for an approved request."""
    return _unavailable_result()


def notify_approver_unavailable(request_id: str, campaign_id: str, amount: float, approver_role: str, summary: str,
                                approver_email: str = "", email_subject: str = "", email_body: str = "") -> dict:
    """Email the human approver that a request is waiting."""
    return _unavailable_result()


_LAST_ERROR = {"message": ""}


def runtime_identity() -> str:
    """Best-effort: the service account this process runs as (shown in errors to make permission problems obvious)."""
    try:
        import google.auth
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        return getattr(creds, "service_account_email", None) or "an unknown identity"
    except Exception:  # noqa: BLE001
        return "an unknown identity"


def _unavailable_result() -> dict:
    return {"status": "ERROR", "error": "The Application Integration workflow could not be loaded: "
            f"{_LAST_ERROR['message']}. Tell the user this step failed; do not retry."}


def _build_toolset(trigger: str, hint: str):
    from google.adk.tools.application_integration_tool import ApplicationIntegrationToolset

    if not config.PROJECT:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not set")
    try:
        return ApplicationIntegrationToolset(
            project=config.PROJECT, location=config.APP_INTEGRATION_LOCATION,
            integration=config.APP_INTEGRATION_NAME, triggers=[trigger], tool_instructions=hint)
    except ValueError as exc:  # ADK raises this when the integration or trigger cannot be found
        raise RuntimeError(
            f"Application Integration '{config.APP_INTEGRATION_NAME}' (trigger {trigger}) was not found or is not "
            f"readable by this identity in project '{config.PROJECT}', region '{config.APP_INTEGRATION_LOCATION}'. "
            "Create it with scripts/setup_application_integration.py and give the running identity "
            "roles/integrations.integrationInvoker and roles/integrations.integrationViewer (or Editor).") from exc


class LazyIntegrationToolset(BaseToolset):
    """Application Integration tools that are built on first use, not when the agent is imported.

    Building them calls Google at once, which must not be able to break the whole agent at start-up (for
    example on Agent Engine, where a missing permission would make every request fail). If the integration
    cannot be reached, the agent still starts and the tool answers with a clear error instead.
    """

    def __init__(self, trigger: str, hint: str, fallback):
        super().__init__()
        self._trigger, self._hint, self._fallback = trigger, hint, fallback
        self._inner = None

    async def get_tools(self, readonly_context=None):
        if self._inner is None:
            try:
                self._inner = await asyncio.to_thread(_build_toolset, self._trigger, self._hint)
            except Exception as exc:  # noqa: BLE001 - report instead of crashing the agent
                identity = await asyncio.to_thread(runtime_identity)
                _LAST_ERROR["message"] = f"running as {identity}; {str(exc)[:300]}"
                logger.error("Application Integration tool %s unavailable: %s | running as %s | cause: %s",
                             self._trigger, exc, identity, exc.__cause__)
                return [FunctionTool(self._fallback)]
        return await self._inner.get_tools(readonly_context)

    async def close(self):
        if self._inner is not None:
            await self._inner.close()


def build_po_tool():
    return LazyIntegrationToolset(config.PO_TRIGGER, _PO_HINT, create_purchase_order_unavailable) \
        if config.WORKFLOW_BACKEND != "mock" else create_purchase_order


def build_notify_tool():
    return LazyIntegrationToolset(config.NOTIFY_TRIGGER, _NOTIFY_HINT, notify_approver_unavailable) \
        if config.WORKFLOW_BACKEND != "mock" else notify_approver
