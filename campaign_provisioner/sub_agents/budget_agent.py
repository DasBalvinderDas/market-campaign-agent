from google.adk.agents import LlmAgent

from .. import config
from ..tools.budget_tools import approve_budget_tool, check_budget, get_approval_policy
from ..workflow import guard
from ..workflow.integration import build_notify_tool

budget_agent = LlmAgent(
    name="budget_agent",
    model=config.MODEL,
    description="Validates campaign budget in BigQuery and approves spend by tiered policy; high-value spend pauses for a named human approver.",
    instruction=(
        "You are the Budget Agent. 1) check_budget for the campaign. 2) get_approval_policy for the total. "
        "3) If the total exceeds the remaining budget, still call approve_budget: it returns 'rejected' without "
        "a human prompt and records the rejection. Then report the shortfall. "
        "4) If the policy requires a human, first call the notify approver tool (request_id, campaign_id, "
        "amount, approver_role, summary) so the approver is alerted through Application Integration. "
        "5) Call approve_budget with the total and a clear justification (items, vendor, cost, remaining "
        "budget). The platform pauses automatically for a human when the tier requires one - do not ask the "
        "user to approve in chat, just call the tool and wait. If it is rejected or the human declines, stop "
        "and transfer back to campaign_provisioner with the reason. When approved, transfer back to "
        "campaign_provisioner with approver and remaining budget."
    ),
    tools=[check_budget, get_approval_policy, build_notify_tool(), approve_budget_tool],
    after_tool_callback=guard.after_tool,
)
