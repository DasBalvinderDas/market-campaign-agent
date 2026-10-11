from google.adk.agents import LlmAgent

from .. import config
from ..tools.brief_tools import build_requirements
from ..workflow.callbacks import on_tool_error

brief_analyst_agent = LlmAgent(
    name="brief_analyst_agent",
    model=config.MODEL,
    description="Breaks a launch brief into requirement lines per channel (creator kits, showroom displays, sales folios), "
                "personalised from the creator list and split by region.",
    instruction=(
        "You are the Brief Analyst. Do not write commentary between tool calls. Call build_requirements ONCE with the "
        "request_id and EVERY bundle of the brief: CREATOR_KIT (VIP creator / influencer unboxing or seeding kits), "
        "SHOWROOM_DISPLAY (showroom or flagship counter displays) and SALES_FOLIO (executive folios, sales "
        "leave-behinds). Use the quantities as stated; give a region (US, EMEA or APAC) only when the brief limits a "
        "bundle to one region. Never invent a bundle type or a quantity. Reply with the channel totals, the regional "
        "split and, for creator kits, the hoodie size and power-plug breakdown. If the tool returns an error, report it "
        "and stop. Reply to the root agent with your report."
    ),
    tools=[build_requirements],
    on_tool_error_callback=on_tool_error,
)
