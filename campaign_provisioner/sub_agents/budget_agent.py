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
        "amount, approver_role, summary; never pass email addresses, subject or body, the platform adds them) so the approver "
        "is emailed through Application Integration. If it reports NO_APPROVERS, continue anyway and tell the "
        "user that no email was sent. "
        "5) Call approve_budget with the total and a clear justification (items, vendor, cost, remaining "
        "budget). The platform pauses automatically for a human when the tier requires one - do not ask the "
        "user to approve in chat, just call the tool and wait. If it is rejected or the human declines, stop "
        "and transfer back to campaign_provisioner with the reason. When approved, transfer back to "
        "campaign_provisioner with approver and remaining budget."
    ),
    tools=[check_budget, get_approval_policy, build_notify_tool(), approve_budget_tool],
    before_tool_callback=guard.before_tool,  # fills the approver email, subject and body for notify_approver
    after_tool_callback=guard.after_tool,
)
