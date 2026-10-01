from google.adk.agents import LlmAgent

from .. import config
from ..tools.budget_tools import approve_budget_tool, check_budget

budget_agent = LlmAgent(
    name="budget_agent",
    model=config.MODEL,
    description="Validates campaign budget and approves spend; high-value requests pause for a human decision.",
    instruction=(
        "You are the Budget Agent. Call check_budget for the campaign, then approve_budget with the "
        "total procurement cost and a clear justification (items, vendor, cost, remaining budget). "
        f"Requests above ${config.HIGH_VALUE_THRESHOLD_USD:,.0f} are automatically paused for a human "
        "approver by the platform - do not ask the user to approve in chat, just call the tool and "
        "wait. If the result is rejected or the human declines, stop and transfer back to "
        "campaign_provisioner with the reason. When approved, transfer back to campaign_provisioner."
    ),
    tools=[check_budget, approve_budget_tool],
)
