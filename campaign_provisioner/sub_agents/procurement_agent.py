from google.adk.agents import LlmAgent

from .. import config, handoff
from ..tools.procurement_tools import get_vendor_quotes
from ..workflow import guard
from ..workflow.integration import build_po_tool

procurement_agent = LlmAgent(
    name="procurement_agent",
    model=config.MODEL,
    description="Sources shortfall items: quotes vendors, recommends one, and creates purchase orders through Application Integration once budget is approved.",
    instruction=handoff.adapt(
        "You are the Procurement Agent. Step 1 (quote): for each shortfall SKU call get_vendor_quotes and "
        "recommend a vendor (cheapest unless lead time breaks the campaign date); report each line total and "
        "the grand total, then transfer to campaign_provisioner so budget approval can happen. "
        "Step 2 (order): only when the orchestrator says the budget is approved, call the purchase order "
        "tool once per SKU with request_id, sku, quantity and vendor_id. If a call returns BLOCKED, never "
        "retry or work around it: transfer to campaign_provisioner and explain. Never approve budget yourself."
    ),
    tools=[get_vendor_quotes, build_po_tool()],
    before_tool_callback=guard.before_tool,
    after_tool_callback=guard.after_tool,
    on_tool_error_callback=guard.on_tool_error,
)
