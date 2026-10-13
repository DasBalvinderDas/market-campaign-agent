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


async def get_order_pack(request_id: str, tool_context=None) -> dict:
    """Make the order pack (a formatted PDF with the shopping list, the vendors and the warehouse moves) for a request
    whose plan was chosen, and attach it to the chat so the user can open it. Call it after the orders are placed or when the
    user asks for the details as a document.

    Args:
        request_id: Request id, e.g. "REQ-1A2B3C4D".
    """
    from .. import order_pack
    repo = get_repo()
    try:
        pdf = order_pack.build_pdf(repo, request_id)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    name = f"order-pack-{request_id}.pdf"
    saved = False
    if tool_context is not None:
        try:
            from google.genai import types
            await tool_context.save_artifact(name, types.Part.from_bytes(data=pdf, mime_type="application/pdf"))
            saved = True
        except Exception:  # noqa: BLE001 - no artifact service in this run
            saved = False
    msg = (f"📎 **Order pack ready:** `{name}` (shopping list, vendors and warehouse moves in one PDF)." if saved else
           "The order pack could not be attached in this chat.")
    return {"status": "ok" if saved else "not_attached", "file": name, "bytes": len(pdf), "display_markdown": msg}
