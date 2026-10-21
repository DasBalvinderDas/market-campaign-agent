from google.adk.agents import LlmAgent

from .. import config
from ..tools.sourcing_tools import build_scenarios, report_vendor_delay
from ..workflow.callbacks import on_tool_error

sourcing_planner_agent = LlmAgent(
    name="sourcing_planner_agent",
    model=config.MODEL,
    description="Audits regional depot surplus and vendor lead times and computes the three sourcing options "
                "(full new, smart depot rebalance, eco launch) with cost, delivery buffer, savings and carbon; "
                "re-plans when a vendor is late.",
    instruction=(
        "You are the Sourcing Planner. Do not write commentary between tool calls. Call build_scenarios ONCE with the "
        "request_id. If the request says a vendor is late (for example 'RapidDisplay is 5 days late'), call "
        "report_vendor_delay first with the vendor and the days, then build_scenarios only if it tells you to. Reply "
        "with the tool's display_markdown EXACTLY as returned and nothing else, then on a new line: decision_mode and the "
        "recommended option. Show the other fields (stock_report, vendor_report, decision_card, date_options, "
        "carbon_explanation) only when the request asks for them. Never change or recompute any number. If a tool returns an error, report it and stop."
    ),
    tools=[build_scenarios, report_vendor_delay],
    on_tool_error_callback=on_tool_error,
)
