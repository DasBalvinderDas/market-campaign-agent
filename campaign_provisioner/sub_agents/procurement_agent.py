from google.adk.agents import LlmAgent

from .. import config
from ..tools.procurement_tools import get_vendor_quotes, quote_shortfalls
from ..workflow import guard
from ..workflow.integration import build_po_tool

procurement_agent = LlmAgent(
    name="procurement_agent",
    model=config.MODEL,
    description="Sources shortfall items: quotes vendors, recommends one, and creates purchase orders through Application Integration once budget is approved.",
    instruction=(
        "You are the Procurement Agent. Do not write commentary between tool calls. Step 1 (quote): call quote_shortfalls ONCE with the request_id (it quotes every "
        "shortfall line from the cheapest active vendor); report each line (SKU, vendor, quantity, line total, lead time) and "
        "the grand total, then reply with your quotes so budget approval can happen. "
        "Step 2 (order): when the request says the budget is APPROVED, do not quote again and do not ask for approval: "
        "call the purchase order tool once per line with request_id, campaign_id, sku, quantity and vendor_id, then report the PO numbers. If a call returns BLOCKED, never "
        "retry or work around it: reply and explain. Never approve budget yourself."
    ),
    tools=[quote_shortfalls, get_vendor_quotes, build_po_tool()],
    before_tool_callback=guard.before_tool,
    after_tool_callback=guard.after_tool,
    on_tool_error_callback=guard.on_tool_error,
)
