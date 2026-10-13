"""Tools of the root agent: the human gate and the status check."""
from .. import decision_flow
from ..repositories import get_repo
from ..workflow.integration_client import IntegrationExecutor


async def authorize_launch(request_id: str, option: str, justification: str, tool_context=None) -> dict:
    """The sign-off gate. Authorise ONE of the computed options. Within the automatic limit it is approved by policy;
    above it the named executive is emailed and nothing is ordered until they approve. The order pack PDF is made here, so
    it is in the chat right away. Only the root agent has this tool.

    Args:
        request_id: Request id with computed options.
        option: The option the user chose: "Option 2", "2", "rebalance", "eco", or "recommended".
        justification: One sentence on why this option (shown to the approver).
    """
    import asyncio
    out = await asyncio.to_thread(decision_flow.authorize, get_repo(), IntegrationExecutor(), request_id, option, justification)
    if out.get("status") in ("approved", "pending_approval"):
        name = await _attach_pack(request_id, tool_context)
        if name:
            out["order_pack"] = name
            if out.get("display_markdown"):
                out["display_markdown"] += f"\n\n📎 **Order pack PDF:** `{name}` (shopping list, vendors and warehouse moves) is attached to this chat."
    return out


async def _attach_pack(request_id: str, tool_context) -> str:
    """Build the order pack PDF and save it as a chat file. Returns its name, or "" if it could not be made."""
    if tool_context is None:
        return ""
    try:
        from google.genai import types

        from .. import order_pack
        pdf = order_pack.build_pdf(get_repo(), request_id)
        name = f"order-pack-{request_id}.pdf"
        await tool_context.save_artifact(name, types.Part.from_bytes(data=pdf, mime_type="application/pdf"))
        return name
    except Exception:  # noqa: BLE001 - the order must never fail because the PDF could not be made
        return ""


def get_launch_status(request_id: str) -> dict:
    """Status of the sign-off and of the orders for a request. If the approver has decided in Application Integration
    this records it: Approved means the fulfilment agent can place the orders, Rejected releases the held depot stock.

    Args:
        request_id: Request id, e.g. "REQ-1A2B3C4D".
    """
    return {"request_id": request_id, **decision_flow.status(get_repo(), request_id)}


async def get_order_pack(request_id: str, tool_context=None) -> dict:
    """Make the order pack PDF again (for example after the orders are placed, so it also lists the purchase order numbers)
    and attach it to the chat. Call it only when the user asks for the pack or the PDF.

    Args:
        request_id: Request id, e.g. "REQ-1A2B3C4D".
    """
    name = await _attach_pack(request_id, tool_context)
    if not name:
        return {"status": "error", "message": "The order pack could not be made yet. A plan has to be chosen first."}
    return {"status": "ok", "file": name, "display_markdown": f"📎 **Order pack ready:** `{name}` (now with the purchase order numbers, if the orders are placed)."}
