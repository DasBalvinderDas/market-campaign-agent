"""Tools for the Budget Agent, including the human-in-the-loop gate."""
from google.adk.tools import FunctionTool, ToolContext

from .. import config
from ..data import BUDGETS
from .audit import audit


def check_budget(campaign_id: str) -> dict:
    """Return budget position for a campaign.

    Args:
        campaign_id: e.g. "CMP-SPRING-LAUNCH".
    """
    b = BUDGETS.get(campaign_id)
    if not b:
        return {"status": "error", "message": f"Unknown campaign '{campaign_id}'. Known: {sorted(BUDGETS)}"}
    remaining = b["total"] - b["spent"] - b["committed"]
    return {"status": "ok", "campaign_id": campaign_id, "total": b["total"],
            "spent": b["spent"], "committed": b["committed"], "remaining": remaining,
            "high_value_threshold": config.HIGH_VALUE_THRESHOLD_USD}


def approve_budget(request_id: str, campaign_id: str, amount: float,
                   justification: str, tool_context: ToolContext) -> dict:
    """Approve and commit budget for a procurement request.

    Requests above the high-value threshold are paused by the framework until a
    human confirms (see ``requires_human`` below); smaller ones are auto-approved
    by policy. The approval is recorded in session state, and procurement refuses
    to place any purchase order without it.

    Args:
        request_id: Campaign request id.
        campaign_id: Budget to charge.
        amount: Total USD to commit.
        justification: Why the spend is needed (shown to the human approver).
    """
    b = BUDGETS.get(campaign_id)
    if not b:
        return {"status": "error", "message": f"Unknown campaign '{campaign_id}'."}
    remaining = b["total"] - b["spent"] - b["committed"]
    if amount > remaining:
        audit(tool_context.state, "budget_agent", "budget_rejected_insufficient",
              request_id=request_id, amount=amount, remaining=remaining)
        return {"status": "rejected", "reason": "Insufficient remaining budget",
                "requested": amount, "remaining": remaining}
    b["committed"] += amount
    human = amount > config.HIGH_VALUE_THRESHOLD_USD
    approvals = dict(tool_context.state.get("approvals", {}))
    approvals[request_id] = {"campaign_id": campaign_id, "approved_amount": amount,
                             "approved_by": "human" if human else "auto-policy"}
    tool_context.state["approvals"] = approvals
    audit(tool_context.state, "budget_agent", "budget_approved", request_id=request_id,
          amount=amount, approved_by=approvals[request_id]["approved_by"])
    return {"status": "approved", "request_id": request_id, "approved_amount": amount,
            "approved_by": approvals[request_id]["approved_by"]}


def requires_human(amount: float, **_) -> bool:
    """Confirmation predicate: True means ADK pauses and asks a human."""
    return amount > config.HIGH_VALUE_THRESHOLD_USD


approve_budget_tool = FunctionTool(approve_budget, require_confirmation=requires_human)
