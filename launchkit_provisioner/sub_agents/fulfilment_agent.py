from google.adk.agents import LlmAgent

from .. import config
from ..tools.fulfilment_tools import execute_plan
from ..workflow.callbacks import on_tool_error

fulfilment_agent = LlmAgent(
    name="fulfilment_agent",
    model=config.MODEL,
    description="Places the orders of an APPROVED sourcing scenario through Application Integration: purchase orders, "
                "depot transfers and the tracking update to the launch team. Refuses without an approved sign-off.",
    instruction=(
        "You are the Fulfilment agent. Do not write commentary between tool calls. Call execute_plan ONCE with the "
        "request_id. Reply with the tool's display_markdown EXACTLY as returned (it is already short). If it "
        "says BLOCKED or reports failed lines, say so plainly and do not retry. Never create an order any other way."
    ),
    tools=[execute_plan],
    on_tool_error_callback=on_tool_error,
)
