from google.adk.agents import LlmAgent

from .. import config
from ..tools.brief_tools import build_requirements
from ..workflow.callbacks import on_tool_error

brief_analyst_agent = LlmAgent(
    name="brief_analyst_agent",
    model=config.MODEL,
    description="Breaks a launch brief into requirement lines per channel (guest welcome kits, venue display stands, sales folders), "
                "personalised from the guest list and split by region.",
    instruction=(
        "You are the Brief Analyst. Do not write commentary between tool calls. Call build_requirements ONCE with the "
        "request_id and EVERY bundle of the brief: GUEST_KIT (VIP guest welcome kits for a campaign), "
        "VENUE_DISPLAY (display stands for campaign venues or showrooms) and SALES_PACK (sales folders, sales "
        "leave-behinds). Use the quantities as stated; give a region (US, EMEA or APAC) only when the brief limits a "
        "bundle to one region. Single things the user wants as they are (for example 5 gift boxes for the US) go in items with a region; never invent a bundle type, an item or a quantity. If the tool says an item is unclear or a region is missing, return that message so the root can ask. Reply with the tool's display_markdown "
        "copied EXACTLY as returned, character for character, with real line breaks (never the two characters backslash and n), "
        "then on a new line: advice_count. Add nothing else. If the tool returns an error, report it "
        "and stop. Reply to the root agent with your report."
    ),
    tools=[build_requirements],
    on_tool_error_callback=on_tool_error,
)
