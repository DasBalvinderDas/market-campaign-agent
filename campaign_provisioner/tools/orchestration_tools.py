"""Tools owned by the root orchestrator (state + audit)."""
from google.adk.tools import ToolContext

from .audit import audit


def register_campaign_request(campaign_id: str, summary: str, tool_context: ToolContext) -> dict:
    """Register a new campaign logistics request and get its request id.

    Args:
        campaign_id: Budget/campaign code, e.g. "CMP-SPRING-LAUNCH".
        summary: One-line description of what the campaign needs.
    """
    n = len(tool_context.state.get("requests", {})) + 1
    request_id = f"REQ-{n:03d}"
    requests = dict(tool_context.state.get("requests", {}))
    requests[request_id] = {"campaign_id": campaign_id, "summary": summary}
    tool_context.state["requests"] = requests
    audit(tool_context.state, "orchestrator", "request_registered",
          request_id=request_id, campaign_id=campaign_id)
    return {"status": "ok", "request_id": request_id, "campaign_id": campaign_id}


def get_audit_trail(tool_context: ToolContext) -> dict:
    """Return the audit trail of every governed action in this session."""
    return {"status": "ok", "events": tool_context.state.get("audit_trail", [])}
