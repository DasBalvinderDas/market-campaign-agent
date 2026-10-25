"""Tools of the root agent for approving inside the Gemini Enterprise app (APPROVAL_CHANNEL=gemini or both)."""
import asyncio

from .. import decision_flow
from ..repositories import get_repo


def _user(tool_context) -> str:
    return str(getattr(tool_context, "user_id", "") or "")


async def get_my_approvals(tool_context=None) -> dict:
    """The approver's inbox inside this app: the requests that wait for the signed-in user's approval. Call it when the user says
    "My approvals", "what is waiting for me", "pending approvals" or "approval inbox". Show `display_markdown` exactly.
    """
    return await asyncio.to_thread(decision_flow.my_approvals, get_repo(), _user(tool_context))


async def decide_approval(request_id: str, decision: str, comment: str = "", tool_context=None) -> dict:
    """Record the signed-in approver's decision on a request: "approve" or "reject". Call it only when the user clearly says
    Approve or Reject with a request number. After approve, call the fulfilment_agent tool to place the orders.

    Args:
        request_id: The request number, e.g. "REQ-1A2B3C4D".
        decision: "approve" or "reject".
        comment: Optional reason the user gave.
    """
    return await asyncio.to_thread(decision_flow.decide_in_app, get_repo(), _user(tool_context), request_id, decision, comment)
