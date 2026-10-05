from google.adk.agents import LlmAgent

from .. import config
from ..tools.budget_tools import check_budget, get_approval_policy
from ..workflow import guard
from ..workflow.integration import build_notify_tool

_EMAIL = config.async_approval()

_NOTIFY_STEP = (
    "3) If the policy requires a human, call the notify approver tool (request_id, campaign_id, amount, "
    "approver_role, summary; never pass email addresses, subject or body, the platform adds them) so the approver "
    "is emailed through Application Integration. If it reports NO_APPROVERS or an error, continue anyway and "
    "mention it. "
)
_NO_NOTIFY_STEP = (
    "3) Do not email anyone: when a human must approve, the orchestrator starts the approval request itself. "
)

budget_agent = LlmAgent(
    name="budget_agent",
    model=config.MODEL,
    description="Validates the campaign budget in BigQuery and looks up the approval tier. It does not approve spend: the orchestrator holds the human approval gate.",
    instruction=(
        "You are the Budget Agent. 1) check_budget for the campaign. 2) get_approval_policy for the total quoted "
        "cost. " + (_NO_NOTIFY_STEP if _EMAIL else _NOTIFY_STEP) +
        "4) Do NOT approve anything yourself. Transfer back to campaign_provisioner right away with: the total, "
        "the remaining budget, the tier and approver role, whether the total fits the remaining budget, "
        + ("" if _EMAIL else "whether the email was sent, ") +
        "and a one-sentence justification for the approval request."
    ),
    tools=[check_budget, get_approval_policy] + ([] if _EMAIL else [build_notify_tool()]),
    before_tool_callback=guard.before_tool,  # fills the approver email, subject and body for notify_approver
    after_tool_callback=guard.after_tool,
)
