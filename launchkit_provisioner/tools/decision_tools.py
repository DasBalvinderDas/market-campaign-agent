"""Tools of the root agent: the human gate and the status check."""
from .. import decision_flow
from ..repositories import get_repo
from ..workflow.integration_client import IntegrationExecutor


def authorize_launch(request_id: str, option: str, justification: str) -> dict:
    """The sign-off gate. Authorise ONE of the computed options. Within the autopilot limit it is approved by policy;
    above it an Application Integration approval emails the named executive and nothing is ordered until they approve.
    Only the root agent has this tool.

    Args:
        request_id: Request id with computed options.
        option: The option the user chose: "Option 2", "2", "rebalance", "eco", or "recommended".
        justification: One sentence on why this option (shown to the approver).
    """
    return decision_flow.authorize(get_repo(), IntegrationExecutor(), request_id, option, justification)


def get_launch_status(request_id: str) -> dict:
    """Status of the sign-off and of the orders for a request. If the approver has decided in Application Integration
    this records it: Approved means the fulfilment agent can place the orders, Rejected releases the held depot stock.

    Args:
        request_id: Request id, e.g. "REQ-1A2B3C4D".
    """
    return {"request_id": request_id, **decision_flow.status(get_repo(), request_id)}
