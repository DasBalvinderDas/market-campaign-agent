"""Tools for the Budget Agent, including the human-in-the-loop gate."""
from google.adk.tools import FunctionTool, ToolContext

from ..repositories import get_repo
from .audit import audit


def check_budget(campaign_id: str) -> dict:
    """Return the budget position of a campaign (from BigQuery view v_campaign_budget).

    Args:
        campaign_id: e.g. "NEXT27-MAIN".
    """
    b = get_repo().get_budget(campaign_id)
    if not b:
        known = [x["campaign_id"] for x in get_repo().list_budgets()]
        return {"status": "error", "message": f"Unknown campaign '{campaign_id}'. Known: {known}"}
    return {"status": "ok", **{k: (float(v) if isinstance(v, (int, float)) else v) for k, v in b.items()}}


def get_approval_policy(amount: float) -> dict:
    """Look up which approval tier applies to an amount (from BigQuery table approval_policy).

    Args:
        amount: Total USD to approve.
    """
    p = get_repo().get_policy(float(amount))
    return {"status": "ok", "amount": amount, "tier": p["tier"],
            "requires_human": bool(p["requires_human"]), "approver_role": p["approver_role"]}


def approve_budget(request_id: str, campaign_id: str, amount: float, justification: str,
                   tool_context: ToolContext | None = None) -> dict:
    """Approve and commit budget for a request. Writes a COMMIT entry to the budget ledger.

    Amounts in a tier that requires a human are paused by the platform until a person
    confirms (see ``requires_human``). Others are approved automatically by policy.

    Args:
        request_id: Campaign request id.
        campaign_id: Budget to charge.
        amount: Total USD to commit.
        justification: Why the spend is needed (shown to the human approver).
    """
    result = _approve(request_id, campaign_id, amount, justification)
    if tool_context is not None and result.get("status") in ("approved", "rejected"):
        # Hand control back to the orchestrator in code, so the next step (purchase orders, or releasing stock
        # after a rejection) does not depend on the model remembering to transfer.
        tool_context.actions.transfer_to_agent = "campaign_provisioner"
    if result.get("status") == "approved":
        result["next_step"] = "Budget approved. Control returns to campaign_provisioner, which now has procurement_agent create the purchase orders."
    elif result.get("status") == "rejected":
        result["next_step"] = "Budget not approved. Control returns to campaign_provisioner, which releases the reserved stock and explains."
    return result


def _approve(request_id: str, campaign_id: str, amount: float, justification: str) -> dict:
    repo = get_repo()
    budget = repo.get_budget(campaign_id)
    if not budget:
        return {"status": "error", "message": f"Unknown campaign '{campaign_id}'."}
    if not repo.get_request(request_id):
        return {"status": "error", "message": f"Unknown request '{request_id}'."}
    remaining = float(budget["remaining"])
    if amount > remaining:
        audit(request_id, "budget_agent", "budget_rejected_insufficient", amount=amount, remaining=remaining)
        return {"status": "rejected", "reason": "Insufficient remaining budget",
                "requested": amount, "remaining": remaining}
    policy = repo.get_policy(float(amount))
    approved_by = f"human:{policy['approver_role']}" if policy["requires_human"] else "auto-policy"
    repo.commit_budget(campaign_id, request_id, float(amount), approved_by)
    audit(request_id, "budget_agent", "budget_approved", amount=amount, approved_by=approved_by,
          tier=policy["tier"], justification=justification)
    return {"status": "approved", "request_id": request_id, "approved_amount": amount,
            "approved_by": approved_by, "tier": policy["tier"], "remaining_after": remaining - amount}


def requires_human(amount: float, campaign_id: str = "", **_) -> bool:
    """Confirmation predicate: True makes ADK pause and ask a human.

    The tier comes from BigQuery. Amounts that exceed the remaining budget skip the
    human prompt, because there is nothing to approve: the tool rejects them directly.
    """
    repo = get_repo()
    budget = repo.get_budget(campaign_id) if campaign_id else None
    if budget is not None and amount > float(budget["remaining"]):
        return False
    return bool(repo.get_policy(float(amount))["requires_human"])


approve_budget_tool = FunctionTool(approve_budget, require_confirmation=requires_human)
